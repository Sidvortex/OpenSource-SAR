#!/usr/bin/env python3
"""
Part 3: the earthquake. Turns NISAR GUNW interferograms into movement maps.

    python pipeline/quake.py demo --hotspot venezuela-coast       # synthetic, labelled, no download
    python pipeline/quake.py download --hotspot venezuela-coast   # needs a free Earthdata login
    python pipeline/quake.py process --hotspot venezuela-coast
    python pipeline/quake.py inspect path/to/GUNW.h5

An interferogram compares the radar phase of two passes 12 days apart. One full
colour cycle ("fringe") is half a wavelength, about 12 cm, of movement toward or
away from the satellite along its line of sight.

Sign convention: movement = -wavelength / (4 pi) x phase, positive = toward the
radar. Check this against the NISAR GUNW product specification before publishing,
and use --flip-sign if it is the other way round.
"""
import argparse
import json
import sys
import warnings
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import h5py
import numpy as np
from rasterio.warp import transform, transform_bounds
from scipy import ndimage

import coverage_check as cc
import dance
import layers
import nisar_io
import water
from layers import ROOT, WORK, load_spot
from water_dance import earthdata_session

MIN_COHERENCE = 0.3
MOVED_CM = 10.0


def pretty(d):
    return f"{d:%b} {d.day}, {d.year}"


def reference_ring(values, frac=0.08):
    """Median of the scene's outer ring: far from most faults, so a fair zero point."""
    h, w = values.shape
    ring = np.ones_like(values, dtype=bool)
    ring[int(h * frac):h - int(h * frac), int(w * frac):w - int(w * frac)] = False
    sample = values[ring & np.isfinite(values)]
    return float(np.median(sample)) if sample.size else 0.0


def movement_cm(pair, iono=True, flip=False):
    """Masked line-of-sight movement in cm (positive = toward the radar), plus coherence."""
    phase = pair.phase.astype("float64")
    valid = np.isfinite(phase)
    if pair.coherence is not None:
        valid &= pair.coherence >= MIN_COHERENCE
    if pair.components is not None:
        valid &= pair.components > 0            # 0 = pixels the unwrapper could not connect
    if iono and pair.ionosphere is not None:
        phase = phase - pair.ionosphere
    los = -pair.wavelength / (4 * np.pi) * phase * 100.0
    if flip:
        los = -los
    los[~valid] = np.nan
    return los.astype("float32")


def build_layers(spot, files, synthetic, res, iono=True, flip=False):
    target = water.target_grid(spot["bbox"], res=res)
    pairs = []
    wavelength = None
    for path in sorted(files):
        pair = nisar_io.read_gunw_crop(path, spot["bbox"])
        if pair is None:
            print(f"  skipped (outside the area): {Path(path).name}")
            continue
        wavelength = pair.wavelength
        bands = {"LOS": movement_cm(pair, iono, flip)}
        if pair.coherence is not None:
            bands["COH"] = pair.coherence
        grid = nisar_io.Grid(acquired=pair.reference, epsg=pair.epsg, x=pair.x, y=pair.y, bands=bands, source=str(path))
        pairs.append((pair.reference, pair.secondary, water.to_target(grid, target), Path(path).name))
        print(f"  read {pair.reference} to {pair.secondary}  {Path(path).name}")
    if not pairs:
        sys.exit("No interferograms cover this area.")

    # Pairs over the same dates (adjacent frames) are averaged into one map.
    merged = defaultdict(list)
    for ref, sec, bands, name in pairs:
        merged[(ref, sec)].append((bands, name))
    maps = {}
    for key, items in sorted(merged.items()):
        with np.errstate(invalid="ignore"), warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN pixels (sea) stay NaN
            los = np.nanmean(np.stack([b["LOS"] for b, _ in items]), axis=0)
            coh = np.nanmean(np.stack([b["COH"] for b, _ in items]), axis=0) if "COH" in items[0][0] else None
        los -= reference_ring(los)
        maps[key] = (los, coh, [n for _, n in items])

    # One shared colour range, so every pair is judged on the same scale.
    extreme = max(np.nanpercentile(np.abs(los), 99.5) for los, _, _ in maps.values())
    vmax = float(max(5.0, np.ceil(extreme / 5.0) * 5.0))
    half_wave_cm = (wavelength or 0.2385) / 2 * 100
    out = layers.layer_folder(spot["id"])
    frames = []
    for (ref, sec), (los, coh, sources) in maps.items():
        stamp = f"{ref.isoformat()}_{sec.isoformat()}"
        files = {"displacement": f"move_{stamp}.png", "fringes": f"fringes_{stamp}.png"}
        layers.save_ramp(los, -vmax, vmax, "RdBu", out / files["displacement"])
        layers.save_cyclic(los, half_wave_cm, "hsv", out / files["fringes"])
        if coh is not None:
            files["coherence"] = f"quality_{stamp}.webp"
            layers.save_ramp(coh, 0.0, 1.0, "gray", out / files["coherence"], webp=True)
        toward = np.nanpercentile(los, 99.5)
        away = np.nanpercentile(los, 0.5)
        moved = np.isfinite(los) & (np.abs(los) > MOVED_CM)
        frames.append({
            "date": sec.isoformat(),
            "start": ref.isoformat(),
            "label": f"{ref:%b} {ref.day} to {pretty(sec)}",
            "files": files,
            "stats": {"max_toward_cm": round(max(float(toward), 0.0), 1), "max_away_cm": round(max(float(-away), 0.0), 1),
                      "max_abs_cm": round(max(float(toward), float(-away), 0.0), 1),
                      "moved_km2": round(water.area_km2(moved, target), 1)},
            "sources": sources,
        })

    # Part 4: each pixel's cumulative movement, its 1-sigma uncertainty from coherence,
    # and the place's dance measured at the spot that moved most.
    keys = list(maps)
    chained = all(keys[i][1] == keys[i + 1][0] for i in range(len(keys) - 1))
    factor = layers.series_factor(target.height, target.width)
    reduced = [layers.reduce_grid(maps[k][0], factor) for k in keys]
    sig_pairs = []
    for k in keys:
        coh = maps[k][1]
        if coh is None:
            sig_pairs.append(np.full_like(reduced[0], 1.0))
            continue
        g = np.clip(layers.reduce_grid(coh, factor), 0.05, 0.999)
        sigma_phase = np.sqrt(1 - g ** 2) / (g * np.sqrt(2 * 10))          # about 10 looks
        sig_pairs.append((wavelength or 0.2385) / (4 * np.pi) * sigma_phase * 100)
    if chained:
        dates = [keys[0][0].isoformat()] + [k[1].isoformat() for k in keys]
        values = [np.zeros_like(reduced[0])] + list(np.cumsum(np.stack(reduced), axis=0))
        sigmas = [np.full_like(reduced[0], 0.1)] + list(np.sqrt(np.cumsum(np.stack(sig_pairs) ** 2, axis=0)))
        label = "Total movement since the first pass"
    else:
        dates = [k[1].isoformat() for k in keys]
        values, sigmas, label = reduced, sig_pairs, "Movement in each pair"
    count, h, w = layers.write_series(out, "series.bin", values)
    layers.write_series(out, "sigma.bin", sigmas)
    final = np.abs(values[-1])
    if np.isfinite(final).any():
        r, c = np.unravel_index(np.nanargmax(final), final.shape)
        t_days = [(date.fromisoformat(d) - date.fromisoformat(dates[0])).days for d in dates]
        place_dance = dance.classify(t_days, [float(v[r, c]) for v in values], [float(s[r, c]) for s in sigmas],
                                     unit="cm", when=[pretty(date.fromisoformat(d)).rsplit(',', 1)[0] for d in dates])
    else:
        place_dance = {"dance": "still", "confidence": "low", "reason": "No reliable pixels."}
    place_dance["basis"] = "the spot that moved most"
    series = {"file": "series.bin", "sigma_file": "sigma.bin", "count": count, "width": w, "height": h, "factor": factor,
              "full_width": target.width, "full_height": target.height, "dates": dates, "label": label, "unit": "cm"}

    event = spot.get("event")
    across = [f for f in frames if event and f["start"] < event < f["date"]]
    if across:
        e = date.fromisoformat(event)
        headline = (f"Across the {pretty(e)} earthquakes, the ground moved up to "
                    f"{across[0]['stats']['max_abs_cm']:.0f} cm toward or away from the radar.")
    else:
        headline = f"The largest movement in these pairs was {max(f['stats']['max_abs_cm'] for f in frames):.0f} cm."
    default_right = frames.index(across[0]) if across else len(frames) - 1
    manifest_layers = [
        {"id": "displacement", "label": "Movement", "opacity": 0.85,
         "ramp": {"colors": layers.ramp_colours("RdBu"), "min": -vmax, "max": vmax, "unit": "cm",
                  "low": "Away from the radar", "high": "Toward the radar"},
         "note": "Movement along the radar's line of sight, which mixes up-down and sideways motion."},
        {"id": "fringes", "label": "Fringes", "opacity": 0.8,
         "ramp": {"colors": layers.ramp_colours("hsv", 7), "min": 0, "max": round(half_wave_cm, 1), "unit": "cm",
                  "low": "One colour cycle", "high": f"= {half_wave_cm:.0f} cm of movement"},
         "note": "Tightly packed rainbow bands mean the ground moved a lot over a short distance."},
    ]
    if any("coherence" in f["files"] for f in frames):
        manifest_layers.append({"id": "coherence", "label": "Data quality", "opacity": 0.85,
                                "ramp": {"colors": layers.ramp_colours("gray"), "min": 0, "max": 1, "unit": "",
                                         "low": "Unreliable", "high": "Reliable"},
                                "note": f"Pixels below {MIN_COHERENCE} coherence are left out of the movement map."})
    return layers.write_manifest(spot, out, {
        "module": "ground",
        "title": f"{spot['name']}: the earthquake",
        "headline": headline,
        "synthetic": synthetic,
        "product": "NISAR L2 GUNW (geocoded unwrapped interferograms), HH polarisation",
        "bounds": target.corners_lonlat(),
        "event": event,
        "frame_noun": "pairs",
        "sides": ["Earlier pair", "Later pair"],
        "side_stat": {"id": "max_abs_cm", "label": "Largest movement", "unit": "cm"},
        "compare": [max(default_right - 1, 0), default_right] if default_right > 0 else [0, min(1, len(frames) - 1)],
        "layers": manifest_layers,
        "stats": [
            {"id": "max_toward_cm", "label": "Largest toward", "unit": "cm"},
            {"id": "max_away_cm", "label": "Largest away", "unit": "cm"},
            {"id": "moved_km2", "label": f"Moved over {MOVED_CM:.0f} cm", "unit": "km²"},
        ],
        "chart": {"area": "max_abs_cm", "line": None, "label": "Largest movement, cm"},
        "series": series,
        "dance": place_dance,
        "method": [
            "Each interferogram compares two passes 12 days apart; the phase change becomes centimetres along the line of sight.",
            f"Pixels with coherence below {MIN_COHERENCE}, or that the unwrapper could not connect, are left out.",
            "The ionospheric phase screen shipped with each product is subtracted." if iono else "No ionospheric correction was applied.",
            "Movement is measured relative to the median of the scene's outer edge, far from the fault.",
            f"One fringe (colour cycle) equals half the radar wavelength: about {half_wave_cm:.0f} cm.",
        ],
        "frames": frames,
    })


# ---------------------------------------------------------------- synthetic demo

def make_demo_pairs(spot, out_dir, spacing=150.0, epsg=32619, slip_m=2.4, locking_km=12.0):
    """
    SYNTHETIC interferograms in the GUNW layout: a right-lateral strike-slip rupture along
    the coast (a textbook screw-dislocation model), atmospheric noise, a decorrelated sea
    and fault zone, and a small ionospheric ramp that the pipeline should remove.
    """
    from matplotlib.path import Path as MplPath

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = spot["bbox"]
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{epsg}", west, south, east, north)
    xs = np.arange(x0 - 3000, x1 + 3000, spacing)
    ys = np.arange(y1 + 3000, y0 - 3000, -spacing)
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = (np.asarray(v).reshape(gx.shape) for v in transform(f"EPSG:{epsg}", "EPSG:4326", gx.ravel().tolist(), gy.ravel().tolist()))

    land = np.zeros(gx.shape, dtype=bool)
    points = np.column_stack([lon.ravel(), lat.ravel()])
    for feature in json.loads((ROOT / "data" / "basemap" / "land.geojson").read_text())["features"]:
        geom = feature["geometry"]
        for polygon in (geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]):
            land |= MplPath(np.asarray(polygon[0])).contains_points(points).reshape(gx.shape)

    # Fault trace along the coast, in projected metres.
    (fx0, fx1), (fy0, fy1) = transform("EPSG:4326", f"EPSG:{epsg}", [-68.3, -66.9], [10.42, 10.56])
    strike = np.array([fx1 - fx0, fy1 - fy0]) / np.hypot(fx1 - fx0, fy1 - fy0)
    rel = np.stack([gx - fx0, gy - fy0], axis=-1)
    along = rel @ strike                                   # metres along the fault
    across = rel @ np.array([-strike[1], strike[0]])       # metres perpendicular to it
    length = np.hypot(fx1 - fx0, fy1 - fy0)
    fade = 25000.0                                         # slip dies away smoothly past the rupture ends
    taper = 0.5 * (np.tanh(along / fade) - np.tanh((along - length) / fade))
    u_parallel = slip_m / np.pi * np.arctan(across / (locking_km * 1000)) * taper
    east_motion = u_parallel * strike[0]
    los_true_m = 0.62 * east_motion                        # roughly E-W look direction, about 40 degrees off vertical

    rng = np.random.default_rng(7)
    wavelength = nisar_io.SPEED_OF_LIGHT / nisar_io.DEFAULT_CENTER_FREQUENCY
    passes = [date(2026, 6, 18) + timedelta(days=12 * i) for i in range(4)]
    written = []
    for i, (ref, sec) in enumerate(zip(passes, passes[1:])):
        coseismic = ref < date(2026, 6, 24) < sec
        signal = los_true_m if coseismic else 0.03 * los_true_m / max(1, i)   # small afterslip later
        atmosphere = ndimage.gaussian_filter(rng.standard_normal(gx.shape), 30)
        atmosphere = atmosphere / np.abs(atmosphere).max() * 0.02
        los = signal + atmosphere + rng.normal(0, 0.006, gx.shape)
        ionosphere = 0.6 * (gx - gx.min()) / (gx.max() - gx.min())       # radians, removed by the pipeline
        phase = -(4 * np.pi / wavelength) * los + ionosphere
        coherence = np.where(land, rng.normal(0.72, 0.1, gx.shape), rng.normal(0.12, 0.05, gx.shape))
        if coseismic:
            coherence[np.abs(across) < 2500] *= 0.35                        # damaged ground along the rupture
        coherence = np.clip(coherence, 0, 1)
        components = (coherence >= 0.3).astype("uint8")
        stamps = [f"{d:%Y%m%d}T101500_{d:%Y%m%d}T101540" for d in (ref, sec)]
        path = out_dir / f"SYNTHETIC_NISAR_L2_PR_GUNW_DEMO_{stamps[0]}_{stamps[1]}_DEMO.h5"
        with h5py.File(path, "w") as f:
            grid = f.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram")
            grid["xCoordinates"], grid["yCoordinates"] = xs, ys
            proj = grid.create_dataset("projection", data=np.int32(epsg))
            proj.attrs["epsg_code"] = np.int32(epsg)
            hh = grid.create_group("HH")
            hh["unwrappedPhase"] = phase.astype("float32")
            hh["coherenceMagnitude"] = coherence.astype("float32")
            hh["connectedComponents"] = components
            hh["ionospherePhaseScreen"] = ionosphere.astype("float32")
            f["science/LSAR/GUNW/grids/frequencyA/centerFrequency"] = nisar_io.DEFAULT_CENTER_FREQUENCY
        written.append(path)
    return written


# ---------------------------------------------------------------- commands

def cmd_download(args):
    spot = load_spot(args.hotspot)
    west, south, east, north = spot["bbox"]
    window = spot.get("window", {})
    area = {"label": spot["name"], "wkt": cc.bbox(west, south, east, north),
            "start": window.get("start", cc.PROVISIONAL_START), "end": window.get("end")}
    results = cc.search("GUNW", area, args.maturity, include_ur=False)
    if not results:
        sys.exit("No GUNW products found. Run update_coverage.py to check this area.")
    print(f"Found {len(results)} GUNW products; downloading up to {args.max}.")
    out = WORK / spot["id"]
    out.mkdir(parents=True, exist_ok=True)
    session = earthdata_session()
    for result in list(results)[:args.max]:
        print(f"  {result.properties.get('sceneName')}")
        result.download(path=str(out), session=session)
    print(f"Saved to {out}. Next: python pipeline/quake.py process --hotspot {spot['id']}")


def cmd_process(args):
    spot = load_spot(args.hotspot)
    folder = Path(args.work) if args.work else WORK / spot["id"]
    files = sorted(folder.glob("*.h5"))
    if not files:
        sys.exit(f"No .h5 files in {folder}. Run the download command first.")
    build_layers(spot, files, any(f.name.startswith("SYNTHETIC_") for f in files), args.res, not args.no_iono, args.flip_sign)


def cmd_demo(args):
    spot = load_spot(args.hotspot)
    print("Writing SYNTHETIC demo interferograms (not NISAR measurements)...")
    files = make_demo_pairs(spot, WORK / f"demo-{spot['id']}")
    build_layers(spot, files, synthetic=True, res=args.res)


def main():
    parser = argparse.ArgumentParser(description="SARabande Part 3: the earthquake.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("download")
    p.add_argument("--hotspot", default="venezuela-coast")
    p.add_argument("--max", type=int, default=6)
    p.add_argument("--maturity", default="PROVISIONAL", choices=["PROVISIONAL", "BETA"])
    p.set_defaults(func=cmd_download)
    p = sub.add_parser("process")
    p.add_argument("--hotspot", default="venezuela-coast")
    p.add_argument("--work")
    p.add_argument("--res", type=float, default=150.0)
    p.add_argument("--no-iono", action="store_true", help="skip the ionospheric correction")
    p.add_argument("--flip-sign", action="store_true", help="if the product's sign convention is the other way round")
    p.set_defaults(func=cmd_process)
    p = sub.add_parser("demo")
    p.add_argument("--hotspot", default="venezuela-coast")
    p.add_argument("--res", type=float, default=150.0)
    p.set_defaults(func=cmd_demo)
    p = sub.add_parser("inspect")
    p.add_argument("file")
    p.set_defaults(func=lambda a: print("\n".join(nisar_io.list_tree(a.file))))
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
