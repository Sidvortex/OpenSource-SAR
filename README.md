# SARabande

Watch Earth's surface dance: sinking cities, swelling lakes, burning forests, growing crops and surging glaciers, measured by the NASA-ISRO NISAR radar every 12 days. Built for the NASA Space Apps Challenge 2026, "Dancing with the SARs".

**Motto: free and open, end to end.** Every line of code is open source (MIT), every dataset is free, and nothing costs money: no paid APIs, no API keys in the app, no server bill.

> **Demo data is synthetic.** Every layer shipped in this repository is a clearly labelled synthetic demo built by the same code that processes real NISAR files. The app says so on every screen that shows one. [DEPLOY.md](DEPLOY.md) explains how to replace each one with real measurements.

## What's inside (all ten parts)

| Part | Feature |
| --- | --- |
| 1 | 3D globe of 19 hotspots whose markers pulse in their dance rhythm; place cards; weekly NISAR coverage check |
| 2 | Water: Tonle Sap flood extent from GCOV, time slider and chart, 3D before/after showcase with "Play reveal" |
| 3 | Earthquakes: Venezuela interferograms as movement, rainbow fringes and data quality |
| 4 | Click-any-pixel inspector with uncertainty; the dance classifier (Python and TypeScript, one shared test set) |
| 5 | Sinking ground: Mexico City totals and velocity, the instrument gap bridged and flagged, GNSS validation |
| 6 | Explanations at three reading levels in English, Hindi and Spanish; guided stories; "How radar sees" with a quiz |
| 7 | Fire (Amazon burn scars), farming (Punjab crop season) and ice (Shisper glacier speed) |
| 8 | "Check any area" from NASA's free catalogue; optional self-hosted API with Docker |
| 9 | Shareable links to any place, layer and date; image and CSV export; RSS and ntfy alerts; STAC catalogue; ground reports |
| 10 | "Hear it" sonification; offline mode; accessibility throughout |

## Run it

```bash
cd web && npm install && npm run dev          # the site, with every demo layer
python pipeline/build_demos.py                 # rebuild all synthetic demos (needs pipeline/requirements.txt)
python pipeline/dance.py --test && (cd web && npm run test:dance)   # both classifiers, one shared test set
```

Python 3.10+ and Node 20+. Install the pipeline with `pip install -r pipeline/requirements.txt`.

## Real NISAR data

Searching is free and needs no login; downloading needs a free NASA Earthdata login. Full steps are in [DEPLOY.md](DEPLOY.md).

| Module | Download | Process |
| --- | --- | --- |
| Water | `python pipeline/water_dance.py download --hotspot tonle-sap` | `python pipeline/water_dance.py process --hotspot tonle-sap` |
| Earthquake or sinking ground | `python pipeline/quake.py download --hotspot mexico-city` | `python pipeline/quake.py process --hotspot mexico-city` |
| Fire or farming | GCOV, as for water | `python pipeline/backscatter.py process --hotspot amazon-arc` |
| Ice | GOFF from ASF Vertex into `pipeline/work/shisper/` | `python pipeline/ice.py process --hotspot shisper` |

Check any area with `python pipeline/coverage_check.py --name my-area --wkt "POLYGON((...))"`, and all hotspots with `python pipeline/update_coverage.py`.

## Layout

```
data/        hotspots, coverage, explain.json (translations), stories.json, layers/<place>/, stac/, feed.xml
pipeline/    coverage checks; nisar_io (HDF5 reader); water_dance, quake + ground + gnss, backscatter, ice;
             dance (classifier); layers (shared output); stac; build_demos
web/         React + TypeScript + Vite + MapLibre app; src/dance.ts mirrors pipeline/dance.py
server/      optional FastAPI companion (Docker); the site never depends on it
.github/     free Actions: deploy to Pages, weekly coverage and alerts, tests; ground-report issue form
```

## Free and open: licences

Our code: MIT. MapLibre GL JS (BSD-3-Clause), React (MIT), Vite (MIT), TypeScript (Apache-2.0), Archivo and Source Serif 4 (SIL OFL), asf_search, NumPy, SciPy, h5py, rasterio (BSD-3-Clause), GDAL (MIT), matplotlib (PSF-based), Pillow (MIT-CMU), FastAPI (MIT), Uvicorn (BSD-3-Clause).

Data: NISAR (NASA/JPL and ISRO, via ASF DAAC, free); OpenFreeMap basemap with OpenStreetMap data (ODbL); Natural Earth (public domain); AWS Open Data Terrain Tiles; GNSS format from the Nevada Geodetic Laboratory. SARabande is informational, not an official warning system.

## Use of AI

Parts of this code were drafted with help from an AI coding assistant (Claude). Space Apps asks teams to disclose this on the project page.
