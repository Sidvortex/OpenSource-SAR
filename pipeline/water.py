"""
Part 2: the water dance.

Every pass is resampled onto one shared Web Mercator grid over the hotspot, so
dates line up pixel for pixel. Open water is dark to radar (smooth surfaces
reflect the pulse away); flooded forest and shrubs turn bright because the
pulse bounces off the water and back up the trunks ("double bounce").
"""
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
import json

import h5py
import numpy as np
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform, transform_bounds
from scipy import ndimage

WEB_CRS = "EPSG:3857"
EARTH_RADIUS = 6378137.0


@dataclass
class TargetGrid:
    transform: object
    width: int
    height: int
    res: float
    row_lat: np.ndarray    # latitude of each row centre, for true areas

    def corners_lonlat(self):
        """Top-left, top-right, bottom-right, bottom-left in lon/lat (MapLibre image order)."""
        left, top = self.transform.c, self.transform.f
        right, bottom = left + self.width * self.res, top - self.height * self.res
        lons, lats = transform(WEB_CRS, "EPSG:4326", [left, right, right, left], [top, top, bottom, bottom])
        return [[round(lo, 6), round(la, 6)] for lo, la in zip(lons, lats)]


def target_grid(bbox, res=100.0):
    """A Web Mercator grid over bbox (west, south, east, north). res is in Mercator metres."""
    left, bottom, right, top = transform_bounds("EPSG:4326", WEB_CRS, *bbox)
    width, height = int(np.ceil((right - left) / res)), int(np.ceil((top - bottom) / res))
    tf = from_origin(left, top, res, res)
    ys = top - (np.arange(height) + 0.5) * res
    row_lat = np.degrees(2 * np.arctan(np.exp(ys / EARTH_RADIUS)) - np.pi / 2)
    return TargetGrid(tf, width, height, res, row_lat)


def to_target(grid, target):
    """Resample each band of a cropped product onto the target grid (averaging linear power)."""
    x, y = grid.x, grid.y
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    out = {}
    for pol, band in grid.bands.items():
        data = band
        if dx < 0:
            data, x_first = data[:, ::-1], x[-1]
        else:
            x_first = x[0]
        if dy > 0:                       # rows running south to north: flip to north-up
            data, y_first = data[::-1, :], y[-1]
        else:
            y_first = y[0]
        src_tf = from_origin(x_first - abs(dx) / 2, y_first + abs(dy) / 2, abs(dx), abs(dy))
        dst = np.full((target.height, target.width), np.nan, dtype="float32")
        reproject(
            source=np.ascontiguousarray(data), destination=dst,
            src_transform=src_tf, src_crs=f"EPSG:{grid.epsg}", src_nodata=np.nan,
            dst_transform=target.transform, dst_crs=WEB_CRS, dst_nodata=np.nan,
            resampling=Resampling.average,
        )
        out[pol] = dst
    return out


def to_db(power):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(power)


def otsu_threshold(values, bins=256):
    """Otsu's method: the cut that best separates two groups in a histogram."""
    hist, edges = np.histogram(values, bins=bins)
    centres = (edges[:-1] + edges[1:]) / 2
    w0 = np.cumsum(hist)
    w1 = w0[-1] - w0
    m0 = np.cumsum(hist * centres) / np.maximum(w0, 1)
    m1 = (np.sum(hist * centres) - np.cumsum(hist * centres)) / np.maximum(w1, 1)
    between = w0 * w1 * (m0 - m1) ** 2
    return float(centres[np.argmax(between)])


def water_masks(hh_db_by_date, clamp=(-24.0, -14.0), rise_db=3.0, bright_db=-8.0):
    """
    Open water: HH below a per-scene Otsu threshold, clamped to a physically sensible range.
    Likely flooded vegetation: HH at least rise_db brighter than on the driest date, and bright overall.
    Returns {date: (open_water, flooded_veg, threshold)} plus the reference (driest) date.
    """
    open_water, thresholds = {}, {}
    for day, hh in hh_db_by_date.items():
        valid = np.isfinite(hh)
        sample = hh[valid]
        if sample.size > 200_000:
            sample = np.random.default_rng(0).choice(sample, 200_000, replace=False)
        thr = float(np.clip(otsu_threshold(sample), *clamp)) if sample.size else clamp[0]
        mask = valid & (hh < thr)
        open_water[day] = ndimage.binary_opening(mask, structure=np.ones((3, 3)))
        thresholds[day] = thr
    reference = min(open_water, key=lambda d: open_water[d].sum())
    ref = hh_db_by_date[reference]
    result = {}
    for day, hh in hh_db_by_date.items():
        veg = np.isfinite(hh) & np.isfinite(ref) & (hh - ref >= rise_db) & (hh > bright_db) & ~open_water[day]
        veg = ndimage.binary_opening(veg, structure=np.ones((3, 3)))
        result[day] = (open_water[day], veg, thresholds[day])
    return result, reference


def area_km2(mask, target):
    """True area: Web Mercator pixels shrink by cos(latitude) in each direction."""
    weights = np.cos(np.radians(target.row_lat)) ** 2
    return float((mask.sum(axis=1) * weights).sum() * target.res ** 2 / 1e6)


# ---------------------------------------------------------------- synthetic demo

def _ease(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def make_demo_products(spot, lake_geojson, out_dir, spacing=150.0, epsg=32648):
    """
    Write SYNTHETIC files in the NISAR GCOV layout so the whole app and pipeline can be
    exercised before real data is downloaded. Every file name starts with SYNTHETIC_,
    and everything built from them is flagged as synthetic in the manifest and the UI.
    """
    from matplotlib.path import Path as MplPath

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = spot["bbox"]
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{epsg}", west, south, east, north)
    xs = np.arange(x0 - 3000, x1 + 3000, spacing)
    ys = np.arange(y1 + 3000, y0 - 3000, -spacing)          # north to south, like NISAR grids
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = transform(f"EPSG:{epsg}", "EPSG:4326", gx.ravel().tolist(), gy.ravel().tolist())
    points = np.column_stack([lon, lat])

    lake = np.zeros(gx.size, dtype=bool)
    for feature in json.loads(Path(lake_geojson).read_text())["features"]:
        geom = feature["geometry"]
        polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for polygon in polygons:
            lake |= MplPath(np.asarray(polygon[0])).contains_points(points)
    lake = lake.reshape(gx.shape)

    rng = np.random.default_rng(42)
    distance = ndimage.distance_transform_edt(~lake) * spacing             # metres from the dry-season lake
    wobble = ndimage.gaussian_filter(rng.standard_normal(gx.shape), 12)
    wobble = wobble / np.abs(wobble).max() * 7000                          # irregular floodplain edges

    start, peak = date(2026, 6, 19), date(2026, 10, 15)
    days = [start + timedelta(days=12 * i) for i in range(9)]
    days = [d for d in days if not date(2026, 7, 27) <= d <= date(2026, 8, 10) and d <= date(2026, 9, 27)]
    written = []
    for day in days:
        reach = 15000 * _ease((day - start).days / (peak - start).days)
        spread = distance + wobble
        water = lake | (spread <= reach)
        veg = ~water & (spread <= reach + 4500) & (reach > 0)
        hh_db = np.full(gx.shape, -8.0) + rng.normal(0, 1.2, gx.shape)
        hv_db = np.full(gx.shape, -14.0) + rng.normal(0, 1.2, gx.shape)
        hh_db[water], hv_db[water] = -22 + rng.normal(0, 1.5, water.sum()), -28 + rng.normal(0, 1.5, water.sum())
        hh_db[veg], hv_db[veg] = -2 + rng.normal(0, 1.2, veg.sum()), -12 + rng.normal(0, 1.2, veg.sum())
        speckle = rng.gamma(4, 1 / 4, gx.shape)                           # 4-look speckle
        stamp = day.strftime("%Y%m%d")
        path = out_dir / f"SYNTHETIC_NISAR_L2_PR_GCOV_DEMO_{stamp}T221500_{stamp}T221540_DEMO.h5"
        with h5py.File(path, "w") as f:
            g = f.create_group("science/LSAR/GCOV/grids/frequencyA")
            g["HHHH"] = (10 ** (hh_db / 10) * speckle).astype("float32")
            g["HVHV"] = (10 ** (hv_db / 10) * speckle).astype("float32")
            g["xCoordinates"] = xs
            g["yCoordinates"] = ys
            proj = g.create_dataset("projection", data=np.int32(epsg))
            proj.attrs["epsg_code"] = np.int32(epsg)
            f["science/LSAR/identification/zeroDopplerStartTime"] = f"{day.isoformat()}T22:15:00".encode()
        written.append(path)
    return written
