"""Planetary Computer additions, run offline against small local rasters."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

import layers
import water

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def place(tmp_path, monkeypatch):
    import water_dance
    shutil.copy(ROOT / "data" / "hotspots.json", tmp_path / "hotspots.json")
    (tmp_path / "layers").mkdir()
    monkeypatch.setattr(layers, "DATA", tmp_path)
    monkeypatch.setattr(layers, "WORK", tmp_path / "work")
    spot = next(s for s in json.loads((tmp_path / "hotspots.json").read_text())["hotspots"] if s["id"] == "tonle-sap")
    files = water.make_demo_products(spot, ROOT / "pipeline" / "assets" / "tonle_sap_lake.geojson", tmp_path / "work" / "h5", spacing=600.0)
    water_dance.build_layers(spot, files, synthetic=True, res=600.0)
    return spot, tmp_path


def geotiff(path, spot, values, count=1, step=0.004):
    """A lon/lat raster over the place; values(lon, lat) returns a uint8 array per band."""
    west, south, east, north = spot["bbox"]
    xs, ys = np.arange(west, east, step) + step / 2, np.arange(north, south, -step) - step / 2
    gx, gy = np.meshgrid(xs, ys)
    data = np.stack([np.asarray(v, dtype="uint8") for v in values(gx, gy)])
    with rasterio.open(path, "w", driver="GTiff", width=len(xs), height=len(ys), count=count, dtype="uint8",
                       crs="EPSG:4326", transform=from_origin(west, north, step, step), nodata=0) as dst:
        dst.write(data)
    return str(path)


def catalogue(features):
    calls = []

    def fetch(url, body=None):
        calls.append(body)
        return {"features": features(body) if callable(features) else features, "links": []}
    return fetch, calls


def test_water_history_splits_new_from_usual(place):
    import exposure
    import planetary
    spot, tmp = place
    out = tmp / "layers" / "tonle-sap"
    before = json.loads((out / "manifest.json").read_text())
    first = np.asarray(Image.open(out / before["frames"][0]["files"]["water"]).convert("RGBA"))[..., 3] > 0
    grid = exposure.layer_grid(spot, out / before["frames"][0]["files"]["water"], before["grid_res"])
    # "Usually water" = wherever the first (driest) pass saw water, written as a lon/lat occurrence raster.
    lon0, lat_top = spot["bbox"][0], spot["bbox"][3]

    def occurrence(gx, gy):
        import rasterio.warp
        xs, ys = rasterio.warp.transform("EPSG:4326", water.WEB_CRS, gx.ravel(), gy.ravel())
        cols = ((np.array(xs) - grid.transform.c) / grid.res).astype(int).clip(0, grid.width - 1)
        rows = ((grid.transform.f - np.array(ys)) / grid.res).astype(int).clip(0, grid.height - 1)
        return [np.where(first[rows, cols], 95, 0).reshape(gx.shape)]

    href = geotiff(tmp / "occ.tif", spot, occurrence, step=0.002)
    fetch, _ = catalogue([{"id": "tile", "assets": {"occurrence": {"href": href}}}])
    m = planetary.add_water_history(spot, fetch=fetch)
    new = [f["stats"]["new_water_km2"] for f in m["frames"]]
    total = [f["stats"]["water_total_km2"] for f in m["frames"]]
    assert new[0] < 0.1 * total[0]                 # the first pass is almost all usual water
    assert new[-1] > 0.5 * (total[-1] - total[0])  # most of the growth counts as new
    assert m["baseline"]["agreement_pct"] >= 90 and m["layers"][1]["id"] == "newwater"
    assert all((out / f["files"]["newwater"]).exists() for f in m["frames"])
    # exposure and land cover now count only the new water
    masks = [mask.sum() for _, mask in exposure.changed_masks(m, out, grid)]
    assert masks[0] < 0.1 * first.sum() and masks[-1] > masks[0]
    # running it twice doesn't duplicate anything
    m2 = planetary.add_water_history(spot, fetch=fetch)
    assert [l["id"] for l in m2["layers"]].count("newwater") == 1
    assert [s["id"] for s in m2["stats"]].count("new_water_km2") == 1


def test_landcover_breakdown_adds_up(place):
    import planetary
    spot, tmp = place
    mid = (spot["bbox"][0] + spot["bbox"][2]) / 2
    href = geotiff(tmp / "cover.tif", spot, lambda gx, gy: [np.where(gx < mid, 40, 50)])   # cropland west, built-up east
    fetch, calls = catalogue([{"id": "wc", "assets": {"map": {"href": href}}}])
    m = planetary.add_landcover(spot, fetch=fetch)
    assert calls[0]["collections"] == ["esa-worldcover"]
    lc = m["landcover"]
    assert {row["label"] for row in lc["peak"]} == {"Cropland", "Built-up"}
    last = m["frames"][-1]
    assert abs(sum(lc["by_frame"][last["date"]].values()) - last["stats"]["water_total_km2"]) < 0.03 * last["stats"]["water_total_km2"]


def test_optical_picks_clear_pass_and_mosaics(place):
    import planetary
    spot, tmp = place
    mid = (spot["bbox"][0] + spot["bbox"][2]) / 2
    west = geotiff(tmp / "w.tif", spot, lambda gx, gy: [np.where(gx < mid, v, 0) for v in (200, 100, 50)], count=3)
    east = geotiff(tmp / "e.tif", spot, lambda gx, gy: [np.where(gx >= mid, v, 0) for v in (60, 120, 220)], count=3)
    cloudy = geotiff(tmp / "c.tif", spot, lambda gx, gy: [np.full(gx.shape, 255)] * 3, count=3)

    def features(body):
        day = body["datetime"][:10]
        item = lambda i, href, cloud, d: {"id": f"{i}-{d}", "properties": {"datetime": f"{d}T03:00:00Z", "eo:cloud_cover": cloud},
                                          "assets": {"visual": {"href": href}}}
        return [item("cloudy", cloudy, 55, day), item("w", west, 4, "2026-07-02"), item("e", east, 6, "2026-07-02")]

    fetch, calls = catalogue(features)
    m = planetary.add_optical(spot, fetch=fetch)
    assert calls[0]["query"] == {"eo:cloud_cover": {"lt": 60}}
    frames = m["optical"]["frames"]
    assert set(frames) == {f["date"] for f in m["frames"]}
    one = next(iter(frames.values()))
    assert one["date"] == "2026-07-02" and one["cloud"] == 5 and one["covered"] > 0.95
    img = np.asarray(Image.open(tmp / "layers" / "tonle-sap" / one["file"]).convert("RGBA")).astype(int)
    h, w = img.shape[:2]
    assert img[h // 2, w // 4, 0] > img[h // 2, w // 4, 2] and img[h // 2, 3 * w // 4, 2] > img[h // 2, 3 * w // 4, 0]
    assert w > 300 and len(m["optical"]["bounds"]) == 4


def test_tokens_are_added_only_to_planetary_computer_files():
    import planetary
    planetary._tokens.clear()
    fetch = lambda url, body=None: {"token": "sv=1&sig=abc"}
    assert planetary.sign("/local/file.tif", "jrc-gsw", fetch) == "/local/file.tif"
    assert planetary.sign("https://x.blob.core.windows.net/a/b.tif", "jrc-gsw", fetch).endswith("b.tif?sv=1&sig=abc")
