#!/usr/bin/env python3
"""
Real-data smoke test: download ONE real NISAR product per type and run our reader on it.

    export EARTHDATA_USERNAME=you EARTHDATA_PASSWORD=secret     # free login, or EARTHDATA_TOKEN
    python pipeline/smoke_test.py                 # GCOV, GUNW and GOFF
    python pipeline/smoke_test.py --products GCOV

It picks the smallest product it can find over a hero place, so it downloads as
little as possible, then prints PASS or FAIL per product with the file's layout
when something doesn't match. Paste the output to the team: a FAIL usually needs
one dataset name adding to the lists at the top of pipeline/nisar_io.py.
"""
import argparse
import sys
import traceback

import coverage_check as cc
import ice
import layers
import nisar_io
from water_dance import earthdata_session

PLACES = {"GCOV": "tonle-sap", "GUNW": "venezuela-coast", "GOFF": "shisper"}
READERS = {
    "GCOV": lambda path, spot: nisar_io.read_crop(path, spot["bbox"]),
    "GUNW": lambda path, spot: nisar_io.read_gunw_crop(path, spot["bbox"]),
    "GOFF": lambda path, spot: ice.read_goff_crop(path, spot["bbox"]),
}


def smallest(product, spot):
    west, south, east, north = spot["bbox"]
    window = spot.get("window", {})
    area = {"label": spot["name"], "wkt": cc.bbox(west, south, east, north),
            "start": window.get("start", cc.PROVISIONAL_START), "end": window.get("end")}
    results = list(cc.search(product, area, "PROVISIONAL", include_ur=False))
    if not results:
        return None
    size = lambda r: sum(v.get("bytes", 0) for v in (r.properties.get("bytes") or {}).values() if isinstance(v, dict))
    return min(results, key=size)


def check(product, session):
    spot = layers.load_spot(PLACES[product])
    result = smallest(product, spot)
    if result is None:
        return "SKIP", f"no PROVISIONAL {product} products over {spot['name']} yet"
    folder = layers.WORK / "smoke" / product
    folder.mkdir(parents=True, exist_ok=True)
    print(f"  downloading {result.properties.get('sceneName')} ...")
    result.download(path=str(folder), session=session)
    files = sorted(folder.glob("*.h5"))
    if not files:
        return "FAIL", "download produced no .h5 file"
    path = files[-1]
    try:
        out = READERS[product](path, spot)
    except Exception:
        tree = "\n".join(nisar_io.list_tree(path)[:60])
        return "FAIL", f"{traceback.format_exc(limit=2)}\nFile layout (first 60 datasets):\n{tree}"
    if out is None:
        return "FAIL", "the reader found no overlap with the place's box; check the box or the product's grid"
    return "PASS", f"read {path.name}"


def main():
    parser = argparse.ArgumentParser(description="Download one real product per type and test our readers.")
    parser.add_argument("--products", nargs="+", default=list(PLACES), choices=list(PLACES))
    args = parser.parse_args()
    session = earthdata_session()
    failed = 0
    for product in args.products:
        print(f"\n== {product} over {PLACES[product]}")
        status, detail = check(product, session)
        failed += status == "FAIL"
        print(f"{status}: {detail}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
