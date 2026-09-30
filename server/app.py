"""
Optional self-hosted API (Part 8). Free to run on a laptop or any machine with Docker.
The public site works without it; this adds coverage for any box and on-demand processing.

    pip install -r pipeline/requirements.txt -r server/requirements.txt
    uvicorn server.app:app --port 8000

Keep it on your own machine or a trusted network: /api/process runs the pipelines.
"""
import json
import subprocess
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "pipeline"
sys.path.insert(0, str(PIPELINE))
import coverage_check as cc  # noqa: E402

app = FastAPI(title="SARabande API", description="Free, open-source companion API for SARabande.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
SCRIPTS = {"water": "water_dance.py", "ground": "quake.py", "fire": "backscatter.py", "farming": "backscatter.py", "ice": "ice.py"}
JOBS: dict = {}


def spots():
    return {s["id"]: s for s in json.loads((ROOT / "data" / "hotspots.json").read_text())["hotspots"]}


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/coverage")
def coverage(bbox: str = Query(..., description="west,south,east,north in degrees"),
             products: str = "GCOV,GUNW", start: str = cc.PROVISIONAL_START):
    try:
        west, south, east, north = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(400, "bbox must be west,south,east,north")
    area = {"label": "custom", "wkt": cc.bbox(west, south, east, north), "start": start, "end": None}
    dates = {}
    for product in products.split(","):
        rows = cc.dedupe([cc.to_row("custom", product, "PROVISIONAL", r) for r in cc.search(product, area, "PROVISIONAL", False)])
        dates[product] = sorted({r["date"] for r in rows})
    return {"bbox": [west, south, east, north], "dates": dates}


@app.post("/api/process/{hotspot}")
def process(hotspot: str):
    spot = spots().get(hotspot)
    if not spot:
        raise HTTPException(404, "unknown hotspot")
    job = uuid.uuid4().hex[:8]
    JOBS[job] = {"status": "running", "hotspot": hotspot, "log": ""}

    def run():
        result = subprocess.run([sys.executable, str(PIPELINE / SCRIPTS[spot["module"]]), "process", "--hotspot", hotspot],
                                capture_output=True, text=True, cwd=PIPELINE)
        JOBS[job] = {"status": "done" if result.returncode == 0 else "failed", "hotspot": hotspot,
                     "log": (result.stdout + result.stderr)[-4000:]}
    threading.Thread(target=run, daemon=True).start()
    return {"job": job}


@app.get("/api/jobs/{job}")
def job_status(job: str):
    if job not in JOBS:
        raise HTTPException(404, "unknown job")
    return JOBS[job]
