#!/usr/bin/env python3
"""
Parts 3 and 5: ground motion from NISAR GUNW interferograms, for earthquakes and sinking ground.

    python pipeline/quake.py demo --hotspot venezuela-coast       # synthetic earthquake, labelled
    python pipeline/quake.py demo --hotspot mexico-city           # synthetic sinking city + GNSS, labelled
    python pipeline/quake.py download --hotspot venezuela-coast   # needs a free Earthdata login
    python pipeline/quake.py process --hotspot venezuela-coast
    python pipeline/quake.py inspect path/to/GUNW.h5

An interferogram compares the radar phase of two passes 12 days apart. One full
colour cycle ("fringe") is half a wavelength, about 12 cm, of movement toward or
away from the satellite along its line of sight.

Sign convention: movement = -wavelength / (4 pi) x phase, positive = toward the
radar. Check this against the NISAR GUNW product specification before publishing,
and use --flip-sign if it is the other way round.
"""
import argparse
import json
import sys
import warnings
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import h5py
import numpy as np
from rasterio.warp import transform, transform_bounds
from scipy import ndimage

import coverage_check as cc
import dance
import layers
import nisar_io
import water
from layers import ROOT, WORK, load_spot
from water_dance import earthdata_session

from ground import MIN_COHERENCE, build_layers, make_subsidence_pairs, pretty  # noqa: F401


# ---------------------------------------------------------------- synthetic demo

def make_demo_pairs(spot, out_dir, spacing=150.0, epsg=32619, slip_m=2.4, locking_km=12.0):
    """
    SYNTHETIC interferograms in the GUNW layout: a right-lateral strike-slip rupture along
    the coast (a textbook screw-dislocation model), atmospheric noise, a decorrelated sea
    and fault zone, and a small ionospheric ramp that the pipeline should remove.
    """
    from matplotlib.path import Path as MplPath

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    west, south, east, north = spot["bbox"]
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{epsg}", west, south, east, north)
    xs = np.arange(x0 - 3000, x1 + 3000, spacing)
    ys = np.arange(y1 + 3000, y0 - 3000, -spacing)
    gx, gy = np.meshgrid(xs, ys)
    lon, lat = (np.asarray(v).reshape(gx.shape) for v in transform(f"EPSG:{epsg}", "EPSG:4326", gx.ravel().tolist(), gy.ravel().tolist()))

    land = np.zeros(gx.shape, dtype=bool)
    points = np.column_stack([lon.ravel(), lat.ravel()])
    for feature in json.loads((ROOT / "data" / "basemap" / "land.geojson").read_text())["features"]:
        geom = feature["geometry"]
        for polygon in (geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]):
            land |= MplPath(np.asarray(polygon[0])).contains_points(points).reshape(gx.shape)

    # Fault trace along the coast, in projected metres.
    (fx0, fx1), (fy0, fy1) = transform("EPSG:4326", f"EPSG:{epsg}", [-68.3, -66.9], [10.42, 10.56])
    strike = np.array([fx1 - fx0, fy1 - fy0]) / np.hypot(fx1 - fx0, fy1 - fy0)
    rel = np.stack([gx - fx0, gy - fy0], axis=-1)
    along = rel @ strike                                   # metres along the fault
    across = rel @ np.array([-strike[1], strike[0]])       # metres perpendicular to it
    length = np.hypot(fx1 - fx0, fy1 - fy0)
    fade = 25000.0                                         # slip dies away smoothly past the rupture ends
    taper = 0.5 * (np.tanh(along / fade) - np.tanh((along - length) / fade))
    u_parallel = slip_m / np.pi * np.arctan(across / (locking_km * 1000)) * taper
    east_motion = u_parallel * strike[0]
    los_true_m = 0.62 * east_motion                        # roughly E-W look direction, about 40 degrees off vertical

    rng = np.random.default_rng(7)
    wavelength = nisar_io.SPEED_OF_LIGHT / nisar_io.DEFAULT_CENTER_FREQUENCY
    passes = [date(2026, 6, 18) + timedelta(days=12 * i) for i in range(4)]
    written = []
    for i, (ref, sec) in enumerate(zip(passes, passes[1:])):
        coseismic = ref < date(2026, 6, 24) < sec
        signal = los_true_m if coseismic else 0.03 * los_true_m / max(1, i)   # small afterslip later
        atmosphere = ndimage.gaussian_filter(rng.standard_normal(gx.shape), 30)
        atmosphere = atmosphere / np.abs(atmosphere).max() * 0.02
        los = signal + atmosphere + rng.normal(0, 0.006, gx.shape)
        ionosphere = 0.6 * (gx - gx.min()) / (gx.max() - gx.min())       # radians, removed by the pipeline
        phase = -(4 * np.pi / wavelength) * los + ionosphere
        coherence = np.where(land, rng.normal(0.72, 0.1, gx.shape), rng.normal(0.12, 0.05, gx.shape))
        if coseismic:
            coherence[np.abs(across) < 2500] *= 0.35                        # damaged ground along the rupture
        coherence = np.clip(coherence, 0, 1)
        components = (coherence >= 0.3).astype("uint8")
        stamps = [f"{d:%Y%m%d}T101500_{d:%Y%m%d}T101540" for d in (ref, sec)]
        path = out_dir / f"SYNTHETIC_NISAR_L2_PR_GUNW_DEMO_{stamps[0]}_{stamps[1]}_DEMO.h5"
        with h5py.File(path, "w") as f:
            grid = f.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram")
            grid["xCoordinates"], grid["yCoordinates"] = xs, ys
            proj = grid.create_dataset("projection", data=np.int32(epsg))
            proj.attrs["epsg_code"] = np.int32(epsg)
            hh = grid.create_group("HH")
            hh["unwrappedPhase"] = phase.astype("float32")
            hh["coherenceMagnitude"] = coherence.astype("float32")
            hh["connectedComponents"] = components
            hh["ionospherePhaseScreen"] = ionosphere.astype("float32")
            f["science/LSAR/GUNW/grids/frequencyA/centerFrequency"] = nisar_io.DEFAULT_CENTER_FREQUENCY
        written.append(path)
    return written


# ---------------------------------------------------------------- commands

def cmd_download(args):
    spot = load_spot(args.hotspot)
    west, south, east, north = spot["bbox"]
    window = spot.get("window", {})
    area = {"label": spot["name"], "wkt": cc.bbox(west, south, east, north),
            "start": window.get("start", cc.PROVISIONAL_START), "end": window.get("end")}
    results = cc.search("GUNW", area, args.maturity, include_ur=False)
    if not results:
        sys.exit("No GUNW products found. Run update_coverage.py to check this area.")
    print(f"Found {len(results)} GUNW products; downloading up to {args.max}.")
    out = WORK / spot["id"]
    out.mkdir(parents=True, exist_ok=True)
    session = earthdata_session()
    for result in list(results)[:args.max]:
        print(f"  {result.properties.get('sceneName')}")
        result.download(path=str(out), session=session)
    print(f"Saved to {out}. Next: python pipeline/quake.py process --hotspot {spot['id']}")


def cmd_process(args):
    spot = load_spot(args.hotspot)
    folder = Path(args.work) if args.work else WORK / spot["id"]
    files = sorted(folder.glob("*.h5"))
    if not files:
        sys.exit(f"No .h5 files in {folder}. Run the download command first.")
    gnss_dir = ROOT / "data" / "gnss" / spot["id"]
    build_layers(spot, files, any(f.name.startswith("SYNTHETIC_") for f in files), args.res, not args.no_iono, args.flip_sign,
                 gnss_dir=gnss_dir if gnss_dir.exists() else None)


def cmd_demo(args):
    spot = load_spot(args.hotspot)
    print("Writing SYNTHETIC demo interferograms (not NISAR measurements)...")
    if spot.get("event"):
        files = make_demo_pairs(spot, WORK / f"demo-{spot['id']}")
        build_layers(spot, files, synthetic=True, res=args.res)
    else:
        files, stations = make_subsidence_pairs(spot, WORK / f"demo-{spot['id']}")
        build_layers(spot, files, synthetic=True, res=args.res, gnss_dir=stations)


def main():
    parser = argparse.ArgumentParser(description="SARabande Part 3: the earthquake.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("download")
    p.add_argument("--hotspot", default="venezuela-coast")
    p.add_argument("--max", type=int, default=6)
    p.add_argument("--maturity", default="PROVISIONAL", choices=["PROVISIONAL", "BETA"])
    p.set_defaults(func=cmd_download)
    p = sub.add_parser("process")
    p.add_argument("--hotspot", default="venezuela-coast")
    p.add_argument("--work")
    p.add_argument("--res", type=float, default=150.0)
    p.add_argument("--no-iono", action="store_true", help="skip the ionospheric correction")
    p.add_argument("--flip-sign", action="store_true", help="if the product's sign convention is the other way round")
    p.set_defaults(func=cmd_process)
    p = sub.add_parser("demo")
    p.add_argument("--hotspot", default="venezuela-coast")
    p.add_argument("--res", type=float, default=150.0)
    p.set_defaults(func=cmd_demo)
    p = sub.add_parser("inspect")
    p.add_argument("file")
    p.set_defaults(func=lambda a: print("\n".join(nisar_io.list_tree(a.file))))
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
