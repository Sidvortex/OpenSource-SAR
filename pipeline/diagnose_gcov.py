#!/usr/bin/env python3
"""
Look inside downloaded GCOV files to see why a place's radar layer is mostly empty.

    python pipeline/diagnose_gcov.py --hotspot tonle-sap

Reads only files already in pipeline/work/<place>/ (no downloads). For each file it
prints where the product's grid lies compared with the place's box, what the raw
backscatter values look like, and how much of the place it actually covers.
"""
import argparse
import sys

import h5py
import numpy as np
from rasterio.warp import transform, transform_bounds

import layers
import nisar_io
import water


def describe(path, spot):
    print(f"\n== {path.name}")
    with h5py.File(path, "r") as f:
        group = nisar_io._find_grid_group(f)
        epsg = nisar_io._epsg(group)
        x = np.asarray(nisar_io._first(group, nisar_io.X_NAMES)[()], dtype="float64")
        y = np.asarray(nisar_io._first(group, nisar_io.Y_NAMES)[()], dtype="float64")
        print(f"grid group: {group.name}   EPSG:{epsg}")
        print(f"x: {x[0]:.1f} .. {x[-1]:.1f}  step {x[1] - x[0]:.2f}  ({x.size} columns)")
        print(f"y: {y[0]:.1f} .. {y[-1]:.1f}  step {y[1] - y[0]:.2f}  ({y.size} rows)")
        west, south, east, north = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *spot["bbox"], densify_pts=21)
        print(f"place box in EPSG:{epsg}: x {west:.1f} .. {east:.1f}, y {south:.1f} .. {north:.1f}")
        for key in ("science/LSAR/identification/boundingPolygon", "science/LSAR/identification/lookDirection",
                    "science/LSAR/identification/orbitPassDirection", "science/LSAR/identification/listOfFrequencies"):
            if key in f:
                v = f[key][()]
                v = v.decode() if isinstance(v, bytes) else v
                print(f"{key.rsplit('/', 1)[-1]}: {str(v)[:300]}")
        name = next((n for n in nisar_io.POLARISATIONS["HH"] if n in group), None)
        if name is None:
            print("no HHHH dataset; datasets in the grid group:", ", ".join(k for k in group.keys())[:400])
            return
        ds = group[name]
        print(f"{name}: shape {ds.shape}, dtype {ds.dtype}, chunks {ds.chunks}, attrs "
              + ", ".join(f"{k}={np.asarray(v).ravel()[:3]}" for k, v in ds.attrs.items())[:300])
        if "mask" in group:
            print(f"mask dataset present: shape {group['mask'].shape}, dtype {group['mask'].dtype}")

        xr = nisar_io._index_range(x, west, east)
        yr = nisar_io._index_range(y, south, north)
        if xr is None or yr is None:
            print("the product's grid does not overlap the place's box at all")
            return
        print(f"overlap: columns {xr[0]}..{xr[1]} of {x.size}, rows {yr[0]}..{yr[1]} of {y.size} "
              f"(that is {(xr[1] - xr[0]) * (yr[1] - yr[0]) / ((east - west) / abs(x[1] - x[0]) * (north - south) / abs(y[1] - y[0])):.0%} of the box's area)")

        step = max(1, int(max(yr[1] - yr[0], xr[1] - xr[0]) // 1500))   # sample, so this stays quick
        raw = ds[yr[0]:yr[1]:step, xr[0]:xr[1]:step].astype("float64")
        n = raw.size
        finite = np.isfinite(raw)
        pos = finite & (raw > 0)
        print(f"raw HH values in the overlap (every {step}th pixel, {n:,} sampled): "
              f"{np.mean(~finite):.0%} NaN, {np.mean(finite & (raw == 0)):.0%} exactly 0, "
              f"{np.mean(finite & (raw < 0)):.0%} negative, {np.mean(pos):.0%} positive")
        if pos.any():
            db = 10 * np.log10(raw[pos])
            print("positive values in dB, 1st/5th/25th/50th/75th/95th/99th percentile: "
                  + " / ".join(f"{v:.1f}" for v in np.percentile(db, [1, 5, 25, 50, 75, 95, 99])))
            print(f"share of positive values below -30 dB: {np.mean(db < -30):.0%}, below -50 dB: {np.mean(db < -50):.0%}")

        lon, lat = spot["lon"], spot["lat"]
        (cx,), (cy,) = transform("EPSG:4326", f"EPSG:{epsg}", [lon], [lat])
        i, j = int(np.argmin(np.abs(y - cy))), int(np.argmin(np.abs(x - cx)))
        inside = x.min() <= cx <= x.max() and y.min() <= cy <= y.max()
        print(f"place centre ({lon}, {lat}) -> x {cx:.1f}, y {cy:.1f}; inside the grid: {inside}")
        if inside:
            patch = ds[max(0, i - 25):i + 25, max(0, j - 25):j + 25].astype("float64")
            ok = np.isfinite(patch) & (patch > 0)
            med = f"{10 * np.log10(np.median(patch[ok])):.1f} dB" if ok.any() else "no valid value"
            print(f"  50x50 pixels around the centre: {ok.mean():.0%} valid, median {med}")

    crop = nisar_io.read_crop(path, spot["bbox"])
    target = water.target_grid(spot["bbox"], res=150.0)
    on_grid = water.to_target(crop, target)["HH" if "HH" in crop.bands else "VV"]
    print(f"after cropping and putting it on the 150 m map grid: {np.isfinite(on_grid).mean():.0%} of the place has a value")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hotspot", default="tonle-sap")
    parser.add_argument("--all", action="store_true", help="check every file, not just the first")
    args = parser.parse_args()
    spot = layers.load_spot(args.hotspot)
    files = sorted((layers.WORK / spot["id"]).glob("*.h5"))
    if not files:
        sys.exit(f"No .h5 files in pipeline/work/{spot['id']}/")
    print(f"{spot['name']}: box {spot['bbox']}, {len(files)} files")
    for path in files if args.all else files[-1:]:
        describe(path, spot)


if __name__ == "__main__":
    main()
