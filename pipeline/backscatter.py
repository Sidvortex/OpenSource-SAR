#!/usr/bin/env python3
"""
Part 7: fire and farming from NISAR GCOV cross-polarised (HV) backscatter.

HV comes mostly from volume scattering in leaves, stems and branches:
  * Fire and clearing remove that structure, so HV drops by several dB and stays low.
  * Crops grow a canopy, so HV rises through the season and falls at harvest.

    python pipeline/backscatter.py demo --hotspot amazon-arc        # synthetic fire demo, labelled
    python pipeline/backscatter.py demo --hotspot punjab-haryana    # synthetic farming demo, labelled
    python pipeline/backscatter.py process --hotspot amazon-arc     # real GCOV files (download with water_dance.py)
"""
import argparse
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from scipy import ndimage

import dance
import layers
import nisar_io
import water
from layers import WORK, load_spot

BURN_DROP_DB = -3.0
GROWING_DB = 4.0
EMBER, OLD_BURN = (224, 85, 43, 225), (122, 30, 18, 200)
hexc = lambda c: "#%02x%02x%02x" % c[:3]
short = lambda d: f"{d:%b} {d.day}"


def hv_from_files(spot, files, target):
    by_date, sources = defaultdict(list), defaultdict(list)
    for path in sorted(files):
        grid = nisar_io.read_crop(path, spot["bbox"], polarisations=("HV", "HH"))
        if grid is None:
            continue
        bands = water.to_target(grid, target)
        by_date[grid.acquired].append(bands.get("HV", bands.get("HH")))
        sources[grid.acquired].append(Path(path).name)
    with np.errstate(invalid="ignore"):
        return {d: water.to_db(np.nanmean(np.stack(v), axis=0)) for d, v in by_date.items()}, sources


def _common(spot, target, days, hv, series_label, sigma, place_values, place_unit, place_basis):
    factor = layers.series_factor(target.height, target.width)
    out = layers.DATA / "layers" / spot["id"]
    count, h, w = layers.write_series(out, "series.bin", [layers.reduce_grid(hv[d], factor) for d in days])
    t = [(d - days[0]).days for d in days]
    place = dance.classify(t, place_values, 0.03 * max(float(np.max(np.abs(place_values))), 1e-6), unit=place_unit,
                           when=[short(d) for d in days])
    place["basis"] = place_basis
    series = {"file": "series.bin", "count": count, "width": w, "height": h, "factor": factor,
              "full_width": target.width, "full_height": target.height, "dates": [d.isoformat() for d in days],
              "label": series_label, "unit": "dB", "sigma": sigma}
    return series, place


def build_fire(spot, target, hv, synthetic, sources):
    days = sorted(hv)
    out = layers.layer_folder(spot["id"])
    baseline = np.nanmedian(np.stack([hv[d] for d in days[:2]]), axis=0)
    first_burn = np.full(baseline.shape, np.datetime64("NaT"), dtype="datetime64[D]")
    previous = np.zeros(baseline.shape, dtype=bool)
    frames, burned_series = [], []
    for d in days:
        drop = ndimage.median_filter(hv[d] - baseline, size=3) <= BURN_DROP_DB
        confirmed = drop & previous                                # low on two passes in a row: not just a wet day
        newly = confirmed & np.isnat(first_burn)
        first_burn[newly] = np.datetime64(d)
        earlier = ~np.isnat(first_burn) & ~newly
        previous = drop
        stamp = d.isoformat()
        layers.save_classes({"old": earlier, "new": newly}, {"old": OLD_BURN, "new": EMBER}, out / f"burn_{stamp}.png")
        layers.save_ramp(hv[d], -30, -8, "gray", out / f"radar_{stamp}.webp", webp=True)
        total = water.area_km2(~np.isnat(first_burn), target)
        burned_series.append(total)
        frames.append({"date": stamp, "label": stamp, "files": {"burn": f"burn_{stamp}.png", "radar": f"radar_{stamp}.webp"},
                       "stats": {"burned_km2": round(total, 1), "new_km2": round(water.area_km2(newly, target), 1)},
                       "sources": sources.get(d, [])})
    series, place = _common(spot, target, days, hv, "Cross-polarised (HV) radar brightness", 0.7, burned_series, "km²", "total burned area")
    return layers.write_manifest(spot, out, {
        "module": "fire", "title": f"{spot['name']}: fire and forest loss",
        "headline": f"Radar mapped about {burned_series[-1]:,.0f} km² of new burn scars and clearings, seen through cloud and smoke.",
        "synthetic": synthetic, "product": "NISAR L2 GCOV (terrain-corrected backscatter), HV polarisation",
        "bounds": target.corners_lonlat(), "event": None, "frame_noun": "passes", "sides": ["Before", "After"],
        "side_stat": {"id": "burned_km2", "label": "Burned or cleared", "unit": "km²"},
        "layers": [
            {"id": "burn", "label": "Burn scars", "opacity": 0.9,
             "legend": [{"label": "New this pass", "color": hexc(EMBER)}, {"label": "Earlier", "color": hexc(OLD_BURN)}]},
            {"id": "radar", "label": "Radar image", "opacity": 0.9,
             "ramp": {"colors": layers.ramp_colours("gray"), "min": -30, "max": -8, "unit": "dB",
                      "low": "Dark: bare or burned", "high": "Bright: standing forest"}},
        ],
        "stats": [{"id": "burned_km2", "label": "Burned or cleared", "unit": "km²", "color": hexc(EMBER)},
                  {"id": "new_km2", "label": "New this pass", "unit": "km²"}],
        "chart": {"area": "burned_km2", "line": None, "label": "Burned or cleared, km²"},
        "series": series, "dance": place,
        "method": ["Baseline: the median HV brightness of the first two passes.",
                   f"A pixel counts as burned or cleared when HV falls {abs(BURN_DROP_DB):.0f} dB or more below its baseline "
                   "on two passes in a row, so one wet day can't fake a fire.",
                   "Cross-check with NASA FIRMS active-fire detections (Part 7 event markers)."],
        "frames": frames,
    })


def build_farming(spot, target, hv, synthetic, sources):
    days = sorted(hv)
    out = layers.layer_folder(spot["id"])
    bare = np.nanmin(np.stack([hv[d] for d in days]), axis=0)
    frames, medians = [], []
    for d in days:
        growth = hv[d] - bare
        stamp = d.isoformat()
        layers.save_ramp(np.clip(growth, 0, 9), 0, 9, "YlGn", out / f"growth_{stamp}.webp", webp=True)
        layers.save_ramp(hv[d], -28, -10, "gray", out / f"radar_{stamp}.webp", webp=True)
        growing = np.isfinite(growth) & (growth > GROWING_DB)
        share = 100 * growing.sum() / max(np.isfinite(growth).sum(), 1)
        medians.append(float(np.nanmedian(hv[d])))
        frames.append({"date": stamp, "label": stamp, "files": {"growth": f"growth_{stamp}.webp", "radar": f"radar_{stamp}.webp"},
                       "stats": {"growing_pct": round(share, 1), "median_hv_db": round(medians[-1], 1)}, "sources": sources.get(d, [])})
    series, place = _common(spot, target, days, hv, "Cross-polarised (HV) radar brightness", 0.7, medians, "dB", "the median field")
    peak = max(frames, key=lambda f: f["stats"]["growing_pct"])
    return layers.write_manifest(spot, out, {
        "module": "farming", "title": f"{spot['name']}: the farming season",
        "headline": f"At the season's peak ({peak['date']}), {peak['stats']['growing_pct']:.0f}% of the land showed a full crop canopy.",
        "synthetic": synthetic, "product": "NISAR L2 GCOV (terrain-corrected backscatter), HV polarisation",
        "bounds": target.corners_lonlat(), "event": None, "frame_noun": "passes", "sides": ["Before", "After"],
        "side_stat": {"id": "growing_pct", "label": "Full canopy", "unit": "%"},
        "layers": [
            {"id": "growth", "label": "Crop growth", "opacity": 0.85,
             "ramp": {"colors": layers.ramp_colours("YlGn"), "min": 0, "max": 9, "unit": "dB",
                      "low": "Bare soil", "high": "Full canopy"},
             "note": "How much brighter each spot is than its own barest moment this season."},
            {"id": "radar", "label": "Radar image", "opacity": 0.9,
             "ramp": {"colors": layers.ramp_colours("gray"), "min": -28, "max": -10, "unit": "dB",
                      "low": "Dark: bare or flooded", "high": "Bright: dense crops"}},
        ],
        "stats": [{"id": "growing_pct", "label": "Full canopy", "unit": "%"},
                  {"id": "median_hv_db", "label": "Median HV", "unit": "dB"}],
        "chart": {"area": "growing_pct", "line": None, "label": "Share of land in full canopy, %"},
        "series": series, "dance": place,
        "method": ["Crop growth: HV brightness above each pixel's own minimum this season.",
                   f"'Full canopy' means more than {GROWING_DB:.0f} dB above that minimum.",
                   "Rice paddies show a dark dip when flooded for planting, then a steady rise."],
        "frames": frames,
    })


# ---------------------------------------------------------------- synthetic demos

def _demo_days():
    days = [date(2026, 6, 19) + timedelta(days=12 * i) for i in range(9)]
    return [d for d in days if not date(2026, 7, 27) <= d <= date(2026, 8, 10)]


def demo_hv(spot, target, kind):
    rng = np.random.default_rng(5)
    shape = (target.height, target.width)
    smooth = lambda s: ndimage.gaussian_filter(rng.standard_normal(shape), s)
    days = _demo_days()
    hv = {}
    if kind == "fire":
        forest = smooth(40) > -0.02
        base = np.where(forest, -12.0, -19.0)
        patches = [(smooth(18) > 0.05) & forest for _ in range(3)]
        starts = [3, 5, 6]
        for i, d in enumerate(days):
            v = base.copy()
            for patch, s in zip(patches, starts):
                if i >= s:
                    v[patch] = -19.5
            hv[d] = v + rng.normal(0, 0.8, shape)
    else:
        rows, cols = np.indices(shape)
        field = (rows // 12) * 1000 + cols // 12                  # fields about 1.8 km across
        noise = np.sin(field * 12.9898) * 43758.5453 % 1
        offset = noise * 20                                        # each field planted on its own day
        amplitude = np.where(noise < 0.25, 0.0, 6 + 3 * noise)     # a quarter of fields left fallow
        for d in days:
            t = (d - days[0]).days - offset
            canopy = amplitude * np.exp(-((t - 42) / 20.0) ** 2)    # rise, peak, harvest
            flooded = (t > 5) & (t < 18)
            hv[d] = -24 + canopy - 3 * flooded + rng.normal(0, 0.8, shape)
    return hv, {d: ["SYNTHETIC demo, not a NISAR product"] for d in days}


def main():
    parser = argparse.ArgumentParser(description="SARabande Part 7: fire and farming from HV backscatter.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "process"):
        p = sub.add_parser(name)
        p.add_argument("--hotspot", required=True)
        p.add_argument("--mode", choices=["fire", "farming"], help="default: the hotspot's module")
        p.add_argument("--res", type=float, help="grid size in Mercator metres (default: 150, or 300 for big areas)")
        p.add_argument("--work")
    args = parser.parse_args()
    spot = load_spot(args.hotspot)
    mode = args.mode or spot["module"]
    if mode not in ("fire", "farming"):
        sys.exit(f"{spot['id']} is a {spot['module']} hotspot; use --mode fire or --mode farming.")
    span = max(spot["bbox"][2] - spot["bbox"][0], spot["bbox"][3] - spot["bbox"][1])
    target = water.target_grid(spot["bbox"], res=args.res or (300.0 if span > 1.2 else 150.0))
    if args.command == "demo":
        print("Building SYNTHETIC demo layers (not NISAR measurements)...")
        hv, sources = demo_hv(spot, target, mode)
        synthetic = True
    else:
        folder = Path(args.work) if args.work else WORK / spot["id"]
        files = sorted(folder.glob("*.h5"))
        if not files:
            sys.exit(f"No .h5 files in {folder}. Download GCOV with: python pipeline/water_dance.py download --hotspot {spot['id']}")
        hv, sources = hv_from_files(spot, files, target)
        synthetic = any(f.name.startswith("SYNTHETIC_") for f in files)
    (build_fire if mode == "fire" else build_farming)(spot, target, hv, synthetic, sources)


if __name__ == "__main__":
    main()
