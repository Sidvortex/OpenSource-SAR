#!/usr/bin/env python3
"""
Check every place's layers before they ship:  python pipeline/validate.py

  * manifest.json matches data/manifest.schema.json;
  * every file a frame names exists;
  * series cubes have exactly count x height x width float32 values;
  * every layer id a frame uses is declared, and index.json lists the place.
Exits non-zero with a list of problems, so CI blocks a broken push.
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
LAYERS = ROOT / "data" / "layers"


def problems_for(folder, validator, index):
    out = []
    manifest = json.loads((folder / "manifest.json").read_text())
    for error in validator.iter_errors(manifest):
        out.append(f"schema: {'/'.join(map(str, error.path)) or '(top)'}: {error.message}")
    declared = {layer["id"] for layer in manifest.get("layers", [])}
    for i, frame in enumerate(manifest.get("frames", [])):
        for key, name in frame.get("files", {}).items():
            if key not in declared:
                out.append(f"frame {i}: file key '{key}' has no matching layer")
            if not (folder / name).exists():
                out.append(f"frame {i}: missing file {name}")
    series = manifest.get("series")
    if series:
        expected = series["count"] * series["height"] * series["width"] * 4
        for key in ("file", "sigma_file"):
            if key in series:
                path = folder / series[key]
                if not path.exists():
                    out.append(f"series: missing {series[key]}")
                elif path.stat().st_size != expected:
                    out.append(f"series: {series[key]} is {path.stat().st_size} bytes, expected {expected}")
    if manifest.get("hotspot") not in index:
        out.append("index.json does not list this place")
    return out


def main():
    validator = Draft202012Validator(json.loads((ROOT / "data" / "manifest.schema.json").read_text()))
    index = json.loads((LAYERS / "index.json").read_text())["layers"]
    total = 0
    for folder in sorted(p for p in LAYERS.iterdir() if (p / "manifest.json").exists()):
        problems = problems_for(folder, validator, index)
        total += len(problems)
        print(f"{'ok  ' if not problems else 'FAIL'} {folder.name}")
        for p in problems:
            print(f"     {p}")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
