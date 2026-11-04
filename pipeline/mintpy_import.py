#!/usr/bin/env python3
"""
Bring a MintPy time series into Open Source SAR.

MintPy (github.com/insarlab/MintPy, GPL-3.0, free) turns a stack of interferograms
into a corrected displacement time series. Run it on a place's NISAR GUNW stack,
geocode the results (MintPy's geocode step, or work in geographic coordinates),
then import:

    python pipeline/mintpy_import.py --hotspot mexico-city \
        --timeseries mintpy/geo/geo_timeseries_ERA5_demErr.h5 --velocity mintpy/geo/geo_velocity.h5

Reads the "timeseries" dataset (metres, dates in the "date" dataset) and, if given,
"velocity" and "velocityStd" (metres per year). Geocoded MintPy files carry the grid
as X_FIRST, Y_FIRST, X_STEP, Y_STEP attributes in degrees (EPSG:4326).
"""
import argparse
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

import dance
import layers
import nisar_io
import water
from layers import load_spot

MOVED_CM = 10.0


def read_geocoded(path, dataset):
    with h5py.File(path, "r") as f:
        attrs = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in f.attrs.items()}
        data = f[dataset][()]
        dates = None
        if "date" in f:
            dates = [datetime.strptime(d.decode() if isinstance(d, bytes) else str(d), "%Y%m%d").date() for d in f["date"][()]]
        extra = {name: f[name][()] for name in ("velocityStd",) if name in f}
    for key in ("X_FIRST", "Y_FIRST", "X_STEP", "Y_STEP"):
        if key not in attrs:
            raise SystemExit(f"{path} has no {key} attribute: geocode the MintPy results first (mintpy geocode).")
    x0, y0, dx, dy = (float(attrs[k]) for k in ("X_FIRST", "Y_FIRST", "X_STEP", "Y_STEP"))
    epsg = int(attrs.get("EPSG", 4326))
    width, length = data.shape[-1], data.shape[-2]
    x = x0 + (np.arange(width) + 0.5) * dx
    y = y0 + (np.arange(length) + 0.5) * dy
    return data, dates, x, y, epsg, extra


def to_grid(arr, x, y, epsg, target, day=None):
    grid = nisar_io.Grid(acquired=day, epsg=epsg, x=x, y=y, bands={"V": arr.astype("float32")}, source="mintpy")
    return water.to_target(grid, target)["V"]


def build(spot, ts_path, vel_path=None, res=150.0, synthetic=False):
    target = water.target_grid(spot["bbox"], res=res)
    ts, dates, x, y, epsg, _ = read_geocoded(ts_path, "timeseries")
    if not dates:
        raise SystemExit("The time-series file has no 'date' dataset.")
    ts_cm = ts * 100.0
    totals = []
    for i, d in enumerate(dates):
        layer = ts_cm[i].astype("float32")
        totals.append(to_grid(layer, x, y, epsg, target, d))
    years = np.array([(d - dates[0]).days / 365.25 for d in dates])
    if vel_path:
        vel, _, vx, vy, vepsg, extra = read_geocoded(vel_path, "velocity")
        velocity = to_grid(vel * 100.0, vx, vy, vepsg, target)
        vstd = to_grid(extra["velocityStd"] * 100.0, vx, vy, vepsg, target) if "velocityStd" in extra else None
    else:
        stack = np.stack(totals)
        with np.errstate(invalid="ignore"):
            velocity = (np.nansum((stack - np.nanmean(stack, 0)) * (years - years.mean())[:, None, None], 0)
                        / np.sum((years - years.mean()) ** 2)).astype("float32")
        vstd = None

    out = layers.layer_folder(spot["id"])
    tot_max = float(max(1.0, np.ceil(max(np.nanpercentile(np.abs(t), 99.5) for t in totals if np.isfinite(t).any()))))
    vel_max = float(max(1.0, np.ceil(np.nanpercentile(np.abs(velocity), 99.5) / 5.0) * 5.0))
    layers.save_ramp(velocity, -vel_max, vel_max, "RdBu", out / "velocity.png")
    frames = []
    for d, t in zip(dates, totals):
        name = f"total_{d.isoformat()}.png"
        layers.save_ramp(t, -tot_max, tot_max, "RdBu", out / name)
        frames.append({"date": d.isoformat(), "label": d.isoformat(), "files": {"total": name, "velocity": "velocity.png"},
                       "stats": {"max_total_cm": round(float(np.nanpercentile(np.abs(t), 99.5)) if np.isfinite(t).any() else 0.0, 1),
                                 "moved_km2": round(water.area_km2(np.isfinite(t) & (np.abs(t) > MOVED_CM), target), 1)},
                       "sources": [Path(ts_path).name]})

    factor = layers.series_factor(target.height, target.width)
    reduced = [layers.reduce_grid(t, factor) for t in totals]
    if vstd is not None:
        sig = layers.reduce_grid(vstd, factor)
        sigmas = [np.maximum(sig * yr, 0.1).astype("float32") for yr in years]
    else:
        sigmas = [np.full_like(reduced[0], 0.5) for _ in years]
    count, h, w = layers.write_series(out, "series.bin", reduced)
    layers.write_series(out, "sigma.bin", sigmas)
    final = np.abs(reduced[-1])
    if np.isfinite(final).any():
        r, c = np.unravel_index(np.nanargmax(final), final.shape)
        place_dance = dance.classify([(d - dates[0]).days for d in dates], [float(v[r, c]) for v in reduced],
                                     [float(s[r, c]) for s in sigmas], unit="cm", when=[f"{d:%b} {d.day}" for d in dates])
    else:
        place_dance = {"dance": "still", "confidence": "low", "reason": "No reliable pixels."}
    place_dance["basis"] = "the spot that moved most"
    return layers.write_manifest(spot, out, {
        "module": "ground",
        "title": f"{spot['name']}: the ground on the move (MintPy time series)",
        "headline": (f"The fastest-moving ground moves about {vel_max:.0f} cm a year along the radar's line of sight, "
                     f"roughly {vel_max * 1.3:.0f} cm a year if it is all sinking."),
        "synthetic": synthetic,
        "product": "MintPy time series from NISAR L2 GUNW interferograms",
        "bounds": target.corners_lonlat(), "grid_res": target.res, "event": spot.get("event"),
        "frame_noun": "passes", "sides": ["First pass", "Latest pass"],
        "side_stat": {"id": "max_total_cm", "label": "Total so far, up to", "unit": "cm"},
        "compare": [0, len(frames) - 1],
        "layers": [
            {"id": "total", "label": "Total so far", "opacity": 0.85,
             "ramp": {"colors": layers.ramp_colours("RdBu"), "min": -tot_max, "max": tot_max, "unit": "cm",
                      "low": "Away from the radar (mostly sinking)", "high": "Toward the radar"},
             "note": "Total line-of-sight movement since the first pass, from MintPy's corrected time series."},
            {"id": "velocity", "label": "Speed per year", "opacity": 0.85,
             "ramp": {"colors": layers.ramp_colours("RdBu"), "min": -vel_max, "max": vel_max, "unit": "cm",
                      "low": "Moving away each year", "high": "Moving toward each year"},
             "note": "MintPy's average rate in cm per year. Purely vertical sinking would be about 1.3 times this."},
        ],
        "stats": [{"id": "max_total_cm", "label": "Total so far, up to", "unit": "cm"},
                  {"id": "moved_km2", "label": f"Moved over {MOVED_CM:.0f} cm", "unit": "km²"}],
        "chart": {"area": "max_total_cm", "line": None, "label": "Total movement so far, cm"},
        "series": {"file": "series.bin", "sigma_file": "sigma.bin", "count": count, "width": w, "height": h,
                   "factor": factor, "full_width": target.width, "full_height": target.height,
                   "dates": [d.isoformat() for d in dates], "label": "Total movement since the first pass (MintPy)", "unit": "cm"},
        "dance": place_dance, "validation": None, "bridged": [],
        "method": ["MintPy inverted the interferogram network into a displacement time series, with its standard corrections.",
                   "Values are line-of-sight centimetres relative to MintPy's reference point.",
                   "Uncertainty grows with time from MintPy's velocity standard deviation." if vstd is not None
                   else "No velocity uncertainty was supplied; a constant 0.5 cm is shown."],
        "frames": frames,
    })


def write_synthetic(spot, folder):
    """SYNTHETIC MintPy-style geocoded files, for testing only."""
    from datetime import date, timedelta
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    west, south, east, north = spot["bbox"]
    step = 0.002
    xs, ys = np.arange(west, east, step), np.arange(north, south, -step)
    gx, gy = np.meshgrid(xs, ys)
    bowl = np.exp(-(((gx - spot["lon"]) / 0.08) ** 2 + ((gy - spot["lat"]) / 0.06) ** 2))
    rate = -0.25 * bowl                                   # metres per year along the line of sight
    days = [date(2026, 6, 19) + timedelta(days=12 * i) for i in range(10)]
    yrs = np.array([(d - days[0]).days / 365.25 for d in days])
    ts = (rate[None] * yrs[:, None, None]).astype("float32")
    attrs = {"X_FIRST": west, "Y_FIRST": north, "X_STEP": step, "Y_STEP": -step, "EPSG": "4326"}
    ts_path, vel_path = folder / "SYNTHETIC_geo_timeseries.h5", folder / "SYNTHETIC_geo_velocity.h5"
    with h5py.File(ts_path, "w") as f:
        f["timeseries"] = ts
        f["date"] = np.array([d.strftime("%Y%m%d").encode() for d in days])
        f.attrs.update(attrs)
    with h5py.File(vel_path, "w") as f:
        f["velocity"] = rate.astype("float32")
        f["velocityStd"] = np.full_like(rate, 0.005, dtype="float32")
        f.attrs.update(attrs)
    return ts_path, vel_path


def main():
    parser = argparse.ArgumentParser(description="Import a geocoded MintPy time series as a place's layers.")
    parser.add_argument("--hotspot", required=True)
    parser.add_argument("--timeseries", required=True)
    parser.add_argument("--velocity")
    parser.add_argument("--res", type=float, default=150.0)
    args = parser.parse_args()
    synthetic = Path(args.timeseries).name.startswith("SYNTHETIC_")
    build(load_spot(args.hotspot), args.timeseries, args.velocity, args.res, synthetic)


if __name__ == "__main__":
    main()
