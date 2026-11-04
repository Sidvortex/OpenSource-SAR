# Open Source SAR

Watch Earth's surface dance: sinking cities, swelling lakes, burning forests, growing crops and surging glaciers, measured by the NASA-ISRO NISAR radar every 12 days. Repository: https://github.com/Sidvortex/OpenSource-SAR. Built for the NASA Space Apps Challenge 2026, "Dancing with the SARs".

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

### Final-version extras

| Feature | What it does |
| --- | --- |
| Also happened | Earthquakes (USGS, M4.5+) and fires (NASA FIRMS, optional free key) marked on the time chart, with daily rain (Open-Meteo) as bars |
| Radar vs optical | An "Optical" button swaps the radar layer for NASA GIBS true colour on the same date, on the globe and in 3D, to show the clouds radar sees through |
| People on changed ground | WorldPop or GHSL population summed where water, fire or ground motion changed (a count of residents, not of people harmed) |
| MintPy import | Brings a corrected MintPy time series in as a ground-motion place |
| Ground reports on the map | GitHub issues from the report form appear as pins, and in the place card |
| Real-data smoke test | Downloads one small real product per type and tests our readers |
| Contract checks | `data/manifest.schema.json`, `pipeline/validate.py` and pipeline tests, all in CI |

## Run it

```bash
cd web && npm install && npm run dev          # the site, with every demo layer
python pipeline/build_demos.py                 # rebuild all synthetic demos (needs pipeline/requirements.txt)
python pipeline/dance.py --test && (cd web && npm run test:dance)   # both classifiers, one shared test set
python -m pytest pipeline/tests -q && python pipeline/validate.py     # pipeline tests and the manifest contract
```

Python 3.10+ and Node 20+. Install the pipeline with `pip install -r pipeline/requirements-dev.txt` (on Arch-based systems, add `--break-system-packages`).

## Real NISAR data

Searching is free and needs no login; downloading needs a free NASA Earthdata login. Full steps are in [DEPLOY.md](DEPLOY.md).

| Module | Download | Process |
| --- | --- | --- |
| Water | `python pipeline/water_dance.py download --hotspot tonle-sap` | `python pipeline/water_dance.py process --hotspot tonle-sap` |
| Earthquake or sinking ground | `python pipeline/quake.py download --hotspot mexico-city` | `python pipeline/quake.py process --hotspot mexico-city` |
| Fire or farming | GCOV, as for water | `python pipeline/backscatter.py process --hotspot amazon-arc` |
| Ice | GOFF from ASF Vertex into `pipeline/work/shisper/` | `python pipeline/ice.py process --hotspot shisper` |

Check any area with `python pipeline/coverage_check.py --name my-area --wkt "POLYGON((...))"`, and all hotspots with `python pipeline/update_coverage.py`. Before processing, run `python pipeline/smoke_test.py` to check our readers against real files.

| Extra | Command |
| --- | --- |
| Context events and rain | `python pipeline/context.py [--hotspot X]` (set `FIRMS_MAP_KEY` for fires) |
| People on changed ground | `python pipeline/exposure.py --hotspot X --population worldpop.tif` |
| MintPy time series | `python pipeline/mintpy_import.py --hotspot X --timeseries geo_timeseries.h5 --velocity geo_velocity.h5` |
| Ground reports | `python pipeline/reports.py` |

## Layout

```
data/        hotspots, coverage, explain.json, stories.json, manifest.schema.json, reports.json,
             layers/<place>/ (manifest, images, series, context.json), stac/, feed.xml
pipeline/    coverage checks; nisar_io (HDF5 reader); water_dance, quake + ground + gnss, backscatter, ice;
             dance (classifier); layers (shared output); context, exposure, mintpy_import, reports;
             smoke_test; stac; validate; build_demos; tests/
web/         React + TypeScript + Vite + MapLibre app; src/dance.ts mirrors pipeline/dance.py
server/      optional FastAPI companion (Docker); the site never depends on it
.github/     free Actions: deploy to Pages, weekly update (coverage, context, reports), tests; issue form
```

## Free and open: licences

Our code: MIT. MapLibre GL JS (BSD-3-Clause), React (MIT), Vite (MIT), TypeScript (Apache-2.0), Archivo and Source Serif 4 (SIL OFL), asf_search, NumPy, SciPy, h5py, rasterio (BSD-3-Clause), GDAL (MIT), matplotlib (PSF-based), Pillow (MIT-CMU), FastAPI (MIT), Uvicorn (BSD-3-Clause), jsonschema (MIT), pytest (MIT). MintPy (GPL-3.0) is an optional separate tool; we only read its output files.

Data: NISAR (NASA/JPL and ISRO, via ASF DAAC, free); OpenFreeMap basemap with OpenStreetMap data (ODbL); Natural Earth (public domain); AWS Open Data Terrain Tiles; GNSS format from the Nevada Geodetic Laboratory; USGS earthquake catalogue (public domain); weather data by Open-Meteo.com (CC BY 4.0); NASA GIBS imagery and NASA FIRMS fire data (free and open; NASA asks for attribution, which the app shows); WorldPop (CC BY 4.0) or JRC GHSL population. Open Source SAR is informational, not an official warning system.

Ideas we've parked because they cost money (a SatDump ground station, a desk display) are in [ROADMAP.md](ROADMAP.md). The project page text and video script are in [SUBMISSION.md](SUBMISSION.md).

## Use of AI

Parts of this code were drafted with help from an AI coding assistant (Claude). Space Apps asks teams to disclose this on the project page.
