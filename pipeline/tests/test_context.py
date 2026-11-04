"""context.py against recorded-style responses (no network)."""
import json
from datetime import date

import context

USGS = {"features": [
    {"properties": {"mag": 7.5, "place": "20 km ESE of Yumare, Venezuela", "time": 1782345600000, "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zp"},
     "geometry": {"coordinates": [-68.5, 10.55, 10.0]}},
    {"properties": {"mag": None, "place": "bad", "time": 1782345600000}, "geometry": {"coordinates": [0, 0, 0]}},
]}
METEO = {"daily": {"time": ["2026-06-17", "2026-06-18"], "precipitation_sum": [12.4, None]}}


def fake(url):
    if "earthquake.usgs.gov" in url:
        assert "minmagnitude=4.5" in url and "format=geojson" in url
        return json.dumps(USGS)
    if "open-meteo" in url:
        assert "daily=precipitation_sum" in url
        return json.dumps(METEO)
    if "firms" in url:
        return "latitude,longitude,acq_date\n1,2,2026-08-30\n1,2,2026-08-30\n1,2,2026-09-02\n"
    raise AssertionError(url)


def test_quakes_parse_and_skip_bad():
    events = context.quakes([-68.6, 10.1, -66.6, 10.9], date(2026, 6, 1), date(2026, 7, 31), fake)
    assert len(events) == 1 and events[0]["magnitude"] == 7.5 and events[0]["kind"] == "earthquake"


def test_rain_keeps_gaps():
    r = context.rain(104.1, 12.8, date(2026, 6, 17), date(2026, 6, 18), fake)
    assert r["mm"] == [12.4, None] and r["dates"][0] == "2026-06-17"


def test_rain_too_recent_returns_none():
    assert context.rain(104.1, 12.8, date.today(), date.today(), fake) is None


def test_fires_sum_per_day():
    out = context.fires([-56.5, -8.5, -54, -6], date(2026, 8, 28), date(2026, 9, 5), "KEY", fake)
    assert [(e["date"], e["count"]) for e in out] == [("2026-08-30", 2), ("2026-09-02", 1)]


def test_offline_keeps_previous_context(tmp_path, monkeypatch):
    import json
    import context
    place = tmp_path / "data" / "layers" / "demo"
    place.mkdir(parents=True)
    (tmp_path / "data" / "hotspots.json").write_text(json.dumps({"hotspots": [
        {"id": "demo", "bbox": [0, 0, 1, 1], "lon": 0.5, "lat": 0.5}]}))
    (place / "manifest.json").write_text(json.dumps({"module": "water", "frames": [{"date": "2026-07-01"}]}))
    old = {"hotspot": "demo", "events": [{"kind": "earthquake", "date": "2026-07-01", "label": "M5"}], "sources": ["x"]}
    (place / "context.json").write_text(json.dumps(old))
    monkeypatch.setattr(context, "ROOT", tmp_path)
    monkeypatch.setattr(context, "LAYERS", tmp_path / "data" / "layers")

    def offline(url):
        raise OSError("offline")

    assert context.build("demo", fetch=offline) == old
    assert json.loads((place / "context.json").read_text()) == old
