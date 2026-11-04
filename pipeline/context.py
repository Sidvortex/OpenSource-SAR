#!/usr/bin/env python3
"""
Context for every place with layers: what else happened while NISAR watched.

    python pipeline/context.py                 # every place in data/layers/index.json
    python pipeline/context.py --hotspot tonle-sap

Writes data/layers/<place>/context.json with:
  * earthquakes (M4.5+) from the USGS FDSN event service: free, no key;
  * daily rainfall at the place's centre from the Open-Meteo archive (ERA5-based):
    free, no key for non-commercial use, CC BY 4.0, "Weather data by Open-Meteo.com";
  * active fires from NASA FIRMS for fire places, only if the free FIRMS_MAP_KEY
    environment variable is set (register at firms.modaps.eosdis.nasa.gov/api).

Every source is optional: if one fails, the others are still written.
"""
import argparse
import csv
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "data" / "layers"
USER_AGENT = "OpenSource-SAR/1.0 (+https://github.com/Sidvortex/OpenSource-SAR)"
MIN_MAG = 4.5


def get(url, timeout=60):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def quakes(bbox, start, end, fetch=get):
    """USGS earthquakes inside the box (padded by 1 degree) between start and end."""
    west, south, east, north = bbox
    params = {"format": "geojson", "starttime": start.isoformat(), "endtime": (end + timedelta(days=1)).isoformat(),
              "minlatitude": max(south - 1, -90), "maxlatitude": min(north + 1, 90),
              "minlongitude": west - 1, "maxlongitude": east + 1, "minmagnitude": MIN_MAG,
              "orderby": "magnitude", "limit": 50}
    data = json.loads(fetch("https://earthquake.usgs.gov/fdsnws/event/1/query?" + urllib.parse.urlencode(params)))
    events = []
    for feature in data.get("features", []):
        p, (lon, lat, *_rest) = feature["properties"], feature["geometry"]["coordinates"]
        when = date.fromtimestamp(p["time"] / 1000) if p.get("time") else None
        if when is None or p.get("mag") is None:
            continue
        events.append({"kind": "earthquake", "date": when.isoformat(), "label": f"M{p['mag']:.1f} {p.get('place') or ''}".strip(),
                       "magnitude": round(float(p["mag"]), 1), "lon": round(lon, 3), "lat": round(lat, 3), "url": p.get("url")})
    return sorted(events, key=lambda e: e["date"])


def rain(lon, lat, start, end, fetch=get):
    """Daily precipitation in mm at one point. The archive lags real time by a few days."""
    end = min(end, date.today() - timedelta(days=5))
    if end < start:
        return None
    params = {"latitude": round(lat, 3), "longitude": round(lon, 3), "start_date": start.isoformat(),
              "end_date": end.isoformat(), "daily": "precipitation_sum", "timezone": "UTC"}
    data = json.loads(fetch("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)))
    daily = data.get("daily") or {}
    days, mm = daily.get("time") or [], daily.get("precipitation_sum") or []
    if not days:
        return None
    return {"dates": days, "mm": [None if v is None else round(float(v), 1) for v in mm],
            "point": [round(lon, 3), round(lat, 3)]}


def fires(bbox, start, end, key, fetch=get):
    """NASA FIRMS VIIRS (S-NPP) detections, fetched in 10-day chunks, summed per day."""
    west, south, east, north = bbox
    per_day = {}
    day = start
    while day <= end:
        span = min(10, (end - day).days + 1)
        for source in ("VIIRS_SNPP_SP", "VIIRS_SNPP_NRT"):
            url = (f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/"
                   f"{west},{south},{east},{north}/{span}/{day.isoformat()}")
            try:
                rows = list(csv.DictReader(io.StringIO(fetch(url))))
            except Exception:
                continue
            if rows and "acq_date" in rows[0]:
                for row in rows:
                    per_day[row["acq_date"]] = per_day.get(row["acq_date"], 0) + 1
                break
        day += timedelta(days=span)
    return [{"kind": "fire", "date": d, "label": f"{n} active-fire detections (VIIRS)", "count": n}
            for d, n in sorted(per_day.items())]


def build(spot_id, fetch=get, firms_key=None):
    manifest = json.loads((LAYERS / spot_id / "manifest.json").read_text())
    spots = {s["id"]: s for s in json.loads((ROOT / "data" / "hotspots.json").read_text())["hotspots"]}
    spot = spots[spot_id]
    frames = manifest["frames"]
    start = date.fromisoformat(frames[0].get("start") or frames[0]["date"]) - timedelta(days=14)
    end = date.fromisoformat(frames[-1]["date"]) + timedelta(days=3)
    out = {"hotspot": spot_id, "window": [start.isoformat(), end.isoformat()], "events": [], "rain": None,
           "sources": [], "errors": []}
    try:
        out["events"] += quakes(spot["bbox"], start, end, fetch)
        out["sources"].append("Earthquakes: USGS FDSN event service")
    except Exception as exc:
        out["errors"].append(f"USGS: {exc}")
    try:
        out["rain"] = rain(spot["lon"], spot["lat"], start, end, fetch)
        if out["rain"]:
            out["sources"].append("Rainfall: Weather data by Open-Meteo.com (ERA5-based), CC BY 4.0")
    except Exception as exc:
        out["errors"].append(f"Open-Meteo: {exc}")
    if firms_key and manifest["module"] == "fire":
        try:
            out["events"] += fires(spot["bbox"], start, end, firms_key, fetch)
            out["sources"].append("Active fires: NASA FIRMS (VIIRS S-NPP)")
        except Exception as exc:
            out["errors"].append(f"FIRMS: {exc}")
    out["events"].sort(key=lambda e: e["date"])
    path = LAYERS / spot_id / "context.json"
    if not out["sources"] and path.exists():
        # Every service failed (offline, rate limit): keep last week's context rather than blank it.
        print(f"{spot_id:18} kept the previous context, errors: {'; '.join(out['errors'])}")
        return json.loads(path.read_text())
    path.write_text(json.dumps(out, indent=1) + "\n")
    print(f"{spot_id:18} {len(out['events'])} events, rain {'yes' if out['rain'] else 'no'}"
          + (f", errors: {'; '.join(out['errors'])}" if out["errors"] else ""))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hotspot")
    args = parser.parse_args()
    index = json.loads((LAYERS / "index.json").read_text())["layers"]
    ids = [args.hotspot] if args.hotspot else list(index)
    for spot_id in ids:
        if not (LAYERS / spot_id / "manifest.json").exists():
            sys.exit(f"No layers for {spot_id}")
        build(spot_id, firms_key=os.environ.get("FIRMS_MAP_KEY"))


if __name__ == "__main__":
    main()
