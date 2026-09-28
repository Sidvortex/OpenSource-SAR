# SARabande

Watch Earth's surface dance: sinking cities, swelling lakes, burning forests and flowing glaciers, measured by the NASA-ISRO NISAR radar every 12 days.

Built for the NASA Space Apps Challenge 2026, challenge "Dancing with the SARs".

**Motto: free and open, end to end.** Every line of code is open source, every dataset is free, and nothing costs money: no paid APIs, no API keys in the app, no server bill. Anyone can fork it, run it and check it.

## Where the build is

SARabande grows in ten parts. Every part ends with a working public site.

| Part | What ships | Status |
| --- | --- | --- |
| 1 | Globe and atlas: 19 hotspots, dance legend, place cards, weekly NISAR coverage check, automatic deploys | **This version** |
| 2 | Water dance: Tonle Sap water extent from GCOV, the Place view and time slider | Next |
| 3 | Earthquake: the Venezuela GUNW pair, fringes and displacement, before/after swipe | |
| 4 | Point inspector and the dance classifier | |
| 5 | Ground-motion time series, MintPy, GNSS validation | |
| 6 | Explanations at three reading levels, story mode, "How radar sees" | |
| 7 | Fire, farming and ice modules, event markers | |
| 8 | Draw any area on Earth, optional self-hosted API, exposure layer | |
| 9 | Alerts (RSS and ntfy), leaderboard, export, STAC catalogue, citizen reports | |
| 10 | Machine learning, sonification, optional in-browser model, offline mode, submission | |

## Run it on your computer

You need Node.js 20 or newer.

```bash
cd web
npm install
npm run dev
```

Open the address it prints (usually http://localhost:5173). `npm run dev` first copies the shared `data/` folder into the site.

## Check which NISAR data exists

You need Python 3.10 or newer. Searching NISAR is free and needs no login.

```bash
pip install -r pipeline/requirements.txt
python pipeline/update_coverage.py          # refreshes data/coverage.json for every hotspot
```

`update_coverage.py` asks NASA's public ASF search which calibrated (PROVISIONAL) NISAR products cover each hotspot, and whether there are enough to build on. The site shows the result on each place card.

`coverage_check.py` is the detailed version for one area. It writes a granule CSV, a Markdown report and a coverage-calendar chart:

```bash
python pipeline/coverage_check.py --hero tonle_sap
python pipeline/coverage_check.py --name jakarta --products GUNW GCOV \
  --wkt "POLYGON((106.6 -6.4,107.1 -6.4,107.1 -6.0,106.6 -6.0,106.6 -6.4))"
```

Downloading NISAR files (from Part 2 on) needs a free NASA Earthdata login.

## Put it online for free

1. Push this folder to a **public** GitHub repository.
2. In the repository, open Settings, then Pages, and set the source to **GitHub Actions**.
3. In Settings, then Actions, then General, allow workflows **read and write** permissions, so the weekly coverage check can commit its results.
4. Push to `main`. The "Deploy site" workflow builds the app and publishes it. The "Check NISAR coverage" workflow runs every Monday, or on demand from the Actions tab.

Both workflows are free for public repositories.

## Settings

Create `web/.env` to change these (both optional):

```
VITE_REPO_URL=https://github.com/your-team/sarabande
VITE_BASEMAP_STYLE=https://tiles.openfreemap.org/styles/positron
```

If the basemap cannot load, the globe falls back to public-domain Natural Earth outlines shipped with the site, so the demo still works offline.

## How the repository is laid out

```
data/          Shared data: hotspots.json, coverage.json, basemap/land.geojson
pipeline/      Python: coverage_check.py and update_coverage.py (later: processing)
web/           React, TypeScript and Vite app with a MapLibre globe
.github/       Free GitHub Actions: deploy to Pages, weekly coverage check
```

## Free and open: licences

| Piece | Licence |
| --- | --- |
| SARabande's own code | MIT (see LICENSE) |
| MapLibre GL JS | BSD-3-Clause |
| React | MIT |
| Vite | MIT |
| TypeScript | Apache-2.0 |
| Archivo and Source Serif 4 fonts (via Fontsource) | SIL Open Font License |
| asf_search | BSD-3-Clause |
| matplotlib | PSF-based, BSD-compatible |

## Data and credits

- NISAR L-band data: NASA/JPL and ISRO, distributed free by the Alaska Satellite Facility DAAC.
- Basemap: OpenFreeMap, with map data from OpenStreetMap contributors (ODbL).
- Offline land outlines: Natural Earth (public domain).
- Hotspot areas are approximate boxes. Tighten them after looking at real scenes.

SARabande is informational. It is not an official warning system.

## Use of AI

Parts of this code were drafted with help from an AI coding assistant (Claude). Space Apps asks teams to say where and how AI was used, so list this on the project page.
