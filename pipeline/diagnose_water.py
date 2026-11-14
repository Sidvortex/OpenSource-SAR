#!/usr/bin/env python3
"""
Why does the water map look wrong?  python pipeline/diagnose_water.py --hotspot tonle-sap

Uses only what is already built (no downloads). Run planetary.py water-history first.
For each pass it prints what the radar measured over the area that is usually water
(JRC 1984-2020): how much has no radar value at all, and how bright the rest is,
next to the threshold we used. Paste the output to the team.
"""
import argparse
import json

import numpy as np
from PIL import Image

import exposure
import layers


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hotspot", default="tonle-sap")
    args = parser.parse_args()
    out = layers.DATA / "layers" / args.hotspot
    m = json.loads((out / "manifest.json").read_text())
    s = m["series"]
    cube = np.fromfile(out / s["file"], dtype="<f4").reshape(s["count"], s["height"], s["width"])
    f = s["factor"]
    print(f"{args.hotspot}: grid {s['full_width']}x{s['full_height']} at {m.get('grid_res')} m, inspector factor {f}")
    for i, frame in enumerate(m["frames"]):
        if "newwater" not in frame["files"]:
            raise SystemExit("Run: python pipeline/planetary.py water-history --hotspot " + args.hotspot)
        rgba = np.asarray(Image.open(out / frame["files"]["newwater"]).convert("RGBA"))
        usual = (rgba[..., 3] > 0) & ~(rgba[..., :3] == exposure.NEW_WATER_RGBA[:3]).all(axis=-1)
        usual = usual[f // 2::f, f // 2::f][:s["height"], :s["width"]]
        db = cube[i][:usual.shape[0], :usual.shape[1]]
        lake, land = db[usual], db[~usual]
        pct = lambda a: "none" if not np.isfinite(a).any() else " / ".join(f"{v:.1f}" for v in np.nanpercentile(a, [5, 50, 95]))
        print(f"{frame['date']}  threshold {frame['stats'].get('threshold_db')} dB, open water {frame['stats'].get('open_water_km2')} km²")
        print(f"   usually-water area: {100 * np.mean(~np.isfinite(lake)):.0f}% has no radar value; rest is {pct(lake)} dB (5th / middle / 95th)")
        print(f"   everywhere else:    {100 * np.mean(~np.isfinite(land)):.0f}% has no radar value; rest is {pct(land)} dB")


if __name__ == "__main__":
    main()
