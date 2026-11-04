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
