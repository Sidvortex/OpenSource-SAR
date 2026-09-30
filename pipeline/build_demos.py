#!/usr/bin/env python3
"""Rebuild every SYNTHETIC demo layer and the STAC catalogue in one go: python pipeline/build_demos.py"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = [
    ["water_dance.py", "demo", "--hotspot", "tonle-sap"],
    ["quake.py", "demo", "--hotspot", "venezuela-coast"],
    ["quake.py", "demo", "--hotspot", "mexico-city"],
    ["backscatter.py", "demo", "--hotspot", "amazon-arc"],
    ["backscatter.py", "demo", "--hotspot", "punjab-haryana"],
    ["ice.py", "demo", "--hotspot", "shisper"],
    ["stac.py"],
]
for step in STEPS:
    print("\n>>", " ".join(step))
    subprocess.run([sys.executable, str(HERE / step[0]), *step[1:]], check=True, cwd=HERE)
shutil.rmtree(HERE / "work", ignore_errors=True)       # synthetic HDF5 files are only intermediate
print("\nAll demos rebuilt. Every one is labelled synthetic in the app.")
