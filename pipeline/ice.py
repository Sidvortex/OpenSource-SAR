#!/usr/bin/env python3
"""
Part 7: ice. Glacier speed from NISAR GOFF (geocoded pixel offsets).

GOFF tracks how far patterns in the radar image shifted between two passes, in
metres along track (the flight direction) and in slant range (the look direction).
Speed = size of that shift, with slant range converted to ground range, divided by the days between passes.

    python pipeline/ice.py demo --hotspot shisper          # synthetic surging glacier, labelled
    python pipeline/ice.py process --hotspot shisper       # real GOFF files in pipeline/work/shisper/
"""
import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import h5py
import numpy as np

import dance
import layers
import nisar_io
import water
from layers import WORK, load_spot

INCIDENCE_DEG = 40.0
FAST_M_DAY = 1.0


def read_goff_crop(path, bbox, margin_m=2000):
    with h5py.File(path, "r") as f:
        along = nisar_io._find_datasets(f, {"alongTrackOffset"})
        rng_ = nisar_io._find_datasets(f, {"slantRangeOffset"})
        if not along or not rng_:
            raise KeyError("No alongTrackOffset/slantRangeOffset datasets. Run the inspect command and add the names you see.")
        a_ds, r_ds = f[along[0]], f[rng_[0]]
        grid = a_ds.parent
        while grid.name != "/" and not any(n in grid for n in nisar_io.X_NAMES):
            grid = grid.parent
        epsg = nisar_io._epsg(grid)
        x = np.asarray(nisar_io._first(grid, nisar_io.X_NAMES)[()], dtype="float64")
        y = np.asarray(nisar_io._first(grid, nisar_io.Y_NAMES)[()], dtype="float64")
        from rasterio.warp import transform_bounds
        west, south, east, north = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *bbox, densify_pts=21)
        xr = nisar_io._index_range(x, west - margin_m, east + margin_m)
        yr = nisar_io._index_range(y, south - margin_m, north + margin_m)
        if xr is None or yr is None:
            return None
        a = a_ds[yr[0]:yr[1], xr[0]:xr[1]].astype("float32")
        r = r_ds[yr[0]:yr[1], xr[0]:xr[1]].astype("float32")
        ref, sec = nisar_io.pair_dates(path)
        ground_range = r / np.sin(np.radians(INCIDENCE_DEG))
        speed = np.hypot(a, ground_range) / max((sec - ref).days, 1)
        return ref, sec, nisar_io.Grid(acquired=ref, epsg=epsg, x=x[xr[0]:xr[1]], y=y[yr[0]:yr[1]],
                                        bands={"SPEED": speed}, source=str(path))


def build_layers(spot, files, synthetic, res):
    target = water.target_grid(spot["bbox"], res=res)
    pairs = []
    for path in sorted(files):
        got = read_goff_crop(path, spot["bbox"])
        if got:
            ref, sec, grid = got
            pairs.append((ref, sec, water.to_target(grid, target)["SPEED"], Path(path).name))
            print(f"  read {ref} to {sec}  {Path(path).name}")
    if not pairs:
        sys.exit("No GOFF products cover this area.")
    vmax = float(max(1.0, np.ceil(max(np.nanpercentile(p[2], 99.5) for p in pairs))))
    out = layers.layer_folder(spot["id"])
    frames, peaks = [], []
    for ref, sec, speed, name in pairs:
        stamp = f"{ref.isoformat()}_{sec.isoformat()}"
        layers.save_ramp(speed, 0, vmax, "magma", out / f"speed_{stamp}.png")
        peak = float(np.nanpercentile(speed, 99.5))
        peaks.append(peak)
        frames.append({"date": sec.isoformat(), "start": ref.isoformat(),
                       "label": f"{ref:%b} {ref.day} to {sec:%b} {sec.day}, {sec.year}",
                       "files": {"speed": f"speed_{stamp}.png"},
                       "stats": {"max_speed_m_day": round(peak, 2),
                                 "fast_km2": round(water.area_km2(np.isfinite(speed) & (speed > FAST_M_DAY), target), 1)},
                       "sources": [name]})
    factor = layers.series_factor(target.height, target.width)
    count, h, w = layers.write_series(out, "series.bin", [layers.reduce_grid(p[2], factor) for p in pairs])
    t = [(p[1] - pairs[0][1]).days for p in pairs]
    place = dance.classify(t, peaks, 0.05 * max(peaks), unit="m/day", when=[f"{p[1]:%b} {p[1].day}" for p in pairs])
    place["basis"] = "the glacier's top speed"
    return layers.write_manifest(spot, out, {
        "module": "ice", "title": f"{spot['name']}: the flowing ice",
        "headline": f"The fastest ice moved about {peaks[-1]:.1f} m a day in the latest pair, "
                    f"{'up from' if peaks[-1] > peaks[0] else 'compared with'} {peaks[0]:.1f} m a day in the first.",
        "synthetic": synthetic, "product": "NISAR L2 GOFF (geocoded pixel offsets)",
        "bounds": target.corners_lonlat(), "event": None, "frame_noun": "pairs", "sides": ["Earlier pair", "Later pair"],
        "side_stat": {"id": "max_speed_m_day", "label": "Top speed", "unit": "m/day"},
        "compare": [0, len(frames) - 1],
        "layers": [{"id": "speed", "label": "Ice speed", "opacity": 0.9,
                    "ramp": {"colors": layers.ramp_colours("magma"), "min": 0, "max": vmax, "unit": "m/day",
                             "low": "Still", "high": f"{vmax:.0f} m a day"},
                    "note": "How far the ice surface moved per day between two passes."}],
        "stats": [{"id": "max_speed_m_day", "label": "Top speed", "unit": "m/day"},
                  {"id": "fast_km2", "label": f"Faster than {FAST_M_DAY:.0f} m/day", "unit": "km²"}],
        "chart": {"area": "max_speed_m_day", "line": None, "label": "Top speed, m/day"},
        "series": {"file": "series.bin", "count": count, "width": w, "height": h, "factor": factor,
                   "full_width": target.width, "full_height": target.height,
                   "dates": [p[1].isoformat() for p in pairs], "label": "Ice speed", "unit": "m/day", "sigma": 0.08},
        "dance": place,
        "method": ["Pixel offsets track how far surface patterns moved between two passes 12 days apart.",
                   f"Slant-range offsets are converted to ground range using a {INCIDENCE_DEG:.0f}° incidence angle.",
                   "Compare with NASA ITS_LIVE velocities for the long-term baseline.",
                   "At high latitudes the ionosphere can bias offsets; treat those results with care."],
        "frames": frames,
    })


def make_demo_goff(spot, out_dir, spacing=60.0, epsg=32643):
    """SYNTHETIC GOFF files: a curved valley glacier whose flow speeds up pair after pair (a surge)."""
    from rasterio.warp import transform, transform_bounds
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = spot["bbox"]
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{epsg}", west, south, east, north)
    xs, ys = np.arange(x0 - 1000, x1 + 1000, spacing), np.arange(y1 + 1000, y0 - 1000, -spacing)
    gx, gy = np.meshgrid(xs, ys)
    lons, lats = np.linspace(74.52, 74.64, 60), 36.47 - 0.14 * np.linspace(0, 1, 60) ** 1.2 + 0.01 * np.sin(np.linspace(0, 3, 60))
    cx, cy = (np.asarray(v) for v in transform("EPSG:4326", f"EPSG:{epsg}", lons.tolist(), lats.tolist()))
    dist = np.full(gx.shape, np.inf)
    along = np.zeros(gx.shape)
    for i, (px, py) in enumerate(zip(cx, cy)):
        d = np.hypot(gx - px, gy - py)
        closer = d < dist
        dist[closer], along[closer] = d[closer], i / (len(cx) - 1)
    ice = dist < 900
    profile = np.where(ice, np.clip(1 - (dist / 900) ** 2, 0, 1) * (0.3 + 1.2 * np.sin(np.pi * along) ** 1.5), 0)
    rng = np.random.default_rng(3)
    passes = [date(2026, 6, 19) + timedelta(days=12 * i) for i in range(9)]
    passes = [d for d in passes if not date(2026, 7, 27) <= d <= date(2026, 8, 10)]
    written = []
    for i, (ref, sec) in enumerate(zip(passes, passes[1:])):
        if (sec - ref).days != 12:
            continue
        surge = 1 + 0.12 * i ** 2                                       # speeding up faster and faster: a surge
        speed = profile * surge + np.abs(rng.normal(0, 0.05, gx.shape))
        metres = speed * 12
        stamps = [f"{d:%Y%m%d}T005000_{d:%Y%m%d}T005040" for d in (ref, sec)]
        path = out_dir / f"SYNTHETIC_NISAR_L2_PR_GOFF_DEMO_{stamps[0]}_{stamps[1]}_DEMO.h5"
        with h5py.File(path, "w") as f:
            grid = f.create_group("science/LSAR/GOFF/grids/frequencyA/pixelOffsets")
            grid["xCoordinates"], grid["yCoordinates"] = xs, ys
            proj = grid.create_dataset("projection", data=np.int32(epsg))
            proj.attrs["epsg_code"] = np.int32(epsg)
            hh = grid.create_group("HH")
            hh["alongTrackOffset"] = (metres * 0.8).astype("float32")
            hh["slantRangeOffset"] = (metres * 0.6 * np.sin(np.radians(INCIDENCE_DEG))).astype("float32")
        written.append(path)
    return written


def main():
    parser = argparse.ArgumentParser(description="SARabande Part 7: ice speed from GOFF.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "process"):
        p = sub.add_parser(name)
        p.add_argument("--hotspot", default="shisper")
        p.add_argument("--res", type=float, default=60.0)
        p.add_argument("--work")
    p = sub.add_parser("inspect")
    p.add_argument("file")
    args = parser.parse_args()
    if args.command == "inspect":
        print("\n".join(nisar_io.list_tree(args.file)))
        return
    spot = load_spot(args.hotspot)
    if args.command == "demo":
        print("Writing SYNTHETIC GOFF products (not NISAR measurements)...")
        build_layers(spot, make_demo_goff(spot, WORK / f"demo-{spot['id']}"), True, args.res)
    else:
        folder = Path(args.work) if args.work else WORK / spot["id"]
        files = sorted(folder.glob("*.h5"))
        if not files:
            sys.exit(f"No .h5 files in {folder}. Download GOFF products for this area first (see DEPLOY.md).")
        build_layers(spot, files, any(f.name.startswith("SYNTHETIC_") for f in files), args.res)


if __name__ == "__main__":
    main()
