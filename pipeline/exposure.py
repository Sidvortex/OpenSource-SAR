#!/usr/bin/env python3
"""
People on changing ground: how many people live where a place's layers show change.

    python pipeline/exposure.py --hotspot tonle-sap --population worldpop.tif
    python pipeline/exposure.py --hotspot mexico-city --population ghsl.tif

Population rasters are free: WorldPop (worldpop.org, CC BY 4.0) or the JRC GHSL
population grid. Download one that covers the place (a counts raster, people per
pixel, not density) and pass its path. The script sums people inside the changed
area of every frame and adds "people_km" statistics to the place's manifest.

What counts as changed ground, per module:
  water    open water or likely flooded vegetation (the class layer)
  fire     burned or cleared (the class layer)
  ground   total movement beyond 5 cm (from the inspector cube)
  farming, ice: not meaningful, so skipped
"""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import Resampling, reproject

import layers
import water
from layers import DATA, load_spot

MOVED_CM = 5.0
CLASS_LAYER = {"water": "water", "fire": "burn"}


def population_on_grid(path, target):
    """Sum a people-per-pixel raster onto the place's shared grid."""
    with rasterio.open(path) as src:
        dst = np.zeros((target.height, target.width), dtype="float64")
        reproject(source=rasterio.band(src, 1), destination=dst, dst_transform=target.transform,
                  dst_crs=water.WEB_CRS, src_nodata=src.nodata, dst_nodata=0, resampling=Resampling.sum)
    dst[~np.isfinite(dst) | (dst < 0)] = 0
    return dst


def layer_grid(spot, image_path, recorded_res=None):
    """The exact grid a place's layers were drawn on: the pipelines call target_grid(bbox, res)."""
    from rasterio.warp import transform_bounds
    width, height = Image.open(image_path).size
    left, bottom, right, top = transform_bounds("EPSG:4326", water.WEB_CRS, *spot["bbox"])
    candidates = ([recorded_res] if recorded_res else []) + [60.0, 100.0, 150.0, 200.0, 300.0, 500.0, 600.0]
    for res in candidates:
        grid = water.target_grid(spot["bbox"], res=res)
        if (grid.width, grid.height) == (width, height):
            return grid
    raise SystemExit(f"Couldn't match the layer grid ({width}x{height}); rebuild the layers first.")


def changed_masks(manifest, out, target):
    module = manifest["module"]
    if module in CLASS_LAYER:
        key = CLASS_LAYER[module]
        for frame in manifest["frames"]:
            alpha = np.asarray(Image.open(out / frame["files"][key]).convert("RGBA"))[..., 3]
            yield frame, alpha > 0
    elif module == "ground":
        s = manifest["series"]
        cube = np.fromfile(out / s["file"], dtype="<f4").reshape(s["count"], s["height"], s["width"])
        by_date = {d: i for i, d in enumerate(s["dates"])}
        for frame in manifest["frames"]:
            i = by_date.get(frame["date"])
            if i is None:
                continue
            small = np.abs(np.nan_to_num(cube[i])) > MOVED_CM
            big = np.kron(small, np.ones((s["factor"], s["factor"]), dtype=bool))[:target.height, :target.width]
            yield frame, big
    else:
        raise SystemExit(f"Exposure isn't meaningful for {module} places.")


def add_exposure(spot, population_path, synthetic_population=False):
    out = DATA / "layers" / spot["id"]
    manifest = json.loads((out / "manifest.json").read_text())
    grid = layer_grid(spot, out / next(iter(manifest["frames"][0]["files"].values())), manifest.get("grid_res"))
    pop = population_on_grid(population_path, grid)
    for frame, mask in changed_masks(manifest, out, grid):
        h, w = min(mask.shape[0], pop.shape[0]), min(mask.shape[1], pop.shape[1])
        frame["stats"]["people_exposed"] = int(round(pop[:h, :w][mask[:h, :w]].sum()))
    stat = {"id": "people_exposed", "label": "People on changed ground", "unit": "people"}
    manifest["stats"] = [s for s in manifest["stats"] if s["id"] != "people_exposed"] + [stat]
    manifest["exposure"] = {"source": Path(population_path).name, "synthetic": synthetic_population,
                            "note": "People per pixel summed where this layer shows change. A count of people living there, "
                                    "not of people harmed."}
    method = "People on changed ground: a population raster summed inside the changed area of each frame."
    if method not in manifest["method"]:
        manifest["method"].append(method)
    layers.write_manifest(spot, out, {k: v for k, v in manifest.items() if k not in ("hotspot", "created")})
    peak = max(f["stats"].get("people_exposed", 0) for f in manifest["frames"])
    print(f"{spot['id']}: up to {peak:,} people on changed ground")
    return manifest


def make_synthetic_population(spot, path, res=500.0):
    """SYNTHETIC population (towns as soft blobs), only for the labelled demos."""
    from rasterio.transform import from_origin
    grid = water.target_grid(spot["bbox"], res=res)
    rng = np.random.default_rng(21)
    rows, cols = np.indices((grid.height, grid.width))
    people = np.zeros((grid.height, grid.width))
    for _ in range(14):
        r, c = rng.uniform(0, grid.height), rng.uniform(0, grid.width)
        size, total = rng.uniform(3, 12), rng.uniform(5_000, 400_000)
        blob = np.exp(-(((rows - r) / size) ** 2 + ((cols - c) / size) ** 2))
        people += blob / blob.sum() * total
    with rasterio.open(path, "w", driver="GTiff", width=grid.width, height=grid.height, count=1, dtype="float32",
                       crs=water.WEB_CRS, transform=from_origin(grid.transform.c, grid.transform.f, res, res), nodata=-1) as dst:
        dst.write(people.astype("float32"), 1)
    return path


def main():
    parser = argparse.ArgumentParser(description="Add people-on-changing-ground statistics to a place.")
    parser.add_argument("--hotspot", required=True)
    parser.add_argument("--population", help="people-per-pixel GeoTIFF (WorldPop or GHSL)")
    parser.add_argument("--demo", action="store_true", help="use a SYNTHETIC population (for the labelled demos only)")
    args = parser.parse_args()
    spot = load_spot(args.hotspot)
    if args.demo:
        path = layers.WORK / f"SYNTHETIC_population_{spot['id']}.tif"
        path.parent.mkdir(parents=True, exist_ok=True)
        add_exposure(spot, make_synthetic_population(spot, path), synthetic_population=True)
    elif args.population:
        add_exposure(spot, args.population)
    else:
        parser.error("give --population FILE, or --demo")


if __name__ == "__main__":
    main()
