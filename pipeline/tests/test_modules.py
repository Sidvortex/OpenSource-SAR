"""MintPy import, exposure and ground reports, run in a temporary data folder."""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

import layers

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    shutil.copy(ROOT / "data" / "hotspots.json", tmp_path / "hotspots.json")
    (tmp_path / "layers").mkdir()
    monkeypatch.setattr(layers, "DATA", tmp_path)
    monkeypatch.setattr(layers, "WORK", tmp_path / "work")
    return tmp_path


def test_mintpy_import_builds_a_sinking_bowl(data_dir):
    import mintpy_import
    spot = layers.load_spot.__wrapped__("mexico-city") if hasattr(layers.load_spot, "__wrapped__") else \
        next(s for s in json.loads((data_dir / "hotspots.json").read_text())["hotspots"] if s["id"] == "mexico-city")
    ts, vel = mintpy_import.write_synthetic(spot, data_dir / "work")
    m = mintpy_import.build(spot, ts, vel, res=300.0, synthetic=True)
    assert len(m["frames"]) == 10 and m["dance"]["dance"] == "march"
    assert 20 <= m["layers"][1]["ramp"]["max"] <= 30          # about 25 cm/yr of synthetic sinking
    s = m["series"]
    cube = np.fromfile(data_dir / "layers" / "mexico-city" / s["file"], dtype="<f4")
    assert cube.size == s["count"] * s["height"] * s["width"]


def test_exposure_counts_people_in_water(data_dir):
    import exposure
    import water_dance
    spot = next(s for s in json.loads((data_dir / "hotspots.json").read_text())["hotspots"] if s["id"] == "tonle-sap")
    import water
    files = water.make_demo_products(spot, ROOT / "pipeline" / "assets" / "tonle_sap_lake.geojson", data_dir / "work" / "h5", spacing=600.0)
    water_dance.build_layers(spot, files, synthetic=True, res=600.0)
    pop = exposure.make_synthetic_population(spot, data_dir / "work" / "pop.tif", res=600.0)
    m = exposure.add_exposure(spot, pop, synthetic_population=True)
    people = [f["stats"]["people_exposed"] for f in m["frames"]]
    assert people[-1] >= people[0] >= 0 and m["exposure"]["synthetic"] is True


def test_reports_parse_issue_form():
    import reports
    issue = {"number": 7, "html_url": "https://github.com/x/y/issues/7", "title": "Ground report: Tonle Sap",
             "body": "### Place\n\n12.85, 104.05\n\n### Date you saw it\n\n2026-10-01\n\n### What did you see?\n\nFlooding\n\n### Details\n\nWater over the road"}
    r = reports.parse(issue)
    assert (r["lat"], r["lon"], r["kind"], r["date"]) == (12.85, 104.05, "Flooding", "2026-10-01")
    assert reports.parse({**issue, "pull_request": {}}) is None
    assert reports.parse({**issue, "body": "### Place\n\nnear the market"})["lat"] is None


def test_pick_pairs_prefers_event_spanning_shortest():
    import coverage_check as cc

    class R:
        def __init__(self, a, b):
            self.properties = {"sceneName": f"NISAR_L2_PR_GUNW_X_{a}T000000_{a}T000010_{b}T000000_{b}T000010_P"}

    rs = [R("20260716", "20260728"), R("20260618", "20260630"), R("20260606", "20260630"), R("20260704", "20260716")]
    picked = [cc.acquisition_dates(r.properties)[0].isoformat() for r in cc.pick_pairs(rs, 3, "2026-06-24")]
    assert picked == ["2026-06-18", "2026-06-06", "2026-07-16"]
    newest = [cc.acquisition_dates(r.properties)[0].isoformat() for r in cc.pick_pairs(rs, 2)]
    assert newest == ["2026-07-16", "2026-07-04"]


class Product:
    """A stand-in for an asf_search result: footprint plus the properties to_row reads."""
    def __init__(self, track, frame, day, west, south, east, north, direction="ASCENDING", gb=2.0):
        self.geometry = {"type": "Polygon", "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]]}
        name = f"NISAR_L2_PR_GCOV_001_{track:03d}_A_{frame:03d}_{day}T220000_{day}T220030_P05023_N_F_J_001"
        self.properties = {"sceneName": name, "pathNumber": track, "frameNumber": frame, "flightDirection": direction,
                           "bytes": {name + ".h5": {"bytes": int(gb * 1e9)}}}


def test_choose_stack_prefers_coverage_over_more_dates():
    import coverage_check as cc
    box = [103.3, 11.9, 105.0, 13.7]
    days = ["20260904", "20260916", "20260928", "20261010", "20261022", "20261103"]
    corner = [Product(155, 9, d, 104.6, 13.4, 107.0, 15.0) for d in days]           # only clips the corner
    south = [Product(11, 7, d, 103.0, 11.5, 105.4, 12.85) for d in days[:4]]       # two frames of one pass
    north = [Product(11, 8, d, 103.0, 12.75, 105.4, 14.0) for d in days[:4]]
    rows = [(r, cc.to_row("tonle-sap", "GCOV", "PROVISIONAL", r)) for r in corner + south + north]
    chosen, plans = cc.choose_stack(rows, box, max_dates=3)
    assert plans[0]["track"] == 11 and sorted(plans[0]["frames"]) == [7, 8]
    assert plans[0]["share"] > 0.97 and plans[1]["share"] < 0.1
    assert len(chosen) == 6 and len({row["date"] for _, row in chosen}) == 3   # 3 dates x 2 frames


def test_pick_pairs_skips_edge_clippers():
    import coverage_check as cc
    box = [-68.6, 10.1, -66.6, 10.9]

    class Pair(Product):
        def __init__(self, a, b, *corners):
            super().__init__(162, 7, a, *corners)
            self.properties["sceneName"] = f"NISAR_L2_PR_GUNW_X_{a}T000000_{a}T000010_{b}T000000_{b}T000010_P"

    edge = Pair("20260618", "20260630", -66.7, 10.0, -64.0, 12.0)        # spans the quake, clips 5%
    good = Pair("20260613", "20260625", -69.0, 9.5, -66.0, 11.5)
    late = Pair("20260724", "20260817", -69.0, 9.5, -66.0, 11.5)
    picked = cc.pick_pairs([edge, late, good], 3, "2026-06-24", box)
    assert picked == [good, late]


def test_reader_drops_near_zero_edge_values(tmp_path):
    import h5py
    import nisar_io
    path = tmp_path / "NISAR_L2_PR_GCOV_001_011_A_007_20260904T220000_20260904T220030_P05023_N_F_J_001.h5"
    xs, ys = np.arange(400000, 402000, 20.0) + 10, np.arange(1420000, 1418000, -20.0) - 10
    hh = np.full((ys.size, xs.size), 0.05, dtype="float32")
    hh[:, :10] = 2e-14                                     # -137 dB filler at the swath edge
    hh[:, 10:20] = np.nan
    with h5py.File(path, "w") as f:
        g = f.create_group("science/LSAR/GCOV/grids/frequencyA")
        g["HHHH"] = hh
        g["xCoordinates"], g["yCoordinates"] = xs, ys
        g["projection"] = np.int32(32648)
    from rasterio.warp import transform_bounds
    bbox = transform_bounds("EPSG:32648", "EPSG:4326", 400000, 1418000, 402000, 1420000)
    crop = nisar_io.read_crop(path, bbox, margin_m=0)
    band = crop.bands["HH"]
    assert np.isnan(band[:, :20]).all() and np.isfinite(band[:, 20:]).all()


def test_choose_stack_takes_one_product_per_pass():
    import coverage_check as cc
    box = [103.3, 11.9, 105.0, 13.7]
    rows = []
    for d in ["20260905", "20260917"]:
        for gb, mode in ((5.0, 1), (1.6, 2), (2.0, 3)):           # three products of the same pass
            r = Product(83, 8, d, 102.5, 11.0, 105.8, 14.5, gb=gb)
            r.properties["sceneName"] = r.properties["sceneName"].replace("_A_008_", f"_A_008_{mode}00{mode}_")
            r.properties["bytes"] = {r.properties["sceneName"] + ".h5": {"bytes": int(gb * 1e9)}}
            rows.append((r, cc.to_row("tonle-sap", "GCOV", "PROVISIONAL", r)))
    chosen, plans = cc.choose_stack(rows, box, max_dates=5)
    assert len(chosen) == 2 and all(row["size_gb"] == 1.6 for _, row in chosen)
    assert abs(plans[0]["size_gb"] - 3.2) < 0.01


def test_choose_pairs_stays_on_one_track():
    import coverage_check as cc
    box = [-68.6, 10.1, -66.6, 10.9]

    class Pair(Product):
        def __init__(self, track, frame, direction, a, b, *corners):
            super().__init__(track, frame, a, *corners, direction=direction)
            self.properties["sceneName"] = f"NISAR_L2_PR_GUNW_X_{track}_{frame}_{a}T000000_{a}T000010_{b}T000000_{b}T000010_P"

    west = (-69.0, 9.5, -66.95, 11.5)          # frame 7 covers ~82%
    east = (-67.0, 9.5, -66.0, 11.5)           # frame 6 fills the rest
    rows = [
        Pair(162, 7, "ASCENDING", "20260613", "20260625", *west), Pair(162, 6, "ASCENDING", "20260613", "20260625", *east),
        Pair(162, 7, "ASCENDING", "20260625", "20260707", *west), Pair(162, 7, "ASCENDING", "20260707", "20260719", *west),
        Pair(54, 83, "DESCENDING", "20260617", "20260629", -68.4, 10.0, -67.2, 11.0),
        Pair(126, 83, "DESCENDING", "20260622", "20260704", -68.5, 10.0, -67.4, 11.0),
    ]
    chosen, passes = cc.choose_pairs(rows, box, 3, "2026-06-24")
    assert {p["track"] for p in passes} == {162}
    assert [str(p["start"]) for p in passes] == ["2026-06-13", "2026-06-25", "2026-07-07"]
    assert sorted(passes[0]["frames"]) == [6, 7] and passes[0]["share"] > 0.97
    assert len(chosen) == 4                     # two frames for the event pass, one each after
    # no event: the best-covering track, newest pairs
    chosen, passes = cc.choose_pairs(rows, box, 2)
    assert {p["track"] for p in passes} == {162} and [str(p["start"]) for p in passes] == ["2026-06-25", "2026-07-07"]
