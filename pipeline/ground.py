"""
Ground motion (Parts 3 and 5): earthquakes and slowly sinking ground from NISAR GUNW pairs.

Earthquake sites (a hotspot with an "event" date) get movement, fringes and data
quality per pair. Sites without an event also get:
  * total movement since the first pass, one map per pass (watch a city sink);
  * a velocity map in cm per year, averaged over every pair;
  * GNSS validation, when station files are in data/gnss/<place>/.

NISAR only makes 12-day nearest-neighbour pairs, so the Jul 27 to Aug 10 instrument
gap breaks the chain. Totals bridge a gap with each pixel's average rate. This is
flagged in the manifest and never done across an event.
"""
import warnings
from datetime import date
from pathlib import Path
import sys

import numpy as np

warnings.filterwarnings("ignore", category=RuntimeWarning)   # all-NaN pixels (sea, shadow) are expected

import dance
import gnss
import layers
import nisar_io
import water
from layers import DATA

MIN_COHERENCE = 0.3
MOVED_CM = 10.0
INCIDENCE_DEG = 40.0          # NISAR looks about 40 degrees off vertical


def pretty(d):
    return f"{d:%b} {d.day}, {d.year}"


def short(d):
    return f"{d:%b} {d.day}"


def reference_ring(values, frac=0.08):
    """Median of the scene's outer ring: far from most faults and bowls, so a fair zero point."""
    h, w = values.shape
    ring = np.ones_like(values, dtype=bool)
    ring[int(h * frac):h - int(h * frac), int(w * frac):w - int(w * frac)] = False
    sample = values[ring & np.isfinite(values)]
    return float(np.median(sample)) if sample.size else 0.0


def movement_cm(pair, iono=True, flip=False):
    """Masked line-of-sight movement in cm. Positive = toward the radar (check the product spec)."""
    phase = pair.phase.astype("float64")
    valid = np.isfinite(phase)
    if pair.coherence is not None:
        valid &= pair.coherence >= MIN_COHERENCE
    if pair.components is not None:
        valid &= pair.components > 0
    if iono and pair.ionosphere is not None:
        phase = phase - pair.ionosphere
    los = -pair.wavelength / (4 * np.pi) * phase * 100.0
    if flip:
        los = -los
    los[~valid] = np.nan
    return los.astype("float32")


def _nanmean(stack):
    with np.errstate(invalid="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(stack, axis=0)


def _read_pairs(spot, files, target, iono, flip):
    merged = {}
    wavelength = 0.2385
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
        merged.setdefault((pair.reference, pair.secondary), []).append((water.to_target(grid, target), Path(path).name))
        print(f"  read {pair.reference} to {pair.secondary}  {Path(path).name}")
    if not merged:
        sys.exit("No interferograms cover this area.")
    maps = {}
    for key in sorted(merged):
        items = merged[key]
        los = _nanmean(np.stack([b["LOS"] for b, _ in items]))
        coh = _nanmean(np.stack([b["COH"] for b, _ in items])) if "COH" in items[0][0] else None
        los -= reference_ring(los)
        maps[key] = (los.astype("float32"), coh, [n for _, n in items])
    return maps, wavelength


def _sigma_cm(coh, wavelength, looks=10):
    g = np.clip(coh, 0.05, 0.999)
    return wavelength / (4 * np.pi) * np.sqrt(1 - g ** 2) / (g * np.sqrt(2 * looks)) * 100


def _cumulative(keys, grids, sigmas, event):
    """Totals since the first pass, bridging gaps with the average rate (never across an event)."""
    rates = np.stack([g / max((k[1] - k[0]).days, 1) for g, k in zip(grids, keys)])
    mean_rate = _nanmean(rates)
    dates, totals, spreads, bridged = [keys[0][0]], [np.zeros_like(grids[0])], [np.full_like(grids[0], 0.1)], []
    running, var = np.zeros_like(grids[0]), np.zeros_like(grids[0])
    for k, g, s in zip(keys, grids, sigmas):
        if dates[-1] != k[0]:
            if event and dates[-1] < event < k[0]:
                return None, mean_rate, []          # an event inside a gap: totals would be guesswork
            gap_days = (k[0] - dates[-1]).days
            running = running + mean_rate * gap_days
            var = var + (np.nanstd(rates, axis=0) * gap_days) ** 2
            dates.append(k[0]); totals.append(running.copy()); spreads.append(np.sqrt(var))
            bridged.append([dates[-2].isoformat(), k[0].isoformat()])
        running = running + np.nan_to_num(g, nan=0.0) * np.where(np.isfinite(g), 1, np.nan)
        var = var + s ** 2
        dates.append(k[1]); totals.append(running.copy()); spreads.append(np.sqrt(var))
    return (dates, totals, spreads), mean_rate, bridged


def build_layers(spot, files, synthetic, res, iono=True, flip=False, gnss_dir=None):
    target = water.target_grid(spot["bbox"], res=res)
    maps, wavelength = _read_pairs(spot, files, target, iono, flip)
    keys = list(maps)
    event = date.fromisoformat(spot["event"]) if spot.get("event") else None
    slow = event is None and len(keys) >= 3            # sinking-ground site: totals and velocity maps

    full_sig = [(_sigma_cm(maps[k][1], wavelength) if maps[k][1] is not None else np.full_like(maps[k][0], 1.0)) for k in keys]
    cum_full, rate_full, bridged = _cumulative(keys, [maps[k][0] for k in keys], full_sig, event)
    extreme = max(np.nanpercentile(np.abs(maps[k][0]), 99.5) for k in keys)
    vmax = float(max(2.0, np.ceil(extreme / 5.0) * 5.0 if extreme >= 5 else np.ceil(extreme)))
    half_wave_cm = wavelength / 2 * 100
    out = layers.layer_folder(spot["id"])

    if slow:
        velocity = rate_full * 365.25
        vel_max = float(max(1.0, np.ceil(np.nanpercentile(np.abs(velocity), 99.5) / 5.0) * 5.0))
        layers.save_ramp(velocity, -vel_max, vel_max, "RdBu", out / "velocity.png")
        tot_max = float(max(1.0, np.ceil(max(np.nanpercentile(np.abs(t), 99.5) for t in cum_full[1]))))
        total_at = {d: t for d, t in zip(cum_full[0], cum_full[1])}

    frames = []
    for (ref, sec) in keys:
        los, coh, sources = maps[(ref, sec)]
        stamp = f"{ref.isoformat()}_{sec.isoformat()}"
        files_out = {"displacement": f"move_{stamp}.png", "fringes": f"fringes_{stamp}.png"}
        layers.save_ramp(los, -vmax, vmax, "RdBu", out / files_out["displacement"])
        layers.save_cyclic(los, half_wave_cm, "hsv", out / files_out["fringes"])
        if coh is not None:
            files_out["coherence"] = f"quality_{stamp}.webp"
            layers.save_ramp(coh, 0.0, 1.0, "gray", out / files_out["coherence"], webp=True)
        stats = {"max_toward_cm": round(max(float(np.nanpercentile(los, 99.5)), 0.0), 1),
                 "max_away_cm": round(max(float(-np.nanpercentile(los, 0.5)), 0.0), 1)}
        stats["max_abs_cm"] = max(stats["max_toward_cm"], stats["max_away_cm"])
        stats["moved_km2"] = round(water.area_km2(np.isfinite(los) & (np.abs(los) > MOVED_CM), target), 1)
        if slow:
            files_out["total"] = f"total_{sec.isoformat()}.png"
            layers.save_ramp(total_at[sec], -tot_max, tot_max, "RdBu", out / files_out["total"])
            files_out["velocity"] = "velocity.png"
            stats["max_total_cm"] = round(float(np.nanpercentile(np.abs(total_at[sec]), 99.5)), 1)
        frames.append({"date": sec.isoformat(), "start": ref.isoformat(), "label": f"{short(ref)} to {pretty(sec)}",
                       "files": files_out, "stats": stats, "sources": sources})

    # Inspector cubes and the place's measured dance.
    factor = layers.series_factor(target.height, target.width)
    red = [layers.reduce_grid(maps[k][0], factor) for k in keys]
    red_sig = [layers.reduce_grid(s, factor) for s in full_sig]
    cum_red, _, _ = _cumulative(keys, red, red_sig, event)
    if cum_red:
        s_dates, s_values, s_sigmas = cum_red
        label = "Total movement since the first pass" + (" (gaps bridged with the average rate)" if bridged else "")
    else:
        s_dates, s_values, s_sigmas, label = [k[1] for k in keys], red, red_sig, "Movement in each pair"
    count, h, w = layers.write_series(out, "series.bin", s_values)
    layers.write_series(out, "sigma.bin", s_sigmas)
    final = np.abs(s_values[-1])
    if np.isfinite(final).any():
        r, c = np.unravel_index(np.nanargmax(final), final.shape)
        t_days = [(d - s_dates[0]).days for d in s_dates]
        place_dance = dance.classify(t_days, [float(v[r, c]) for v in s_values], [float(s[r, c]) for s in s_sigmas],
                                     unit="cm", when=[short(d) for d in s_dates])
    else:
        place_dance = {"dance": "still", "confidence": "low", "reason": "No reliable pixels."}
    place_dance["basis"] = "the spot that moved most"

    manifest_layers = []
    if slow:
        manifest_layers += [
            {"id": "total", "label": "Total so far", "opacity": 0.85,
             "ramp": {"colors": layers.ramp_colours("RdBu"), "min": -tot_max, "max": tot_max, "unit": "cm",
                      "low": "Away from the radar (mostly sinking)", "high": "Toward the radar"},
             "note": "Total line-of-sight movement since the first pass. Press play to watch it build up."},
            {"id": "velocity", "label": "Speed per year", "opacity": 0.85,
             "ramp": {"colors": layers.ramp_colours("RdBu"), "min": -vel_max, "max": vel_max, "unit": "cm",
                      "low": "Moving away each year", "high": "Moving toward each year"},
             "note": "Average rate in cm per year from every pair. Purely vertical sinking would be about 1.3 times this."},
        ]
    manifest_layers += [
        {"id": "displacement", "label": "Movement" if not slow else "Each pair", "opacity": 0.85,
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
                                "note": f"Pixels below {MIN_COHERENCE} coherence are left out of the movement maps."})

    across = [f for f in frames if event and f["start"] < event.isoformat() < f["date"]]
    if across:
        headline = (f"Across the {pretty(event)} earthquakes, the ground moved up to "
                    f"{across[0]['stats']['max_abs_cm']:.0f} cm toward or away from the radar.")
    elif slow:
        headline = (f"The fastest-moving ground here moves about {vel_max:.0f} cm a year along the radar's "
                    f"line of sight, roughly {vel_max * 1.3:.0f} cm a year if it is all sinking.")
    else:
        headline = f"The largest movement in these pairs was {max(f['stats']['max_abs_cm'] for f in frames):.0f} cm."
    right = frames.index(across[0]) if across else len(frames) - 1
    compare = [max(right - 1, 0), right] if across and right > 0 else ([0, min(1, len(frames) - 1)] if across else [0, len(frames) - 1])

    validation = None
    if slow and gnss_dir and Path(gnss_dir).exists():
        validation = gnss.validate(Path(gnss_dir), rate_full * 365.25, target, s_dates[0], s_dates[-1], INCIDENCE_DEG)

    method = [
        "Each interferogram compares two passes 12 days apart; the phase change becomes centimetres along the line of sight.",
        f"Pixels with coherence below {MIN_COHERENCE}, or that the unwrapper could not connect, are left out.",
        "The ionospheric phase screen shipped with each product is subtracted." if iono else "No ionospheric correction was applied.",
        "Movement is measured relative to the median of the scene's outer edge.",
        f"One fringe (colour cycle) equals half the radar wavelength: about {half_wave_cm:.0f} cm.",
    ]
    if bridged:
        method.append("Gaps in the 12-day chain (such as NISAR's instrument gap) are bridged with each pixel's average rate; "
                      "the uncertainty band grows across them.")
    return layers.write_manifest(spot, out, {
        "module": "ground",
        "title": f"{spot['name']}: {'the earthquake' if event else 'the ground on the move'}",
        "headline": headline,
        "synthetic": synthetic,
        "product": "NISAR L2 GUNW (geocoded unwrapped interferograms), HH polarisation",
        "bounds": target.corners_lonlat(),
        "event": event.isoformat() if event else None,
        "frame_noun": "pairs",
        "sides": ["Earlier pair", "Later pair"] if event else ["First pair", "Latest pair"],
        "side_stat": ({"id": "max_total_cm", "label": "Total so far, up to", "unit": "cm"} if slow
                      else {"id": "max_abs_cm", "label": "Largest movement", "unit": "cm"}),
        "compare": compare,
        "layers": manifest_layers,
        "stats": ([{"id": "max_total_cm", "label": "Total so far, up to", "unit": "cm"}] if slow else []) + [
            {"id": "max_toward_cm", "label": "Largest toward", "unit": "cm"},
            {"id": "max_away_cm", "label": "Largest away", "unit": "cm"},
            {"id": "moved_km2", "label": f"Moved over {MOVED_CM:.0f} cm", "unit": "km²"},
        ],
        "chart": ({"area": "max_total_cm", "line": None, "label": "Total movement so far, cm"} if slow
                  else {"area": "max_abs_cm", "line": None, "label": "Largest movement, cm"}),
        "series": {"file": "series.bin", "sigma_file": "sigma.bin", "count": count, "width": w, "height": h,
                   "factor": factor, "full_width": target.width, "full_height": target.height,
                   "dates": [d.isoformat() for d in s_dates], "label": label, "unit": "cm"},
        "dance": place_dance,
        "validation": validation,
        "bridged": bridged,
        "method": method,
        "frames": frames,
    })


# ---------------------------------------------------------------- synthetic sinking city

def make_subsidence_pairs(spot, out_dir, rate_cm_yr=30.0, spacing=150.0):
    """SYNTHETIC GUNW pairs over a city sinking in a bowl, plus SYNTHETIC GNSS stations to check against."""
    import h5py
    from datetime import timedelta
    from rasterio.warp import transform, transform_bounds
    from scipy import ndimage

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    epsg = 32614                                               # UTM 14N covers Mexico City
    west, south, east, north = spot["bbox"]
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{epsg}", west, south, east, north)
    xs = np.arange(x0 - 3000, x1 + 3000, spacing)
    ys = np.arange(y1 + 3000, y0 - 3000, -spacing)
    gx, gy = np.meshgrid(xs, ys)
    (cx,), (cy,) = transform("EPSG:4326", f"EPSG:{epsg}", [spot["lon"] + 0.02], [spot["lat"] - 0.03])
    r2 = ((gx - cx) / 9000) ** 2 + ((gy - cy) / 7000) ** 2
    bowl = np.exp(-r2) + 0.45 * np.exp(-(((gx - cx - 12000) / 5000) ** 2 + ((gy - cy + 9000) / 4000) ** 2))
    vertical_rate = -rate_cm_yr * bowl / bowl.max()            # cm/yr, negative = sinking
    los_rate = vertical_rate * np.cos(np.radians(INCIDENCE_DEG))  # sinking moves the ground away from the radar

    rng = np.random.default_rng(11)
    wavelength = nisar_io.SPEED_OF_LIGHT / nisar_io.DEFAULT_CENTER_FREQUENCY
    passes = [date(2026, 6, 19) + timedelta(days=12 * i) for i in range(9)]
    passes = [d for d in passes if not date(2026, 7, 27) <= d <= date(2026, 8, 10)]
    written = []
    for ref, sec in zip(passes, passes[1:]):
        if (sec - ref).days != 12:
            continue                                            # NISAR makes 12-day pairs only
        los_m = los_rate * 12 / 365.25 / 100
        atmosphere = ndimage.gaussian_filter(rng.standard_normal(gx.shape), 25)
        los_m = los_m + atmosphere / np.abs(atmosphere).max() * 0.0012 + rng.normal(0, 0.0015, gx.shape)
        phase = -(4 * np.pi / wavelength) * los_m
        coherence = np.clip(rng.normal(0.6, 0.12, gx.shape), 0, 1)
        stamps = [f"{d:%Y%m%d}T010000_{d:%Y%m%d}T010040" for d in (ref, sec)]
        path = out_dir / f"SYNTHETIC_NISAR_L2_PR_GUNW_DEMO_{stamps[0]}_{stamps[1]}_DEMO.h5"
        with h5py.File(path, "w") as f:
            grid = f.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram")
            grid["xCoordinates"], grid["yCoordinates"] = xs, ys
            proj = grid.create_dataset("projection", data=np.int32(epsg))
            proj.attrs["epsg_code"] = np.int32(epsg)
            hh = grid.create_group("HH")
            hh["unwrappedPhase"] = phase.astype("float32")
            hh["coherenceMagnitude"] = coherence.astype("float32")
            hh["connectedComponents"] = (coherence >= 0.3).astype("uint8")
        written.append(path)

    stations = out_dir / "gnss"
    stations.mkdir(exist_ok=True)
    for i, (lon, lat) in enumerate([(spot["lon"] + 0.02, spot["lat"] - 0.03), (spot["lon"] - 0.08, spot["lat"] + 0.05),
                                    (spot["lon"] + 0.13, spot["lat"] - 0.1)]):
        (sx,), (sy,) = transform("EPSG:4326", f"EPSG:{epsg}", [lon], [lat])
        row = int(np.clip((ys[0] - sy) / spacing, 0, len(ys) - 1)); col = int(np.clip((sx - xs[0]) / spacing, 0, len(xs) - 1))
        gnss.write_synthetic_tenv3(stations / f"SYN{i + 1}.tenv3", f"SYN{i + 1}", lon, lat,
                                   vertical_rate[row, col] / 100, passes[0], passes[-1], rng)
    return written, stations
