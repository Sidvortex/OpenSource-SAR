# Deploying Open Source SAR (free, step by step)

*Written by Mind (Ravada Siddharth), team lead. Follow it top to bottom; every step is free and nothing asks for a card.*

## 1. Accounts

| Account | Why | Cost |
| --- | --- | --- |
| GitHub (public repository) | Code, free Pages hosting, free Actions | Free |
| NASA Earthdata (urs.earthdata.nasa.gov) | Downloading NISAR files | Free |
| NASA FIRMS map key (optional) | Active-fire markers on fire places | Free, by email |
| ASF OpenSARLab (optional) | Processing big files next to the archive | Free, apply early |
| ntfy topic (optional) | Push alerts to phones, no account | Free |

## 2. Get the code into our repository

Our repository already has four commits on `main`. Put this version on top of them, so we keep the history.

```bash
git clone https://github.com/Sidvortex/OpenSource-SAR.git
cd OpenSource-SAR
# unzip OpenSource-SAR.zip somewhere else, then copy everything over the clone:
rsync -a --exclude .git /path/to/unzipped/OpenSource-SAR/ ./
git add -A
git commit -m "Final version: context events, optical view, exposure, MintPy, reports, tests"
git push origin main
```

On my machine (EndeavourOS), I set up the tools once, with no virtual environment:

```bash
sudo pacman -S --needed python python-pip nodejs npm git gdal
pip install --break-system-packages -r pipeline/requirements-dev.txt
cd web && npm ci && cd ..
```

Then I check that everything passes locally before pushing:

```bash
python pipeline/dance.py --test
python -m pytest pipeline/tests -q
python pipeline/validate.py
cd web && npm run test:dance && npm run build && npm run preview   # opens on http://localhost:4173
```

## 3. Turn on the site

1. **Settings → Pages**: Source **GitHub Actions**.
2. **Settings → Actions → General → Workflow permissions**: **Read and write**, so the weekly job can commit.
3. **Settings → Secrets and variables → Actions → Variables** (all optional):
   - `VITE_REPO_URL` = `https://github.com/Sidvortex/OpenSource-SAR` (this is also the default)
   - `SITE_URL` = `https://sidvortex.github.io/OpenSource-SAR/`
   - `VITE_NTFY_TOPIC` = a hard-to-guess topic, for push alerts
   - `VITE_GIBS_LAYER` = another NASA GIBS layer for the Optical button (default `MODIS_Terra_CorrectedReflectance_TrueColor`; `VIIRS_SNPP_CorrectedReflectance_TrueColor` also works)
4. **Secrets** (optional): `NTFY_TOPIC` (same topic name) and `FIRMS_MAP_KEY` (from firms.modaps.eosdis.nasa.gov/api/map_key).
5. **Issues → Labels**: create a label called `ground-report`. The issue form adds it, and the weekly job only reads issues with it.
6. Push, or run **Actions → Deploy site → Run workflow**. The site appears at https://sidvortex.github.io/OpenSource-SAR/.
7. Run **Actions → Weekly update → Run workflow** once by hand, so context and reports appear straight away.

Three workflows run for free:

- **Deploy site** (every push)
- **Tests** (every push and pull request: both dance classifiers, pipeline tests, manifest schema, type check and build)
- **Weekly update** (Mondays: NISAR coverage, RSS and ntfy alerts, earthquakes, rain, fires, ground reports, STAC, validation)

## 4. Replace the synthetic demos with real NISAR data

First, the smoke test. It downloads the smallest real product of each type and runs our readers on it:

```bash
export EARTHDATA_USERNAME=you EARTHDATA_PASSWORD=secret     # or EARTHDATA_TOKEN=...
python pipeline/smoke_test.py
```

A FAIL prints the file's layout. Add the dataset name it shows to the lists at the top of `pipeline/nisar_io.py`, then run it again.

Then, per hero (the README table has every module):

```bash
python pipeline/water_dance.py download --hotspot tonle-sap --max 12
python pipeline/water_dance.py process --hotspot tonle-sap
python pipeline/context.py --hotspot tonle-sap
python pipeline/stac.py && python pipeline/validate.py
git add data && git commit -m "Real NISAR water layers for Tonle Sap" && git push
```

- **Disk space:** GCOV and GUNW files are gigabytes. Use `--max`, or run in OpenSARLab and copy back only `data/layers/<place>/`.
- **Sign convention:** confirm in the GUNW specification whether positive phase means toward or away from the radar; if it's the opposite of our assumption, add `--flip-sign`.
- **GNSS checks:** put Nevada Geodetic Laboratory tenv3 files in `data/gnss/<place>/`, and `quake.py process` compares them.
- **The synthetic banner disappears on its own:** real manifests say `"synthetic": false`.

### Better ground motion with MintPy

For the sinking-city heroes, I'd like us to run MintPy (free, GPL-3.0, a separate tool) on the GUNW stack and import its corrected time series:

```bash
pip install --break-system-packages mintpy
# run smallbaselineApp.py on the stack, then geocode, then:
python pipeline/mintpy_import.py --hotspot mexico-city \
    --timeseries mintpy/geo/geo_timeseries_ERA5_demErr.h5 --velocity mintpy/geo/geo_velocity.h5
```

### People on changed ground

Download a free WorldPop (CC BY 4.0) or GHSL counts raster that covers the place (people per pixel, not density), then:

```bash
python pipeline/exposure.py --hotspot tonle-sap --population tha_khm_ppp_2020.tif
```

This works for water, fire and ground places. The app says it's a count of residents, not of people harmed.

## 5. Optional: self-host everything

```bash
cd web && npm ci && npm run build && cd ..
docker compose up        # site on http://localhost:8080, API on http://localhost:8000/docs
```

The API adds coverage for any box and on-demand processing. It is bound to localhost on purpose, because it runs the pipelines; put it behind authentication before exposing it.

## 6. Before the demo

- [ ] Every check in section 2 passes, and the Tests workflow is green.
- [ ] Open every hero once on the demo laptop, so offline mode caches it.
- [ ] Rehearse: a story, the inspector, "Hear it", Explain in Hindi, "Check any area", the Optical button on a cloudy date, then the 3D "Play reveal".
- [ ] Record the 30-second video (script in SUBMISSION.md) from real screen captures, with subtitles.
- [ ] If any synthetic layer is still showing, say so out loud and on the project page.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Blank globe | The basemap is blocked; the offline outlines should appear. Check the console for `tiles.openfreemap.org` |
| Optical shows nothing | GIBS has no image for that date yet (a day or two of latency), or zoom is past level 9 |
| No earthquakes or rain | Run the Weekly update; it keeps last week's context if the services are down |
| No ground reports | The issues need the `ground-report` label and a "lat, lon" in the Place field |
| "Couldn't match the layer grid" | Rebuild the place's layers; new manifests record `grid_res` |
| Tests fail on `validate.py` | It lists the exact file or field; usually a frame image wasn't committed |
| Weekly job can't push | Workflow permissions must be "Read and write" (section 3, step 2) |
| Page 404 after deploy | Pages source must be "GitHub Actions" (section 3, step 1) |
