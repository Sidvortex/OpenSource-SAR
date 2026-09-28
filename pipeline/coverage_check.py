#!/usr/bin/env python3
"""
SARabande - week-one NISAR coverage check.

Finds which calibrated NISAR L-band products exist over each demo hero (or any
area you pass in), checks whether they are good enough to build on, and writes
a CSV of granules, a Markdown report and a coverage-calendar chart per area.

Searching needs no login. Downloading later needs a free NASA Earthdata login.

    pip install --upgrade asf_search matplotlib
    python coverage_check.py                      # all heroes
    python coverage_check.py --hero venezuela     # one hero
    python coverage_check.py --name jakarta --products GUNW GCOV \
        --wkt "POLYGON((106.6 -6.4,107.1 -6.4,107.1 -6.0,106.6 -6.0,106.6 -6.4))"
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import asf_search as asf
except ImportError:
    sys.exit("asf_search is missing: pip install --upgrade asf_search")

PROVISIONAL_START = "2026-06-17"             # first acquisition with calibrated products
INSTRUMENT_GAP = (date(2026, 7, 27), date(2026, 8, 10))  # permanent NISAR data gap
REPEAT_DAYS = 12
PAIR_PRODUCTS = {"GUNW", "GOFF", "RUNW", "RIFG", "ROFF"}  # products made from two passes
TIMESTAMP = re.compile(r"(\d{8})T\d{6}")


def bbox(lon_min, lat_min, lon_max, lat_max):
    """WKT polygon for a lon/lat box."""
    return (f"POLYGON(({lon_min} {lat_min},{lon_max} {lat_min},{lon_max} {lat_max},"
            f"{lon_min} {lat_max},{lon_min} {lat_min}))")


# Approximate areas of interest. Tighten them once you have looked at real scenes.
HEROES = {
    "venezuela": {
        "label": "Caracas and La Guaira coast, Venezuela (Tango)",
        "wkt": bbox(-68.6, 10.1, -66.6, 10.9),
        "start": "2026-06-01", "end": "2026-07-31",
        "products": ["GUNW", "GCOV"],
        "event": "2026-06-24",
        "rule": {"product": "GUNW", "test": "event_pairs", "min": 1,
                 "meaning": "12-day GUNW pairs spanning the Jun 24 earthquakes"},
    },
    "tonle_sap": {
        "label": "Tonle Sap, Cambodia (Waltz)",
        "wkt": bbox(103.6, 12.2, 104.7, 13.4),
        "start": PROVISIONAL_START, "end": None,
        "products": ["GCOV"],
        "rule": {"product": "GCOV", "test": "dates_on_one_stack", "min": 6,
                 "meaning": "GCOV dates on a single track and frame"},
    },
    "mexico_city": {
        "label": "Mexico City, Mexico (March)",
        "wkt": bbox(-99.35, 19.15, -98.85, 19.65),
        "start": PROVISIONAL_START, "end": None,
        "products": ["GUNW", "GCOV"],
        "rule": {"product": "GUNW", "test": "longest_chain", "min": 6,
                 "meaning": "back-to-back GUNW pairs on a single track and frame"},
    },
    "shisper": {
        "label": "Shisper Glacier, Karakoram, Pakistan (stretch hero)",
        "wkt": bbox(74.45, 36.28, 74.75, 36.50),
        "start": PROVISIONAL_START, "end": None,
        "products": ["GOFF", "GCOV"],
        "rule": {"product": "GOFF", "test": "dates_on_one_stack", "min": 4,
                 "meaning": "GOFF pixel-offset pairs on a single track and frame"},
    },
}


# ---------------------------------------------------------------- searching

def search(product, area, maturity, include_ur):
    kwargs = {"dataset": "NISAR", "processingLevel": product, "dataMaturity": maturity,
              "intersectsWith": area["wkt"], "start": area["start"]}
    if area.get("end"):
        kwargs["end"] = area["end"]
    if not include_ur:
        kwargs["productionConfiguration"] = "PR"   # standard products, not Urgent Response
    return asf.search(**kwargs)


def acquisition_dates(props):
    """Distinct acquisition dates in the scene name (pair products carry two passes)."""
    found = sorted({datetime.strptime(d, "%Y%m%d").date()
                    for d in TIMESTAMP.findall(props.get("sceneName") or "")})
    if not found and props.get("startTime"):
        found = [datetime.fromisoformat(props["startTime"].replace("Z", "+00:00")).date()]
    return found


def to_row(area_key, product, maturity, result):
    props = result.properties
    dates = acquisition_dates(props)
    first = dates[0] if dates else None
    second = None
    if product in PAIR_PRODUCTS and first:
        # skip timestamps that only cross midnight; the secondary pass is days later
        later = [d for d in dates if (d - first).days >= 6]
        second = later[0] if later else None
    size = 0
    if isinstance(props.get("bytes"), dict):
        size = sum(v.get("bytes", 0) for v in props["bytes"].values() if isinstance(v, dict))
    return {
        "area": area_key, "product": product, "maturity": maturity,
        "track": props.get("pathNumber"), "frame": props.get("frameNumber"),
        "direction": props.get("flightDirection") or "",
        "date": first.isoformat() if first else "",
        "secondary_date": second.isoformat() if second else "",
        "crid": props.get("crid") or "",
        "frame_coverage": props.get("frameCoverage") or "",
        "size_gb": round(size / 1e9, 2),
        "scene": props.get("sceneName") or "",
        "url": props.get("url") or "",
    }


def dedupe(rows):
    """Keep one row per acquisition (the highest release ID wins when reprocessed)."""
    best = {}
    for r in rows:
        key = (r["product"], r["track"], r["frame"], r["direction"], r["date"], r["secondary_date"])
        if key not in best or r["crid"] > best[key]["crid"]:
            best[key] = r
    return list(best.values())


# ---------------------------------------------------------------- analysis

def overlaps_gap(a, b):
    return a <= INSTRUMENT_GAP[1] and b >= INSTRUMENT_GAP[0]


def analyse_stack(product, rows, event=None):
    """Summarise one track/frame/direction stack of a product."""
    d = lambda s: date.fromisoformat(s)
    info = {"product": product, "n_items": len(rows), "flags": [], "event_pairs": [],
            "longest_chain": 0, "size_gb": round(sum(r["size_gb"] for r in rows), 1)}
    if product in PAIR_PRODUCTS:
        pairs = sorted({(r["date"], r["secondary_date"]) for r in rows if r["secondary_date"]})
        info["n_dates"] = len(pairs)
        info["first"] = pairs[0][0] if pairs else ""
        info["last"] = pairs[-1][1] if pairs else ""
        # longest run of back-to-back pairs (secondary of one = reference of the next)
        run = best = 0
        prev_sec = None
        for ref, sec in pairs:
            run = run + 1 if prev_sec == ref else 1
            best = max(best, run)
            if prev_sec and prev_sec != ref:
                gap = (d(ref) - d(prev_sec)).days
                why = " (instrument gap)" if overlaps_gap(d(prev_sec), d(ref)) else ""
                info["flags"].append(f"chain breaks {prev_sec} -> {ref}, {gap} days{why}")
            prev_sec = sec
        info["longest_chain"] = best
        if event:
            ev = d(event)
            info["event_pairs"] = [f"{a} -> {b}" for a, b in pairs if d(a) < ev < d(b)]
        long_pairs = [p for p in pairs if (d(p[1]) - d(p[0])).days > REPEAT_DAYS]
        if long_pairs:
            info["flags"].append(f"{len(long_pairs)} pair(s) longer than {REPEAT_DAYS} days")
    else:
        dates = sorted({r["date"] for r in rows if r["date"]})
        info["n_dates"] = len(dates)
        info["first"] = dates[0] if dates else ""
        info["last"] = dates[-1] if dates else ""
        for a, b in zip(dates, dates[1:]):
            gap = (d(b) - d(a)).days
            if gap > REPEAT_DAYS + 2:
                why = " (instrument gap)" if overlaps_gap(d(a), d(b)) else ""
                info["flags"].append(f"gap {a} -> {b}, {gap} days{why}")
    if any(r["frame_coverage"] == "PARTIAL" for r in rows):
        info["flags"].append("some frames only partially covered")
    return info


def analyse_area(area, rows):
    stacks = defaultdict(list)
    for r in rows:
        stacks[(r["product"], r["track"], r["frame"], r["direction"])].append(r)
    results = []
    for (product, track, frame, direction), stack_rows in sorted(stacks.items(), key=str):
        info = analyse_stack(product, stack_rows, area.get("event"))
        info["stack"] = f"T{track} F{frame} {direction}".strip()
        info["rows"] = stack_rows
        results.append(info)
    return results


def verdict(area, stacks):
    rule = area.get("rule")
    if not rule:
        return None, None
    mine = [s for s in stacks if s["product"] == rule["product"]]
    if rule["test"] == "event_pairs":
        score = sum(len(s["event_pairs"]) for s in mine)
    elif rule["test"] == "longest_chain":
        score = max((s["longest_chain"] for s in mine), default=0)
    else:
        score = max((s["n_dates"] for s in mine), default=0)
    return score >= rule["min"], score


# ---------------------------------------------------------------- output

def calendar_plot(key, area, stacks, out_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        return None
    if not stacks:
        return None
    fig, ax = plt.subplots(figsize=(11, 0.55 * len(stacks) + 2.2))
    seen = []
    for y, s in enumerate(stacks):
        rows = sorted((r for r in s["rows"] if r["date"]), key=lambda r: r["date"])
        for i, r in enumerate(rows):
            a = date.fromisoformat(r["date"])
            seen.append(a)
            if r["secondary_date"]:
                b = date.fromisoformat(r["secondary_date"])
                seen.append(b)
                off = 0.12 if i % 2 else -0.12   # alternate so back-to-back pairs stay visible
                ax.plot([a, b], [y + off, y + off], lw=3, color="tab:blue", alpha=0.7,
                        solid_capstyle="butt")
            else:
                ax.plot([a], [y], "o", ms=6, color="tab:green")
    if seen and overlaps_gap(min(seen), max(seen)):
        ax.axvspan(INSTRUMENT_GAP[0], INSTRUMENT_GAP[1], color="grey", alpha=0.2,
                   label="instrument gap")
    if area.get("event"):
        ax.axvline(date.fromisoformat(area["event"]), ls="--", color="crimson", label="event")
    ax.set_yticks(range(len(stacks)))
    ax.set_yticklabels([f"{s['product']}  {s['stack']}" for s in stacks])
    ax.set_ylim(-0.6, len(stacks) - 0.4)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.set_title(f"NISAR coverage: {area['label']}\n(bars = 12-day pairs, dots = single passes)",
                 fontsize=10)
    if ax.get_legend_handles_labels()[0]:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=8,
                  frameon=False)
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    path = out_dir / f"{key}_calendar.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser(description="Check NISAR coverage for SARabande hotspots.")
    ap.add_argument("--hero", choices=[*HEROES, "all"], default="all")
    ap.add_argument("--wkt", help="custom area as a WKT polygon, longitude first")
    ap.add_argument("--name", default="custom", help="label for a custom area")
    ap.add_argument("--products", nargs="+", default=["GUNW", "GCOV"], help="for a custom area")
    ap.add_argument("--start", default=PROVISIONAL_START, help="for a custom area")
    ap.add_argument("--end", help="for a custom area")
    ap.add_argument("--maturity", choices=["PROVISIONAL", "BETA"], default="PROVISIONAL")
    ap.add_argument("--include-ur", action="store_true", help="also list Urgent Response products")
    ap.add_argument("--out", default="coverage_out")
    ap.add_argument("--no-plots", action="store_true")
    args = ap.parse_args()

    if args.wkt:
        areas = {args.name: {"label": args.name, "wkt": args.wkt, "start": args.start,
                             "end": args.end, "products": args.products}}
    else:
        areas = HEROES if args.hero == "all" else {args.hero: HEROES[args.hero]}

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    all_rows, report = [], [f"# NISAR coverage check ({args.maturity})",
                            f"Run on {date.today().isoformat()}. Areas are approximate boxes.", ""]

    for key, area in areas.items():
        print(f"\n== {area['label']}")
        rows = []
        for product in area["products"]:
            try:
                results = search(product, area, args.maturity, args.include_ur)
            except Exception as exc:   # network, API change or an outdated asf_search
                print(f"   {product}: search failed ({exc}). Try: pip install --upgrade asf_search")
                continue
            found = dedupe([to_row(key, product, args.maturity, r) for r in results])
            print(f"   {product}: {len(found)} products")
            rows.extend(found)
        all_rows.extend(rows)

        stacks = analyse_area(area, rows)
        ok, score = verdict(area, stacks)
        report += [f"## {area['label']}", ""]
        if ok is not None:
            status = "PASS" if ok else "FAIL"
            line = f"**{status}**: {score} {area['rule']['meaning']} (need {area['rule']['min']})."
            print("   " + line.replace("**", ""))
            report += [line, ""]
        report += ["| Product | Stack | Items | First | Last | Longest chain | Event pairs | Size (GB) | Flags |",
                   "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for s in stacks:
            report.append(f"| {s['product']} | {s['stack']} | {s['n_dates']} | {s['first']} | {s['last']} "
                          f"| {s['longest_chain'] or ''} | {'; '.join(s['event_pairs'])} "
                          f"| {s['size_gb']} | {'; '.join(s['flags'])} |")
        if not stacks:
            report.append("| none found | | | | | | | | |")
        if not args.no_plots:
            plot = calendar_plot(key, area, stacks, out_dir)
            if plot:
                report += ["", f"![coverage calendar]({plot.name})"]
        report.append("")

    csv_path = out_dir / "granules.csv"
    fields = ["area", "product", "maturity", "track", "frame", "direction", "date",
              "secondary_date", "crid", "frame_coverage", "size_gb", "scene", "url"]
    with open(csv_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rows)
    (out_dir / "report.md").write_text("\n".join(report))
    print(f"\nWrote {csv_path}, {out_dir / 'report.md'} and calendar charts in {out_dir}/")


if __name__ == "__main__":
    main()
