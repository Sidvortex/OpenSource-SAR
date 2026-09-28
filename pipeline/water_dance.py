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
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

import coverage_check as cc
import nisar_io
import water

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WORK = ROOT / "pipeline" / "work"
WATER_RGBA = (31, 143, 209, 215)       # open water, the module's radar blue
VEG_RGBA = (55, 194, 176, 205)         # likely flooded vegetation, teal
RADAR_RANGE_DB = (-25.0, 0.0)


def load_spot(spot_id):
    spots = json.loads((DATA / "hotspots.json").read_text())["hotspots"]
    for spot in spots:
        if spot["id"] == spot_id:
            return spot
    sys.exit(f"No hotspot called {spot_id!r}. Choose one of: {', '.join(s['id'] for s in spots)}")


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

def radar_png(hh_db, path):
    lo, hi = RADAR_RANGE_DB
    grey = np.clip((hh_db - lo) / (hi - lo), 0, 1)
    valid = np.isfinite(hh_db)
    la = np.zeros(hh_db.shape + (2,), dtype="uint8")          # grey + alpha: half the size of RGBA
    la[..., 0] = np.where(valid, grey * 255, 0).astype("uint8")
    la[..., 1] = np.where(valid, 255, 0)
    # WebP keeps transparency and shrinks speckled radar images several-fold compared with PNG.
    Image.fromarray(la, mode="LA").convert("RGBA").save(path, "WEBP", quality=78, method=6)


def water_png(open_water, veg, path):
    rgba = np.zeros(open_water.shape + (4,), dtype="uint8")
    rgba[open_water] = WATER_RGBA
    rgba[veg] = VEG_RGBA
    Image.fromarray(rgba).save(path, optimize=True)


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
    out = DATA / "layers" / spot["id"]
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob("*.png")) + list(out.glob("*.webp")):
        old.unlink()
    dates = []
    for day in sorted(masks):
        open_water, veg, threshold = masks[day]
        stamp = day.isoformat()
        water_png(open_water, veg, out / f"water_{stamp}.png")
        radar_png(hh_db[day], out / f"radar_{stamp}.webp")
        dates.append({
            "date": stamp,
            "water": f"water_{stamp}.png",
            "radar": f"radar_{stamp}.webp",
            "open_water_km2": round(water.area_km2(open_water, target), 1),
            "flooded_veg_km2": round(water.area_km2(veg, target), 1),
            "threshold_db": round(threshold, 1),
            "sources": sources[day],
        })
    manifest = {
        "hotspot": spot["id"],
        "module": "water",
        "title": f"{spot['name']}: the water dance",
        "synthetic": synthetic,
        "created": date.today().isoformat(),
        "product": "NISAR L2 GCOV (terrain-corrected backscatter), HH polarisation",
        "grid": {"crs": water.WEB_CRS, "resolution_m": res, "width": target.width, "height": target.height},
        "bounds": target.corners_lonlat(),
        "reference_date": reference.isoformat(),
        "method": [
            "Each pass is averaged onto one shared grid, so dates line up pixel for pixel.",
            "Open water: HH backscatter below a per-pass Otsu threshold, kept between -24 and -14 dB.",
            f"Likely flooded vegetation: HH at least 3 dB brighter than on the driest pass ({reference.isoformat()}) and brighter than -8 dB.",
            "Areas are true areas, corrected for map-projection stretch.",
        ],
        "legend": [
            {"id": "open_water", "label": "Open water", "color": "#%02x%02x%02x" % WATER_RGBA[:3]},
            {"id": "flooded_veg", "label": "Likely flooded vegetation", "color": "#%02x%02x%02x" % VEG_RGBA[:3]},
        ],
        "dates": dates,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    update_index(spot["id"], "water", synthetic)
    print(f"Wrote {len(dates)} dates to {out.relative_to(ROOT)}")
    return manifest


def update_index(spot_id, module, synthetic):
    """data/layers/index.json tells the site which places have layers, without guessing URLs."""
    path = DATA / "layers" / "index.json"
    index = json.loads(path.read_text()) if path.exists() else {"layers": {}}
    index["layers"][spot_id] = {"module": module, "synthetic": synthetic, "updated": date.today().isoformat()}
    path.write_text(json.dumps(index, indent=2) + "\n")


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
