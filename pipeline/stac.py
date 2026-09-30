#!/usr/bin/env python3
"""Part 9: a static STAC 1.0 catalogue of every web layer, so other tools can find and reuse them."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYERS, OUT = ROOT / "data" / "layers", ROOT / "data" / "stac"
MEDIA = {".png": "image/png", ".webp": "image/webp", ".bin": "application/octet-stream"}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = {"type": "Catalog", "stac_version": "1.0.0", "id": "sarabande",
               "description": "SARabande web layers derived from NISAR. Check each item's 'synthetic' flag.",
               "links": [{"rel": "root", "href": "./catalog.json", "type": "application/json"}]}
    for manifest_path in sorted(LAYERS.glob("*/manifest.json")):
        m = json.loads(manifest_path.read_text())
        lons, lats = [c[0] for c in m["bounds"]], [c[1] for c in m["bounds"]]
        bbox = [min(lons), min(lats), max(lons), max(lats)]
        ring = [[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]], [bbox[0], bbox[1]]]
        for frame in m["frames"]:
            item_id = f"{m['hotspot']}_{frame.get('start', '')}{'_' if frame.get('start') else ''}{frame['date']}"
            assets = {key: {"href": f"../layers/{m['hotspot']}/{name}", "type": MEDIA.get(Path(name).suffix, "application/octet-stream"),
                            "roles": ["visual"]} for key, name in frame["files"].items()}
            item = {"type": "Feature", "stac_version": "1.0.0", "id": item_id, "bbox": bbox,
                    "geometry": {"type": "Polygon", "coordinates": [ring]},
                    "properties": {"datetime": f"{frame['date']}T00:00:00Z", "start_datetime": f"{frame.get('start', frame['date'])}T00:00:00Z",
                                   "end_datetime": f"{frame['date']}T00:00:00Z", "sarabande:module": m["module"],
                                   "sarabande:synthetic": m["synthetic"], "sarabande:stats": frame["stats"],
                                   "sarabande:sources": frame.get("sources", [])},
                    "assets": assets,
                    "links": [{"rel": "root", "href": "./catalog.json"}, {"rel": "parent", "href": "./catalog.json"}]}
            (OUT / f"{item_id}.json").write_text(json.dumps(item, indent=1))
            catalog["links"].append({"rel": "item", "href": f"./{item_id}.json", "type": "application/geo+json"})
    (OUT / "catalog.json").write_text(json.dumps(catalog, indent=1))
    print(f"STAC catalogue: {len(catalog['links']) - 1} items in {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
