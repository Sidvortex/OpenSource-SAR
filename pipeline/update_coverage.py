#!/usr/bin/env python3
"""
Part 1: refresh data/coverage.json for every hotspot in data/hotspots.json.

Uses NASA's free, public ASF search (no login, no key). Run it by hand or let
the weekly GitHub Action do it:  python pipeline/update_coverage.py
"""
import json
import sys
from datetime import date
from pathlib import Path

import coverage_check as cc

ROOT = Path(__file__).resolve().parents[1]
HOTSPOTS = ROOT / "data" / "hotspots.json"
OUT = ROOT / "data" / "coverage.json"
MATURITY = "PROVISIONAL"

# What "good enough to build on" means for each module, unless a hotspot overrides it.
DEFAULT_RULES = {
    "ground": {"product": "GUNW", "test": "longest_chain", "min": 6,
               "meaning": "back-to-back 12-day GUNW pairs on one track and frame"},
    "water": {"product": "GCOV", "test": "dates_on_one_stack", "min": 6,
              "meaning": "GCOV passes on one track and frame"},
    "fire": {"product": "GCOV", "test": "dates_on_one_stack", "min": 6,
             "meaning": "GCOV passes on one track and frame"},
    "farming": {"product": "GCOV", "test": "dates_on_one_stack", "min": 6,
                "meaning": "GCOV passes on one track and frame"},
    "ice": {"product": "GOFF", "test": "dates_on_one_stack", "min": 4,
            "meaning": "GOFF pixel-offset pairs on one track and frame"},
}


def area_for(spot):
    west, south, east, north = spot["bbox"]
    window = spot.get("window", {})
    return {
        "label": spot["name"],
        "wkt": cc.bbox(west, south, east, north),
        "start": window.get("start", cc.PROVISIONAL_START),
        "end": window.get("end"),
        "products": spot["products"],
        "event": spot.get("event"),
        "rule": spot.get("rule") or DEFAULT_RULES[spot["module"]],
    }


def summarise(area, stacks):
    products = {}
    for product in area["products"]:
        mine = [s for s in stacks if s["product"] == product]
        best = max(mine, key=lambda s: (s["longest_chain"], s["n_dates"]), default=None)
        products[product] = {
            "stacks": len(mine),
            "items": sum(s["n_dates"] for s in mine),
            "best_stack": best["stack"] if best else None,
            "best_items": best["n_dates"] if best else 0,
            "first": min((s["first"] for s in mine if s["first"]), default=None),
            "last": max((s["last"] for s in mine if s["last"]), default=None),
            "size_gb": round(sum(s["size_gb"] for s in mine), 1),
        }
    return products


def main():
    spots = json.loads(HOTSPOTS.read_text())["hotspots"]
    result = {"checked": date.today().isoformat(), "maturity": MATURITY, "hotspots": {}}
    failures = 0
    for spot in spots:
        area = area_for(spot)
        rows, errors = [], []
        for product in area["products"]:
            try:
                found = cc.search(product, area, MATURITY, include_ur=False)
                rows += cc.dedupe([cc.to_row(spot["id"], product, MATURITY, r) for r in found])
            except Exception as exc:  # network trouble or an API change
                errors.append(f"{product}: {exc}")
        stacks = cc.analyse_area(area, rows)
        ok, score = cc.verdict(area, stacks)
        verdict = None if errors and not rows else ("pass" if ok else "fail")
        failures += verdict != "pass"
        result["hotspots"][spot["id"]] = {
            "verdict": verdict,
            "score": score,
            "need": area["rule"]["min"],
            "rule": area["rule"]["meaning"],
            "products": summarise(area, stacks),
            "errors": errors,
        }
        print(f"{spot['name']:<40} {verdict or 'error':<6} {score} ({area['rule']['meaning']})")
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(f"\nWrote {OUT.relative_to(ROOT)}; {len(spots) - failures} of {len(spots)} hotspots pass.")


if __name__ == "__main__":
    sys.exit(main())
