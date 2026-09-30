# SARabande

Watch Earth's surface dance: sinking cities, swelling lakes, burning forests and flowing glaciers, measured by the NASA-ISRO NISAR radar every 12 days.

Built for the NASA Space Apps Challenge 2026, challenge "Dancing with the SARs".

**Motto: free and open, end to end.** Every line of code is open source, every dataset is free, and nothing costs money: no paid APIs, no API keys in the app, no server bill. Anyone can fork it, run it and check it.

## Where the build is

SARabande grows in ten parts. Every part ends with a working public site.

| Part | What ships | Status |
| --- | --- | --- |
| 1 | Globe and atlas: 19 hotspots, dance legend, place cards, weekly NISAR coverage check, automatic deploys | Done |
| 2 | Water dance: Tonle Sap water extent from GCOV, time slider and chart, and the 3D before/after showcase | Done |
| 3 | Earthquake: Venezuela GUNW pairs as fringes, movement and data quality, compared in the 3D showcase | Done |
| 4 | Point inspector and the dance classifier | **This version** |
| 5 | Ground-motion time series, MintPy, GNSS validation | Next |
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

## Part 2: the water dance

The site ships with a **synthetic demo** for Tonle Sap so every screen works before any download. It grows the real lake outline (Natural Earth, public domain) through a pretend monsoon, and the app labels it "Synthetic demo data, not NISAR measurements" everywhere it appears. Rebuild it with:

```bash
python pipeline/water_dance.py demo --hotspot tonle-sap
```

To replace it with real NISAR measurements, get a free Earthdata login at urs.earthdata.nasa.gov, then:

```bash
export EARTHDATA_USERNAME=you EARTHDATA_PASSWORD=secret     # or EARTHDATA_TOKEN=...
python pipeline/water_dance.py download --hotspot tonle-sap --max 12
python pipeline/water_dance.py process --hotspot tonle-sap
```

`download` picks the track and frame with the most passes. GCOV files are large (several GB each), so check your disk space, or run it in ASF OpenSARLab next to the archive. `process` reads only the part of each file that covers the lake. It maps open water (dark to radar) and likely flooded vegetation (bright from double bounce), then writes small PNG layers and a `manifest.json` to `data/layers/tonle-sap/`. Commit those and the site updates.

If a real file's layout differs from what the reader expects, it stops with a clear message. Run `python pipeline/water_dance.py inspect FILE.h5` to see the layout, and add the dataset name to the candidate lists at the top of `pipeline/nisar_io.py`.

**The 3D before/after showcase:** on any place with layers, press "See before and after in 3D". Two 3D maps stay locked together, with a divider you can drag (or move with the arrow keys). "Play reveal" sweeps the later pass across the landscape while the camera circles, which makes a good shot for the demo video. The elevation comes from the free AWS Terrain Tiles. If they can't load, the view drops to flat and keeps working.

## Part 3: the earthquake

An interferogram compares the radar phase of two passes 12 days apart. One full colour cycle ("fringe") is half the radar wavelength, about 12 cm of movement toward or away from the satellite. Venezuela ships with a **synthetic demo**, labelled as such everywhere, built from a textbook strike-slip fault model along the coast:

```bash
python pipeline/quake.py demo --hotspot venezuela-coast
```

For real NISAR interferograms (free Earthdata login, as in Part 2):

```bash
python pipeline/quake.py download --hotspot venezuela-coast
python pipeline/quake.py process --hotspot venezuela-coast
```

`process` masks pixels with coherence below 0.3 or that the unwrapper could not connect. It subtracts the ionospheric phase screen shipped with each product (`--no-iono` to skip) and measures movement relative to the scene's outer edge. It writes three layers per pair: movement in centimetres, rainbow fringes and data quality. Pairs spanning the event are found automatically, and the 3D showcase opens on the pair across the quake next to a quiet pair.

**Check before publishing real results:** the code uses movement = -wavelength / (4 pi) x phase, with positive meaning toward the radar. Confirm this against the NISAR GUNW product specification, and add `--flip-sign` if it's the other way round.

Every module now writes the same general `manifest.json` (frames, layers with plain-words legends, statistics), so later parts add pipelines without new front-end code for the basics.

## Part 4: the inspector and the dance classifier

Click anywhere on a place's layer to see that spot's full history, with its measurement uncertainty as a shaded band, and the dance measured for that spot alone. Each place card now shows the expected dance next to the dance **measured from the data**.

The classifier compares simple explanations of a time series against its noise: no change (Still), one sudden jump (Tango), a rise and fall (Waltz), a speeding-up trend (Crescendo) or a steady trend (March). It exists twice, in `pipeline/dance.py` for the pipeline and in `web/src/dance.ts` for clicked pixels, and both must pass the same test cases in `data/dance_tests.json`:

```bash
python pipeline/dance.py --test
cd web && npm run test:dance
```

Add a test case whenever you change a rule, so the two versions can never drift apart. The pipelines also write each pixel's history to small binary files (`series.bin`, and `sigma.bin` for uncertainty), which are float32, laid out time by row by column.

With only months of passes, some places show part of their dance: Tonle Sap's monsoon rise reads as a March until a full year reveals the Waltz. The card shows both, which is a useful talking point.

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
VITE_TERRAIN_TILES=https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
```

If the basemap cannot load, the globe falls back to public-domain Natural Earth outlines shipped with the site, so the demo still works offline.

## How the repository is laid out

```
data/          Shared data: hotspots.json, coverage.json, basemap/, layers/<place>/ (web layers + manifest)
pipeline/      Python: coverage checks, nisar_io.py (HDF5 reader), layers.py (shared output),
               water.py and water_dance.py (Part 2), quake.py (Part 3), dance.py (Part 4)
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
| NumPy, SciPy, h5py | BSD-3-Clause |
| rasterio (bundles GDAL, MIT) | BSD-3-Clause |
| Pillow | MIT-CMU |

## Data and credits

- NISAR L-band data: NASA/JPL and ISRO, distributed free by the Alaska Satellite Facility DAAC.
- Basemap: OpenFreeMap, with map data from OpenStreetMap contributors (ODbL).
- Offline land outlines and the Tonle Sap lake outline: Natural Earth (public domain).
- Elevation for the 3D view: Terrain Tiles from the AWS Open Data programme (SRTM, GMTED and other public sources).
- Hotspot areas are approximate boxes. Tighten them after looking at real scenes.

SARabande is informational. It is not an official warning system.

## Use of AI

Parts of this code were drafted with help from an AI coding assistant (Claude). Space Apps asks teams to say where and how AI was used, so list this on the project page.
