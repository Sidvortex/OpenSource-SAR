"""
Shared helpers for every module's web layers.

Each place gets data/layers/<place>/manifest.json in one general format:
frames (single dates, or pairs of dates), named layers with plain-words
legends, and statistics per frame. The site reads only this format, so new
modules need no new front-end code for the basics.
"""
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image
from matplotlib import colormaps

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WORK = ROOT / "pipeline" / "work"


def load_spot(spot_id):
    spots = json.loads((DATA / "hotspots.json").read_text())["hotspots"]
    for spot in spots:
        if spot["id"] == spot_id:
            return spot
    sys.exit(f"No hotspot called {spot_id!r}. Choose one of: {', '.join(s['id'] for s in spots)}")


def layer_folder(spot_id):
    out = DATA / "layers" / spot_id
    out.mkdir(parents=True, exist_ok=True)
    for old in list(out.glob("*.png")) + list(out.glob("*.webp")):
        old.unlink()
    return out


def save_ramp(values, vmin, vmax, cmap, path, webp=False):
    """Continuous values through a matplotlib colour map; NaN becomes transparent."""
    norm = np.clip((values - vmin) / (vmax - vmin), 0, 1)
    rgba = (colormaps[cmap](np.nan_to_num(norm)) * 255).astype("uint8")
    rgba[..., 3] = np.where(np.isfinite(values), 255, 0)
    image = Image.fromarray(rgba)
    if webp:
        image.save(path, "WEBP", quality=80, method=6)
    else:
        image.save(path, optimize=True)


def save_cyclic(values, period, cmap, path):
    """Wrap values into repeating colour cycles, like interferogram fringes."""
    save_ramp(np.mod(values, period) / period, 0.0, 1.0, cmap, path)


def save_classes(classes, colours, path):
    """classes: {name: boolean mask}; colours: {name: (r, g, b, a)}. Later classes paint over earlier ones."""
    shape = next(iter(classes.values())).shape
    rgba = np.zeros(shape + (4,), dtype="uint8")
    for name, mask in classes.items():
        rgba[mask] = colours[name]
    Image.fromarray(rgba).save(path, optimize=True)


def ramp_colours(cmap, n=5):
    return ["#%02x%02x%02x" % tuple(int(c * 255) for c in colormaps[cmap](i / (n - 1))[:3]) for i in range(n)]


def write_manifest(spot, out, manifest):
    manifest = {"hotspot": spot["id"], "created": date.today().isoformat(), **manifest}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    update_index(spot["id"], manifest["module"], manifest["synthetic"])
    print(f"Wrote {len(manifest['frames'])} frames to {out.relative_to(ROOT)}")
    return manifest


def update_index(spot_id, module, synthetic):
    """data/layers/index.json tells the site which places have layers, without guessing URLs."""
    path = DATA / "layers" / "index.json"
    index = json.loads(path.read_text()) if path.exists() else {"layers": {}}
    index["layers"][spot_id] = {"module": module, "synthetic": synthetic, "updated": date.today().isoformat()}
    path.write_text(json.dumps(index, indent=2) + "\n")
