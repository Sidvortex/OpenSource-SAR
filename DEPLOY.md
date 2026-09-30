# Deploying SARabande (free, step by step)

Everything here uses free accounts and free tiers. Nothing asks for a card.

## 1. Accounts you need

| Account | Why | Cost |
| --- | --- | --- |
| GitHub (public repository) | Code, free Pages hosting, free Actions | Free |
| NASA Earthdata (urs.earthdata.nasa.gov) | Downloading NISAR files | Free |
| ASF OpenSARLab (optional) | Process large files in the cloud, next to the archive | Free, apply early |
| ntfy topic (optional) | Push alerts to phones, no account needed | Free |

## 2. Publish the site on GitHub Pages

1. Create a **public** repository and push this folder to its `main` branch.
2. **Settings → Pages**: set Source to **GitHub Actions**.
3. **Settings → Actions → General → Workflow permissions**: choose **Read and write**, so the weekly job can commit.
4. **Settings → Secrets and variables → Actions → Variables**: add
   - `VITE_REPO_URL` = `https://github.com/<you>/<repo>` (turns on "Source code" and "Report what you see")
   - `SITE_URL` = your Pages address, e.g. `https://<you>.github.io/<repo>/` (used in alert links)
   - `VITE_NTFY_TOPIC` = a hard-to-guess topic name, if you want push alerts
5. If you set up push alerts, go to **Secrets** and add `NTFY_TOPIC` with the same topic name.
6. Push any change, or run **Actions → Deploy site → Run workflow**. The address appears on the run page.

Three workflows run for free: **Deploy site** (every push), **Tests** (both dance classifiers and a type check) and **Check NISAR coverage** (Mondays: coverage, RSS feed, ntfy alerts, STAC catalogue).

Custom domain (optional): add it under Settings → Pages. The site uses relative paths, so it works at any address.

## 3. Replace the synthetic demos with real NISAR data

Do this per hero, starting with the one whose coverage passes (`python pipeline/update_coverage.py` shows which).

```bash
pip install -r pipeline/requirements.txt
export EARTHDATA_USERNAME=you EARTHDATA_PASSWORD=secret     # or EARTHDATA_TOKEN=...
python pipeline/water_dance.py download --hotspot tonle-sap --max 12
python pipeline/water_dance.py process --hotspot tonle-sap
python pipeline/stac.py
git add data && git commit -m "Real NISAR water layers for Tonle Sap" && git push
```

For the others, see the table in the README. Things to know:

- **Disk space:** GCOV and GUNW files are gigabytes each. Use `--max`, or run the pipeline in OpenSARLab and copy back only `data/layers/<place>/`.
- **File layout:** if a real file surprises the reader, run `python pipeline/water_dance.py inspect FILE.h5` and add the dataset name to the lists at the top of `pipeline/nisar_io.py`.
- **Sign convention (ground motion):** confirm in the NISAR GUNW product specification whether positive phase means toward or away from the radar. If it's the opposite of our assumption, add `--flip-sign`.
- **GNSS checks:** download station files in tenv3 format from the Nevada Geodetic Laboratory (geodesy.unr.edu) into `data/gnss/<place>/`, and `quake.py process` compares them automatically.
- **The synthetic banner disappears by itself:** manifests built from real files say `"synthetic": false`.
- **Ice:** download GOFF products for the Shisper box from ASF Vertex into `pipeline/work/shisper/`.

## 4. Optional: self-host everything

```bash
cd web && npm ci && npm run build && cd ..
docker compose up        # site on http://localhost:8080, API on http://localhost:8000/docs
```

The API adds coverage for any box and on-demand processing (`POST /api/process/<place>`). It is bound to localhost on purpose, because it runs the pipelines; put it behind authentication before exposing it.

## 5. Before the demo

- [ ] Run both test suites and `npm run build`.
- [ ] Open every hero once on the demo laptop so offline mode caches it.
- [ ] Rehearse: a story, the inspector, "Hear it", Explain in Hindi, "Check any area", then the 3D "Play reveal".
- [ ] Record the 30-second video from real screen captures, with English subtitles.
- [ ] If you're still showing any synthetic layer, say so out loud and on the project page.
- [ ] Project page: list NASA data, ISRO and ESA partner data, every open-source library, and the AI-use statement.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Blank globe | The basemap is blocked. The offline outlines should appear; check the console for `tiles.openfreemap.org` errors |
| "Couldn't reach NASA's catalogue" | CMR may be down or blocked. Use the Vertex link, or run `coverage_check.py` |
| 3D view is flat | Elevation tiles didn't load (it falls back safely); check the network |
| Weekly job can't push | Workflow permissions must be "Read and write" (step 2.3) |
| Page 404 after deploy | Pages source must be "GitHub Actions" (step 2.2) |
