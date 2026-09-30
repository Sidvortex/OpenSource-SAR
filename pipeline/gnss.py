"""
GNSS validation (Part 5): compare InSAR velocity with GPS/GNSS stations.

Station files are in the free Nevada Geodetic Laboratory "tenv3" format
(geodesy.unr.edu). Put them in data/gnss/<place>/ as SITE.tenv3. Columns used
(1-based): 3 decimal year, 8+9 east, 10+11 north, 12+13 up (metres), and, when
present, 21 and 22 latitude and longitude. Check NGL's format notes if a file
looks different.

Assumption, shown in the app: sinking ground moves vertically, so the GNSS
vertical rate is projected onto the radar line of sight with cos(incidence).
"""
from datetime import date, timedelta
from pathlib import Path

import numpy as np

EARTH_RADIUS = 6378137.0


def decimal_year_to_date(y):
    year = int(y)
    start = date(year, 1, 1)
    days = (date(year + 1, 1, 1) - start).days
    return start + timedelta(days=(y - year) * days)


def date_to_decimal_year(d):
    start = date(d.year, 1, 1)
    return d.year + (d - start).days / (date(d.year + 1, 1, 1) - start).days


def parse_tenv3(text):
    """Returns (site, lon, lat, decimal_years, up_metres); lon/lat are None if the file lacks them."""
    site, lon, lat, years, up = None, None, None, [], []
    for line in text.splitlines():
        cols = line.split()
        if len(cols) < 13 or not cols[2].replace(".", "", 1).isdigit():
            continue                                   # header or malformed line
        site = cols[0]
        years.append(float(cols[2]))
        up.append(float(cols[11]) + float(cols[12]))
        if len(cols) >= 22:
            lat, lon = float(cols[20]), float(cols[21])
            lon = lon - 360 if lon > 180 else lon
    return site, lon, lat, np.array(years), np.array(up)


def write_synthetic_tenv3(path, site, lon, lat, up_rate_m_yr, start, end, rng):
    """A SYNTHETIC station file in tenv3 layout, for the demo only."""
    lines = ["site YYMMMDD yyyy.yyyy __MJD week d reflon _e0(m) __east(m) ____n0(m) _north(m) u0(m) ____up(m) "
             "_ant(m) sig_e(m) sig_n(m) sig_u(m) __corr_en __corr_eu __corr_nu _latitude(deg) _longitude(deg) __height(m)"]
    day, t0 = start - timedelta(days=60), date_to_decimal_year(start)
    while day <= end + timedelta(days=10):
        y = date_to_decimal_year(day)
        up = up_rate_m_yr * (y - t0) + rng.normal(0, 0.003)
        lines.append(f"{site} {day:%y%b%d}".upper() + f" {y:.4f} 0 0 0 {lon:.1f} 0 {rng.normal(0, 0.002):.5f} 0 "
                     f"{rng.normal(0, 0.002):.5f} 0 {up:.5f} 0 0.001 0.001 0.003 0 0 0 {lat:.6f} {lon:.6f} 2240.0")
        day += timedelta(days=1)
    Path(path).write_text("\n".join(lines) + "\n")


def _pixel(target, lon, lat):
    x = np.radians(lon) * EARTH_RADIUS
    y = EARTH_RADIUS * np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))
    col = int((x - target.transform.c) / target.res)
    row = int((target.transform.f - y) / target.res)
    return (row, col) if 0 <= row < target.height and 0 <= col < target.width else None


def validate(folder, velocity_cm_yr, target, start, end, incidence_deg):
    stations, synthetic = [], False
    for path in sorted(Path(folder).glob("*.tenv3")):
        site, lon, lat, years, up = parse_tenv3(path.read_text())
        synthetic |= path.name.upper().startswith("SYN")
        if site is None or lon is None or len(years) < 10:
            continue
        window = (years >= date_to_decimal_year(start)) & (years <= date_to_decimal_year(end))
        use = window if window.sum() >= 10 else np.ones_like(years, dtype=bool)
        up_rate_cm = float(np.polyfit(years[use], up[use], 1)[0] * 100)
        pix = _pixel(target, lon, lat)
        if pix is None:
            continue
        r, c = pix
        patch = velocity_cm_yr[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2]
        insar = float(np.nanmean(patch)) if np.isfinite(patch).any() else None
        gnss_los = up_rate_cm * np.cos(np.radians(incidence_deg))
        stations.append({"id": site, "lon": round(lon, 4), "lat": round(lat, 4),
                         "gnss_cm_yr": round(gnss_los, 1),
                         "insar_cm_yr": None if insar is None else round(insar, 1),
                         "difference_cm_yr": None if insar is None else round(insar - gnss_los, 1)})
    diffs = [s["difference_cm_yr"] for s in stations if s["difference_cm_yr"] is not None]
    if not stations:
        return None
    return {"source": "GNSS stations, Nevada Geodetic Laboratory format", "synthetic": synthetic,
            "assumption": f"GNSS vertical rates projected onto the line of sight with cos({incidence_deg:.0f}°), assuming purely vertical motion.",
            "stations": stations,
            "rms_cm_yr": round(float(np.sqrt(np.mean(np.square(diffs)))), 1) if diffs else None}
