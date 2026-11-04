#!/usr/bin/env python3
"""
Ground reports: people's observations, filed through the repository's issue form.

    python pipeline/reports.py            # reads issues labelled "ground-report"

Writes data/reports.json. Reports are public GitHub issues, so anything here is
already public. Only open issues are used; close an issue to remove a report.
Set GITHUB_TOKEN to raise the rate limit (the weekly workflow does this for you).
"""
import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = os.environ.get("GITHUB_REPOSITORY", "Sidvortex/OpenSource-SAR")
LATLON = re.compile(r"(-?\d{1,2}(?:\.\d+)?)\s*[, ]\s*(-?\d{1,3}(?:\.\d+)?)")


def fetch_issues(repo=REPO, token=None):
    url = f"https://api.github.com/repos/{repo}/issues?labels=ground-report&state=open&per_page=100"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "OpenSource-SAR"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def sections(body):
    """Issue forms render as '### Label' followed by the answer."""
    out, current = {}, None
    for line in (body or "").splitlines():
        if line.startswith("### "):
            current = line[4:].strip().lower()
            out[current] = []
        elif current is not None:
            out[current].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def parse(issue):
    if "pull_request" in issue:
        return None
    s = sections(issue.get("body"))
    place = s.get("place", "")
    report = {"id": issue["number"], "url": issue["html_url"], "title": issue["title"], "place": place,
              "date": s.get("date you saw it", ""), "kind": s.get("what did you see?", ""),
              "details": s.get("details", "")[:400], "lon": None, "lat": None}
    m = LATLON.search(place)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            report["lat"], report["lon"] = lat, lon
    return report


def main():
    issues = fetch_issues(token=os.environ.get("GITHUB_TOKEN"))
    reports = [r for r in (parse(i) for i in issues) if r]
    (ROOT / "data" / "reports.json").write_text(json.dumps({"repo": REPO, "reports": reports}, indent=1) + "\n")
    print(f"{len(reports)} ground reports, {sum(r['lat'] is not None for r in reports)} with coordinates")


if __name__ == "__main__":
    main()
