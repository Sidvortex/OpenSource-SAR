#!/usr/bin/env python3
"""
Free context layers from Microsoft's Planetary Computer (a Space Apps Global Offer).

The catalogue is public: no account, no key, no cost. Run these AFTER a place's
radar layers are built, because they add to its manifest:

    python pipeline/planetary.py optical --hotspot tonle-sap        # Sentinel-2 photos per radar date
    python pipeline/planetary.py water-history --hotspot tonle-sap  # new flood water vs 1984-2020
    python pipeline/planetary.py landcover --hotspot tonle-sap      # what kind of land changed
    python pipeline/planetary.py all --hotspot tonle-sap

  optical        ESA Sentinel-2 L2A true colour (10 m), least cloudy scene near each radar date.
  water-history  EC JRC Global Surface Water occurrence, 1984-2020 (water places only).
  landcover      ESA WorldCover 2021, 10 m (water, fire and ground places).

Rebuilding a place's radar layers removes these additions, so run them again afterwards.
Anonymous access is rate limited; if you have a free Planetary Computer key, set
PC_SDK_SUBSCRIPTION_KEY and it is sent with every request.
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta

import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds

import exposure
import layers
import water

STAC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
SAS_TOKEN = "https://planetarycomputer.microsoft.com/api/sas/v1/token/"

PERMANENT_PCT = 75                      # water in at least 75% of 1984-2020 observations
PERMANENT_RGBA = (120, 150, 190, 150)
NEW_RGBA = exposure.NEW_WATER_RGBA

WORLDCOVER = [   # ESA WorldCover classes, with ESA's own colours
    (10, "Tree cover", "#006400"), (20, "Shrubland", "#ffbb22"), (30, "Grassland", "#ffff4c"),
    (40, "Cropland", "#f096ff"), (50, "Built-up", "#fa0000"), (60, "Bare or sparse", "#b4b4b4"),
    (70, "Snow and ice", "#f0f0f0"), (80, "Permanent water", "#0064c8"),
    (90, "Wetland", "#0096a0"), (95, "Mangroves", "#00cf75"), (100, "Moss and lichen", "#fae6a0"),
]


# ---------------------------------------------------------------- catalogue access

def http_json(url, body=None):
    headers = {"Accept": "application/json", "User-Agent": "OpenSource-SAR"}
    if os.environ.get("PC_SDK_SUBSCRIPTION_KEY"):
        headers["Ocp-Apim-Subscription-Key"] = os.environ["PC_SDK_SUBSCRIPTION_KEY"]
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=60) as r:
        return json.load(r)


def search(collection, bbox, when=None, query=None, fetch=http_json, pages=5):
    """STAC items of one collection over bbox (west, south, east, north)."""
    body = {"collections": [collection], "bbox": list(bbox), "limit": 100}
    if when:
        body["datetime"] = when
    if query:
        body["query"] = query
    items, url = [], STAC_SEARCH
    for _ in range(pages):
        page = fetch(url, body)
        items += page.get("features", [])
        nxt = next((l for l in page.get("links", []) if l.get("rel") == "next"), None)
        if not nxt:
            break
        url, body = nxt["href"], nxt.get("body", body)
    return items


_tokens = {}


def sign(href, collection, fetch=http_json):
    """Planetary Computer files need a short-lived read token; anyone can get one."""
    if "blob.core.windows.net" not in href:
        return href
    if collection not in _tokens:
        _tokens[collection] = fetch(SAS_TOKEN + urllib.parse.quote(collection))["token"]
    return f"{href}?{_tokens[collection]}"


def read_onto_grid(href, target, bands=(1,), categorical=False):
    """Read a (possibly remote, cloud-optimised) raster onto the place's grid.

    Reads only the window over the place, at a reduced resolution close to the grid's,
    so a 10 m global tile costs a few megabytes rather than gigabytes.
    Returns a (bands, height, width) uint8 array, 0 where there is no data, or None if no overlap.
    """
    left, top = target.transform.c, target.transform.f
    right, bottom = left + target.width * target.res, top - target.height * target.res
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="4", GDAL_HTTP_RETRY_DELAY="2"):
        with rasterio.open(href) as src:
            box = transform_bounds(water.WEB_CRS, src.crs, left, bottom, right, top, densify_pts=21)
            win = from_bounds(*box, transform=src.transform)
            try:
                win = win.intersection(Window(0, 0, src.width, src.height))
            except rasterio.errors.WindowError:
                return None
            win = win.round_offsets().round_lengths()
            if win.width < 1 or win.height < 1:
                return None
            # how many source pixels fit in one grid pixel (grid metres are stretched by 1/cos(lat))
            mid_lat = float(target.row_lat[len(target.row_lat) // 2])
            ground = target.res * np.cos(np.radians(mid_lat))
            src_res = abs(src.transform.a) * (111_320.0 if src.crs.is_geographic else 1.0)
            step = max(1, int(ground // src_res))
            out_h, out_w = max(1, int(win.height // step)), max(1, int(win.width // step))
            data = src.read(list(bands), window=win, out_shape=(len(bands), out_h, out_w),
                            resampling=Resampling.nearest if categorical else Resampling.average)
            tf = src.window_transform(win) * rasterio.Affine.scale(win.width / out_w, win.height / out_h)
            out = np.zeros((len(bands), target.height, target.width), dtype="uint8")
            reproject(data, out, src_transform=tf, src_crs=src.crs, dst_transform=target.transform,
                      dst_crs=water.WEB_CRS, src_nodata=src.nodata, dst_nodata=0,
                      resampling=Resampling.nearest if categorical else Resampling.bilinear)
    return out


def mosaic(items, asset, collection, target, bands=(1,), categorical=False, fetch=http_json, valid=None, enough=0.995):
    """Paint items onto the grid in order; the first item with data at a pixel wins."""
    valid = valid or (lambda a: a.any(axis=0))
    canvas = np.zeros((len(bands), target.height, target.width), dtype="uint8")
    filled = np.zeros((target.height, target.width), dtype=bool)
    used = []
    for item in items:
        if asset not in item.get("assets", {}):
            continue
        try:
            tile = read_onto_grid(sign(item["assets"][asset]["href"], collection, fetch), target, bands, categorical)
        except (rasterio.errors.RasterioIOError, OSError) as exc:
            print(f"    couldn't read {item.get('id')}: {exc}")
            continue
        if tile is None:
            continue
        add = valid(tile) & ~filled
        if add.any():
            canvas[:, add] = tile[:, add]
            filled |= add
            used.append(item)
        if filled.mean() >= enough:
            break
    return canvas, filled, used


# ---------------------------------------------------------------- shared manifest handling

def load(spot):
    out = layers.DATA / "layers" / spot["id"]
    path = out / "manifest.json"
    if not path.exists():
        sys.exit(f"No layers for {spot['id']} yet. Build its radar layers first.")
    manifest = json.loads(path.read_text())
    first = out / next(iter(manifest["frames"][0]["files"].values()))
    return out, manifest, exposure.layer_grid(spot, first, manifest.get("grid_res"))


def save(spot, out, manifest):
    return layers.write_manifest(spot, out, {k: v for k, v in manifest.items() if k not in ("hotspot", "created")})


def add_method(manifest, line):
    if line not in manifest["method"]:
        manifest["method"].append(line)


# ---------------------------------------------------------------- Sentinel-2 optical

def optical_grid(spot, max_side=2400, finest=20.0):
    """A finer grid than the radar layers, capped so each photo stays a small download."""
    left, bottom, right, top = transform_bounds("EPSG:4326", water.WEB_CRS, *spot["bbox"])
    res = max(finest, float(np.ceil(max(right - left, top - bottom) / max_side)))
    return water.target_grid(spot["bbox"], res=res)


def add_optical(spot, days=10, max_cloud=60, fetch=http_json):
    out, manifest, _ = load(spot)
    grid = optical_grid(spot)
    for old in out.glob("optical_*.webp"):
        old.unlink()
    frames, cache = {}, {}
    for frame in manifest["frames"]:
        day = date.fromisoformat(frame["date"])
        when = f"{day - timedelta(days=days)}T00:00:00Z/{day + timedelta(days=days)}T23:59:59Z"
        items = search("sentinel-2-l2a", spot["bbox"], when, {"eo:cloud_cover": {"lt": max_cloud}}, fetch)
        taken = lambda it: date.fromisoformat(it["properties"]["datetime"][:10])
        # whole passes, least cloudy first: one date gives one consistent picture
        by_day = {}
        for it in items:
            by_day.setdefault(taken(it), []).append(it)
        cloud = lambda group: float(np.mean([it["properties"].get("eo:cloud_cover", 100) for it in group]))
        order = sorted(by_day, key=lambda d: (round(cloud(by_day[d]) / 10), abs((d - day).days)))
        ordered = [it for d in order for it in sorted(by_day[d], key=lambda it: it["properties"].get("eo:cloud_cover", 100))]
        key = tuple(it["id"] for it in ordered[:24])
        if not key:
            print(f"  {frame['date']}: no Sentinel-2 scene under {max_cloud}% cloud within {days} days")
            continue
        if key not in cache:
            cache[key] = mosaic(ordered[:24], "visual", "sentinel-2-l2a", grid, bands=(1, 2, 3), fetch=fetch)
        rgb, filled, used = cache[key]
        if filled.mean() < 0.2:
            print(f"  {frame['date']}: Sentinel-2 covers only {filled.mean():.0%} of the place; skipped")
            continue
        name = f"optical_{frame['date']}.webp"
        rgba = np.dstack([rgb[0], rgb[1], rgb[2], np.where(filled, 255, 0).astype("uint8")])
        Image.fromarray(rgba).save(out / name, quality=82, method=4)
        dates = sorted({taken(it) for it in used})
        frames[frame["date"]] = {
            "file": name, "date": max(dates, key=[taken(it) for it in used].count).isoformat(),
            "dates": [d.isoformat() for d in dates], "cloud": round(cloud(used)), "covered": round(float(filled.mean()), 2)}
        print(f"  {frame['date']}: Sentinel-2 from {', '.join(frames[frame['date']]['dates'])}, about {frames[frame['date']]['cloud']}% cloud")
    if not frames:
        manifest.pop("optical", None)
        print("No optical frames were added; the app keeps using NASA's MODIS image.")
    else:
        manifest["optical"] = {
            "source": "ESA Copernicus Sentinel-2 L2A true colour, via Microsoft Planetary Computer",
            "bounds": grid.corners_lonlat(), "res": grid.res, "frames": frames,
            "note": "The clearest Sentinel-2 pass near each radar date. It can be several days away, so check its date."}
        add_method(manifest, "Optical view: the least cloudy Sentinel-2 pass within "
                             f"{days} days of each radar date; frames without one fall back to NASA MODIS.")
    return save(spot, out, manifest)


# ---------------------------------------------------------------- JRC water history

def add_water_history(spot, fetch=http_json):
    out, manifest, grid = load(spot)
    if manifest["module"] != "water":
        sys.exit("Water history only applies to water places.")
    items = search("jrc-gsw", spot["bbox"], fetch=fetch)
    occ, filled, used = mosaic(items, "occurrence", "jrc-gsw", grid, fetch=fetch, enough=2.0)
    if not used:
        sys.exit("No JRC Global Surface Water tiles found over this place.")
    occ = occ[0].astype("int16")
    occ[occ > 100] = 0                                    # 255 marks no data
    permanent = occ >= PERMANENT_PCT
    core = occ >= 90
    for old in out.glob("newwater_*.png"):
        old.unlink()
    seen = []
    for frame in manifest["frames"]:
        alpha = np.asarray(Image.open(out / frame["files"]["water"]).convert("RGBA"))[..., 3] > 0
        new = alpha & ~permanent
        name = f"newwater_{frame['date']}.png"
        layers.save_classes({"permanent": permanent, "new": new}, {"permanent": PERMANENT_RGBA, "new": NEW_RGBA}, out / name)
        frame["files"]["newwater"] = name
        frame["stats"]["new_water_km2"] = round(water.area_km2(new, grid), 1)
        if core.any():
            seen.append(float((alpha & core).sum() / core.sum()))
    hexc = lambda rgba: "#%02x%02x%02x" % rgba[:3]
    layer = {"id": "newwater", "label": "New water", "opacity": 0.9,
             "legend": [{"label": "New on this pass", "color": hexc(NEW_RGBA)},
                        {"label": "Usually water (1984-2020)", "color": hexc(PERMANENT_RGBA)}],
             "note": "Radar water outside the area that was water in at least 75% of 1984-2020 satellite observations."}
    manifest["layers"] = [l for l in manifest["layers"] if l["id"] != "newwater"]
    manifest["layers"].insert(1, layer)
    stat = {"id": "new_water_km2", "label": "New water", "unit": "km²", "color": hexc(NEW_RGBA)}
    manifest["stats"] = [s for s in manifest["stats"] if s["id"] != "new_water_km2"] + [stat]
    manifest["baseline"] = {
        "source": "JRC Global Surface Water 1984-2020 (EC JRC/Google), via Microsoft Planetary Computer",
        "permanent_km2": round(water.area_km2(permanent, grid), 1),
        "agreement_pct": round(100 * float(np.median(seen))) if seen else None,
        "note": "Agreement: the share of long-term water (present in 90% or more of 1984-2020 observations) "
                "that our radar method also maps as water, on a typical pass."}
    add_method(manifest, "New water: radar water outside the JRC Global Surface Water area that was water "
                         f"in at least {PERMANENT_PCT}% of 1984-2020 observations.")
    peak = max(f["stats"]["new_water_km2"] for f in manifest["frames"])
    agree = manifest["baseline"]["agreement_pct"]
    print(f"{spot['id']}: usually water {manifest['baseline']['permanent_km2']:,} km²; new water up to {peak:,} km²"
          + (f"; radar finds {agree}% of long-term water" if agree is not None else ""))
    return save(spot, out, manifest)


# ---------------------------------------------------------------- ESA WorldCover

def add_landcover(spot, fetch=http_json):
    out, manifest, grid = load(spot)
    items = search("esa-worldcover", spot["bbox"], "2021-01-01T00:00:00Z/2021-12-31T23:59:59Z", fetch=fetch)
    cover, filled, used = mosaic(items, "map", "esa-worldcover", grid, categorical=True, fetch=fetch)
    if not used:
        sys.exit("No ESA WorldCover tiles found over this place.")
    cover = cover[0]
    by_frame = {}
    for frame, mask in exposure.changed_masks(manifest, out, grid):
        h, w = min(mask.shape[0], cover.shape[0]), min(mask.shape[1], cover.shape[1])
        m = np.zeros(cover.shape, dtype=bool)
        m[:h, :w] = mask[:h, :w]
        row = {}
        for code, label, _ in WORLDCOVER:
            if manifest["module"] == "water" and code == 80:
                continue                                   # water on permanent water is not a change
            km2 = round(water.area_km2(m & (cover == code), grid), 1)
            if km2 > 0:
                row[label] = km2
        by_frame[frame["date"]] = row
    peak_date = max(by_frame, key=lambda d: sum(by_frame[d].values()))
    colour = {label: c for _, label, c in WORLDCOVER}
    peak = sorted(by_frame[peak_date].items(), key=lambda kv: -kv[1])
    manifest["landcover"] = {
        "source": "ESA WorldCover 2021 (10 m, CC BY 4.0), via Microsoft Planetary Computer",
        "peak_date": peak_date,
        "peak": [{"label": label, "color": colour[label], "km2": km2} for label, km2 in peak],
        "by_frame": by_frame,
        "note": "The kind of land under the changed area, from a 2021 map. Land use may have changed since."}
    add_method(manifest, "Land cover: ESA WorldCover 2021 sampled on the layer grid, summed inside the changed area of each frame.")
    print(f"{spot['id']}: on {peak_date}, " + ", ".join(f"{label} {km2:,} km²" for label, km2 in peak[:4]))
    return save(spot, out, manifest)


def main():
    parser = argparse.ArgumentParser(description="Add free Planetary Computer context to a place.")
    parser.add_argument("what", choices=["optical", "water-history", "landcover", "all"])
    parser.add_argument("--hotspot", required=True)
    parser.add_argument("--days", type=int, default=10, help="optical: search this many days either side of each radar date")
    parser.add_argument("--max-cloud", type=int, default=60, help="optical: ignore scenes cloudier than this percentage")
    args = parser.parse_args()
    spot = layers.load_spot(args.hotspot)
    module = json.loads((layers.DATA / "layers" / spot["id"] / "manifest.json").read_text())["module"] \
        if (layers.DATA / "layers" / spot["id"] / "manifest.json").exists() else None
    if args.what in ("water-history", "all") and (args.what != "all" or module == "water"):
        add_water_history(spot)
    if args.what in ("landcover", "all") and (args.what != "all" or module in ("water", "fire", "ground")):
        add_landcover(spot)
    if args.what in ("optical", "all"):
        add_optical(spot, args.days, args.max_cloud)


if __name__ == "__main__":
    main()
