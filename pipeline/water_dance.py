#!/usr/bin/env python3
"""
Part 2: turn NISAR GCOV products into the water-dance layers the site shows.

    python pipeline/water_dance.py demo --hotspot tonle-sap        # synthetic, labelled, no download
    python pipeline/water_dance.py download --hotspot tonle-sap    # needs a free Earthdata login
    python pipeline/water_dance.py process --hotspot tonle-sap     # real layers into data/layers/
    python pipeline/water_dance.py inspect path/to/product.h5      # print the file's layout

Downloads use a free NASA Earthdata login: set EARTHDATA_TOKEN, or
EARTHDATA_USERNAME and EARTHDATA_PASSWORD, in your environment.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import coverage_check as cc
import dance
import layers
import nisar_io
import water
from layers import ROOT, WORK, load_spot

WATER_RGBA = (31, 143, 209, 215)       # open water, the module's radar blue
VEG_RGBA = (55, 194, 176, 205)         # likely flooded vegetation, teal
RADAR_RANGE_DB = (-25.0, 0.0)
hexcolour = lambda rgba: "#%02x%02x%02x" % rgba[:3]


# ---------------------------------------------------------------- download

def earthdata_session():
    import asf_search as asf
    token = os.environ.get("EARTHDATA_TOKEN")
    user, password = os.environ.get("EARTHDATA_USERNAME"), os.environ.get("EARTHDATA_PASSWORD")
    if token:
        return asf.ASFSession().auth_with_token(token)
    if user and password:
        return asf.ASFSession().auth_with_creds(user, password)
    sys.exit("Downloading needs a free NASA Earthdata login. Set EARTHDATA_TOKEN, or "
             "EARTHDATA_USERNAME and EARTHDATA_PASSWORD. Register at urs.earthdata.nasa.gov.")


def cmd_download(args):
    spot = load_spot(args.hotspot)
    west, south, east, north = spot["bbox"]
    area = {"label": spot["name"], "wkt": cc.bbox(west, south, east, north),
            "start": args.start, "end": args.end}
    results = cc.search("GCOV", area, args.maturity, include_ur=False)
    rows = [(r, cc.to_row(spot["id"], "GCOV", args.maturity, r)) for r in results]
    if not rows:
        sys.exit("No GCOV products found for this area and time. Run update_coverage.py to check.")
    stacks = defaultdict(list)
    for result, row in rows:
        stacks[(row["track"], row["frame"], row["direction"])].append((result, row))
    best_key = max(stacks, key=lambda k: len({row["date"] for _, row in stacks[k]}))
    chosen = sorted(stacks[best_key], key=lambda pair: pair[1]["date"])[-args.max:]
    size = sum(row["size_gb"] for _, row in chosen)
    print(f"Best stack: track {best_key[0]}, frame {best_key[1]}, {best_key[2]}; "
          f"downloading {len(chosen)} products, about {size:.1f} GB.")
    out = WORK / spot["id"]
    out.mkdir(parents=True, exist_ok=True)
    session = earthdata_session()
    for result, row in chosen:
        print(f"  {row['date']}  {row['scene']}")
        result.download(path=str(out), session=session)
    print(f"Saved to {out}. Next: python pipeline/water_dance.py process --hotspot {spot['id']}")


# ---------------------------------------------------------------- process

def build_layers(spot, files, synthetic, res):
    target = water.target_grid(spot["bbox"], res=res)
    by_date = defaultdict(list)
    for path in sorted(files):
        grid = nisar_io.read_crop(path, spot["bbox"])
        if grid is None:
            print(f"  skipped (outside the area): {Path(path).name}")
            continue
        by_date[grid.acquired].append((water.to_target(grid, target), Path(path).name))
        print(f"  read {grid.acquired}  {Path(path).name}")
    if len(by_date) < 2:
        sys.exit("Need at least two dates to show change.")

    hh_db, sources = {}, {}
    for day, items in sorted(by_date.items()):
        pol = "HH" if "HH" in items[0][0] else "VV"
        stack = np.stack([bands[pol] for bands, _ in items])
        with np.errstate(invalid="ignore"):
            mosaic = np.nanmean(stack, axis=0)       # adjacent frames on the same day
        hh_db[day] = water.to_db(mosaic)
        sources[day] = [name for _, name in items]

    masks, reference = water.water_masks(hh_db)
    out = layers.layer_folder(spot["id"])
    frames = []
    for day in sorted(masks):
        open_water, veg, threshold = masks[day]
        stamp = day.isoformat()
        layers.save_classes({"open": open_water, "veg": veg}, {"open": WATER_RGBA, "veg": VEG_RGBA}, out / f"water_{stamp}.png")
        layers.save_ramp(hh_db[day], *RADAR_RANGE_DB, "gray", out / f"radar_{stamp}.webp", webp=True)
        open_km2, veg_km2 = water.area_km2(open_water, target), water.area_km2(veg, target)
        frames.append({
            "date": stamp,
            "label": stamp,
            "files": {"water": f"water_{stamp}.png", "radar": f"radar_{stamp}.webp"},
            "stats": {"open_water_km2": round(open_km2, 1), "flooded_veg_km2": round(veg_km2, 1),
                      "water_total_km2": round(open_km2 + veg_km2, 1), "threshold_db": round(threshold, 1)},
            "sources": sources[day],
        })
    first, last = frames[0], frames[-1]
    # Part 4: every pixel's history for the inspector, and the place's measured dance.
    days = sorted(masks)
    factor = layers.series_factor(target.height, target.width)
    count, h, w = layers.write_series(out, "series.bin", [layers.reduce_grid(hh_db[d], factor) for d in days])
    thresholds = [masks[d][2] for d in days]
    totals = [f["stats"]["water_total_km2"] for f in frames]
    t_days = [(d - days[0]).days for d in days]
    place_dance = dance.classify(t_days, totals, 0.02 * float(np.median(totals)), unit="km²",
                                 when=[f"{d:%b} {d.day}" for d in days])
    place_dance["basis"] = "total water area"
    return layers.write_manifest(spot, out, {
        "module": "water",
        "title": f"{spot['name']}: the water dance",
        "headline": (f"Open water grew from {first['stats']['open_water_km2']:,.0f} km² to "
                     f"{last['stats']['open_water_km2']:,.0f} km² between the first and last pass."),
        "synthetic": synthetic,
        "product": "NISAR L2 GCOV (terrain-corrected backscatter), HH polarisation",
        "bounds": target.corners_lonlat(),
        "event": spot.get("event"),
        "frame_noun": "passes",
        "sides": ["Before", "After"],
        "side_stat": {"id": "open_water_km2", "label": "Open water", "unit": "km²"},
        "layers": [
            {"id": "water", "label": "Water map", "opacity": 0.85,
             "legend": [{"label": "Open water", "color": hexcolour(WATER_RGBA)},
                        {"label": "Likely flooded vegetation", "color": hexcolour(VEG_RGBA)}]},
            {"id": "radar", "label": "Radar image", "opacity": 0.9,
             "ramp": {"colors": layers.ramp_colours("gray"), "min": RADAR_RANGE_DB[0], "max": RADAR_RANGE_DB[1], "unit": "dB",
                      "low": "Dark: smooth water", "high": "Bright: rough ground or flooded forest"}},
        ],
        "stats": [
            {"id": "open_water_km2", "label": "Open water", "unit": "km²", "color": hexcolour(WATER_RGBA)},
            {"id": "flooded_veg_km2", "label": "Flooded vegetation", "unit": "km²", "color": hexcolour(VEG_RGBA)},
        ],
        "chart": {"area": "water_total_km2", "line": "open_water_km2", "label": "Water, km²"},
        "series": {"file": "series.bin", "count": count, "width": w, "height": h, "factor": factor,
                   "full_width": target.width, "full_height": target.height,
                   "dates": [d.isoformat() for d in days], "label": "Radar brightness", "unit": "dB",
                   "sigma": 0.6, "threshold": round(float(np.median(thresholds)), 1),
                   "threshold_label": "Below the dashed line counts as open water"},
        "dance": place_dance,
        "method": [
            "Each pass is averaged onto one shared grid, so dates line up pixel for pixel.",
            "Open water: HH backscatter below a per-pass Otsu threshold, kept between -24 and -14 dB.",
            f"Likely flooded vegetation: HH at least 3 dB brighter than on the driest pass ({reference.isoformat()}) and brighter than -8 dB.",
            "Areas are true areas, corrected for map-projection stretch.",
        ],
        "frames": frames,
    })


def cmd_process(args):
    spot = load_spot(args.hotspot)
    folder = Path(args.work) if args.work else WORK / spot["id"]
    files = sorted(folder.glob("*.h5"))
    if not files:
        sys.exit(f"No .h5 files in {folder}. Run the download command first.")
    synthetic = any(f.name.startswith("SYNTHETIC_") for f in files)
    build_layers(spot, files, synthetic, args.res)


def cmd_demo(args):
    spot = load_spot(args.hotspot)
    lake = ROOT / "pipeline" / "assets" / "tonle_sap_lake.geojson"
    if spot["id"] != "tonle-sap":
        sys.exit("The synthetic demo is built for tonle-sap (it grows the real lake outline).")
    folder = WORK / f"demo-{spot['id']}"
    print("Writing SYNTHETIC demo products (not NISAR measurements)...")
    files = water.make_demo_products(spot, lake, folder)
    build_layers(spot, files, synthetic=True, res=args.res)


def cmd_inspect(args):
    for line in nisar_io.list_tree(args.file):
        print(line)


def main():
    parser = argparse.ArgumentParser(description="SARabande Part 2: the water dance.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("download", help="download the best GCOV stack for a hotspot")
    p.add_argument("--hotspot", default="tonle-sap")
    p.add_argument("--start", default=cc.PROVISIONAL_START)
    p.add_argument("--end")
    p.add_argument("--max", type=int, default=12, help="most recent N products")
    p.add_argument("--maturity", default="PROVISIONAL", choices=["PROVISIONAL", "BETA"])
    p.set_defaults(func=cmd_download)
    p = sub.add_parser("process", help="build web layers from downloaded .h5 files")
    p.add_argument("--hotspot", default="tonle-sap")
    p.add_argument("--work", help="folder of .h5 files (default pipeline/work/<hotspot>)")
    p.add_argument("--res", type=float, default=150.0, help="web grid size in Mercator metres")
    p.set_defaults(func=cmd_process)
    p = sub.add_parser("demo", help="synthetic, clearly labelled demo layers; no download")
    p.add_argument("--hotspot", default="tonle-sap")
    p.add_argument("--res", type=float, default=150.0)
    p.set_defaults(func=cmd_demo)
    p = sub.add_parser("inspect", help="print the datasets inside an HDF5 product")
    p.add_argument("file")
    p.set_defaults(func=cmd_inspect)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
