# Space Apps submission: Open Source SAR

*Drafted by Mind (Ravada Siddharth), team lead. Paste each section into the matching field on our Space Apps project page, and edit wherever the facts change (real data, team names, links).*

- **Challenge:** Dancing with the SARs
- **Project name:** Open Source SAR
- **Repository:** https://github.com/Sidvortex/OpenSource-SAR
- **Live site:** https://sidvortex.github.io/OpenSource-SAR/

## High-level summary (about 150 words)

Open Source SAR lets anyone watch Earth's surface "dance" using the NASA-ISRO NISAR radar, which maps the planet every 12 days through clouds, smoke and darkness. We turn NISAR's flood, interferogram and pixel-offset products into an interactive globe: a lake that breathes with the monsoon, a city that sinks, a coast that jumped in an earthquake, forests that burn and a glacier that surges. Click any pixel to see its history with uncertainty, and a classifier names the dance (Waltz, March, Tango, Crescendo or Still). Explanations come in three reading levels and three languages. Earthquakes, fires and rain are marked on the timeline; an Optical button shows the clouds radar sees through; and population data shows how many people live on changed ground. Everything is free and open source, end to end: no paid services, no keys in the app, and hosting on free GitHub Pages.

## Project demo (30-second video script)

| Time | Picture | Voice / subtitle |
| --- | --- | --- |
| 0–4 s | Globe spinning, markers pulsing in rhythm | "Every 12 days, a radar called NISAR maps the whole Earth." |
| 4–9 s | Tonle Sap: press play, the lake swells | "It sees a lake breathe with the monsoon…" |
| 9–13 s | Press Optical: white cloud covers the lake; press Movement again | "…straight through the clouds that blind ordinary cameras." |
| 13–18 s | Caracas coast; the earthquake marks on the chart | "It saw this coast jump in the June earthquakes." |
| 18–23 s | Click a pixel in Mexico City; the inspector says "March" | "Click anywhere, and we tell you how that ground dances." |
| 23–27 s | 3D before/after, Play reveal | "See it in 3D, in your language, at your reading level." |
| 27–30 s | Logo, repository address | "Open Source SAR. Free and open, end to end." |

Record real screen captures only, with subtitles burned in. If any layer is still a synthetic demo, show the on-screen "Synthetic demo" banner rather than hiding it.

## Final project (detailed description)

**What it does.** Open Source SAR is a web app and an open pipeline. The pipeline searches NASA's free archive for NISAR products over 19 places worldwide, downloads them with a free Earthdata login, and turns them into small image layers, statistics and time-series cubes. The app shows those layers on a 3D globe with a time slider, a chart, a click-any-pixel inspector and a before/after 3D view.

**The five dances.** Each place and each clicked pixel gets a plain-language label:

- **Waltz:** seasonal back and forth.
- **March:** steady one-way change.
- **Tango:** a sudden jump.
- **Crescendo:** speeding up.
- **Still:** no real change.

The classifier is written twice, in Python and TypeScript, and both pass one shared test set.

**Modules:**

| Module | NISAR product |
| --- | --- |
| Water and wetlands | GCOV backscatter |
| Earthquakes and sinking ground | GUNW interferograms, checked against GNSS stations |
| Fire and farming | GCOV change |
| Glacier speed | GOFF pixel offsets |

A converter also imports MintPy time series for research-grade ground motion.

**Context.** Earthquakes from USGS, rain from Open-Meteo and, optionally, fires from NASA FIRMS are drawn on each place's chart. An Optical button swaps radar for NASA GIBS true-colour imagery of the same date, which makes radar's advantage obvious. A population layer (WorldPop or GHSL) counts the people living where the ground changed. The app is careful to call this a count of residents, not of people harmed.

**For everyone:**

- Explanations at three reading levels in English, Hindi and Spanish.
- Guided stories, and a "How radar sees" lesson with a quiz.
- Sonification.
- Offline mode, and keyboard and screen-reader support.
- Shareable links, image and CSV export, RSS and push alerts, and a STAC catalogue.
- Ground reports from the public, filed as GitHub issues and shown on the map.

**How it's built.** A Python pipeline (NumPy, h5py, rasterio, asf_search) writes a static `data/` folder against one JSON schema. A React, TypeScript, Vite and MapLibre app reads it. Free GitHub Actions run the tests, validate every manifest, deploy to GitHub Pages and refresh coverage, context and reports every week. An optional FastAPI server in Docker adds on-demand processing for self-hosters.

**Why it matters.** Radar data is powerful, but it is hard for most people to read. We wanted a farmer, a student or a city planner to be able to look up their own place and understand what the ground is doing, honestly, with its uncertainty, and without paying for anything.

**Honesty.** Every layer says whether it is real or a synthetic demo, and what the method can't tell you. The app is informational, not an official warning system.

## Use of artificial intelligence

We used an AI coding assistant (Claude, by Anthropic) to help draft code, tests and documentation. The team reviewed, ran and edited everything, and we chose the design, data and science approach. The app itself uses no AI model: explanations are written from templates that only restate numbers in the data. No AI-generated images or video are presented as NASA data.

## NASA data

- **NISAR** L2 GCOV, L2 GUNW, L2 GOFF and L3 SME2 products (NASA/JPL and ISRO), via the Alaska Satellite Facility DAAC, found with NASA CMR and asf_search.
- **NASA GIBS:** MODIS Terra corrected reflectance, true colour (the Optical view).
- **NASA FIRMS:** VIIRS S-NPP active fires (optional context).
- **NASA Earthdata Login**, for downloads.

## Space agency partner data

- **ISRO:** NISAR is a joint NASA-ISRO mission. The S-band data is planned (see the roadmap).
- **ESA:** Sentinel-1, for longer history before NISAR. This is planned and will be clearly labelled.

## Other free resources

- USGS earthquake catalogue (FDSN event service).
- Open-Meteo historical weather (CC BY 4.0).
- WorldPop / JRC GHSL population.
- Nevada Geodetic Laboratory GNSS.
- OpenFreeMap and OpenStreetMap (ODbL), Natural Earth, and AWS Open Data Terrain Tiles.
- MintPy (optional).

Every software library and its licence is listed in the README.

## References

- NISAR mission and data user guide: nisar.jpl.nasa.gov and the ASF NISAR documentation.
- ASF DAAC NISAR products and asf_search documentation.
- NASA GIBS API documentation (nasa-gibs.github.io/gibs-api-docs).
- NASA FIRMS area API documentation.
- USGS FDSN event web service documentation.
- Open-Meteo historical weather API documentation.
- Yunjun, Z., Fattahi, H., and Amelung, F. (2019), "Small baseline InSAR time series analysis: Unwrapping error correction and noise reduction", *Computers & Geosciences* (MintPy).

## Team

- **Mind (Ravada Siddharth):** team lead, pipeline and deployment.
- **[Teammate 2]:** [role]
- **[Teammate 3]:** [role]
