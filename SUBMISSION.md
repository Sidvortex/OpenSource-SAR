# Space Apps submission: Open Source SAR

*Written by Mind (Ravada Siddharth), team lead. One section per field of the Space Apps project form, in the form's order. Paste each one as it is.*

- **Challenge:** Dancing with the SARs
- **Repository:** https://github.com/Sidvortex/OpenSource-SAR
- **Live site:** https://sidvortex.github.io/OpenSource-SAR/

---

## Project Name

Open Source SAR

---

## High-Level Project Summary

Open Source SAR is a free, open-source web app and data pipeline that lets anyone watch Earth's surface "dance" in NASA-ISRO NISAR radar data, which maps the planet every 12 days through cloud, smoke and darkness. It turns NISAR's backscatter, interferogram and pixel-offset products into an interactive 3D globe of places around the world: a lake that swells with the monsoon, a city that sinks, a coast that jumped in an earthquake, forests that burn, crops that grow and a glacier that surges. Click any spot to see its history with uncertainty, and a classifier names its motion as one of five dances (Waltz, March, Tango, Crescendo or Still). Plain-language explanations come at three reading levels in English, Hindi and Spanish. Earthquakes, fires, rain, cloud-free optical photos and 36 years of water records give each change its context. It answers the challenge by making SAR change readable for non-experts, honestly and at no cost to anyone.

---

## Link to Project Demo

https://github.com/Sidvortex/OpenSource-SAR/blob/main/docs/OpenSource-SAR-demo.pdf

(A 7-slide presentation: title, the problem, what we built, how it works, context, accessibility, and free and open.)

---

## Link to Final Project

https://sidvortex.github.io/OpenSource-SAR/

Source code, pipeline and documentation: https://github.com/Sidvortex/OpenSource-SAR

---

## Detailed Project Description

**What it does**

Open Source SAR has two halves that share one data contract.

1. **The pipeline (Python)** searches NASA's archive for NISAR products over each place, downloads them with a free NASA Earthdata login, and turns them into small map layers, statistics and per-pixel time series:
   - **Water and wetlands** from L2 GCOV backscatter: open water and likely flooded vegetation for every 12-day pass.
   - **Earthquakes and sinking ground** from L2 GUNW interferograms: line-of-sight movement in centimetres, fringes and data quality, with the ionospheric correction applied and GNSS stations as an independent check.
   - **Fire and farming** from GCOV cross-polarised change: burn scars and crop growth.
   - **Glacier speed** from L2 GOFF pixel offsets.
   - A converter that imports MintPy time series for research-grade ground motion.

2. **The web app** shows those layers on a 3D globe with a time slider, a chart, a click-any-pixel inspector and a before/after 3D view with a "Play reveal". Each place and each clicked pixel gets one of five dances:
   - **Waltz:** seasonal back and forth.
   - **March:** steady one-way change.
   - **Tango:** a sudden jump.
   - **Crescendo:** speeding up.
   - **Still:** no real change.

   The classifier exists in Python and TypeScript, and both pass one shared test set.

**Context that makes a change understandable**

- Earthquakes (USGS) and active fires (NASA FIRMS) are marked on each place's timeline, with daily rain (Open-Meteo) as bars.
- An Optical button swaps radar for a true-colour photo near the same date: ESA Sentinel-2 at 10 m, or NASA GIBS MODIS where there is none. A cloudy day shows exactly why radar matters.
- For floods, the app compares against the JRC Global Surface Water record for 1984 to 2020 and shows only the water that is new. It also reports how much of the long-term water our method finds, as a check.
- ESA WorldCover says what kind of land changed (cropland, built-up, forest), and a population layer counts how many people live there. The app says plainly that this counts residents, not people harmed.

**For everyone**

- Explanations at three reading levels (like I'm 10, everyday, expert) in English, Hindi and Spanish.
- Guided stories, and a "How radar sees" lesson with a quiz.
- Sonification ("Hear it"), offline mode, and keyboard and screen-reader support.
- "Check any area": draw a box anywhere on Earth to see which NISAR passes exist there.
- Shareable links, image and CSV export, RSS and push alerts, and a STAC catalogue of every layer.
- Ground reports from the public, filed through a GitHub issue form and shown as pins on the map.

**Benefits**

Radar sees through cloud and at night, so it watches floods, landslides and sinking ground exactly when cameras can't. But SAR data is hard to read, and the tools usually need expertise, a powerful computer or a paid account. Open Source SAR lets a student, a farmer, a journalist or a city planner open a link, find their place and understand what the ground is doing, with its uncertainty and its limits stated next to every number.

**What we hope to achieve**

A public, free window onto NISAR that any community can extend: add a place by editing one JSON file, run the pipeline, and the site, the alerts and the catalogue update themselves. The ROADMAP lists the next steps: combining ascending and descending passes into true vertical motion, Sentinel-1 history before NISAR, and more languages.

**Honest status**

The pipeline's readers have been tested on real NISAR PROVISIONAL products (GCOV, GUNW and GOFF all pass), and the coverage checks, NASA catalogue search, context events and optical photos use live data. Real NISAR layers for the hero places are being processed now. Until each one is finished, the app shows a clearly labelled synthetic demo built by the same code, with a "Synthetic demo" banner on every screen that shows one. The app is informational, not an official warning system.

**Tools, languages, hardware and software**

- **Languages:** Python 3 and TypeScript.
- **Pipeline:** NumPy, SciPy, h5py, rasterio and GDAL, asf_search, Shapely, Pillow, matplotlib, jsonschema and pytest.
- **Web app:** React, Vite and MapLibre GL JS.
- **Optional server:** FastAPI and Uvicorn in Docker.
- **Automation and hosting:** GitHub Actions for tests, a weekly data update and deployment, with hosting on GitHub Pages.
- **Hardware:** our own laptops (EndeavourOS Linux). No paid cloud services.

Everything is MIT-licensed, and every dependency is free and open source.

---

## Use of Super Intelligence (SI)

Yes. We used Claude (Anthropic), an AI assistant, throughout the project:

- **Planning:** we used it in our first planning conversation to explore the challenge and brainstorm what to build, then shaped the plan ourselves. The team set the goals and rules: global scope, everything free and open source, a ten-part build from small to full, honest labelling of demo data, and the project's name.
- **Code:** most of the pipeline and web app code, the tests and the GitHub workflows were written by the assistant under our direction. We ran, reviewed and debugged them on our own machines, including against real NISAR files (the coverage-selection and download fixes came from those runs).
- **Text:** the assistant drafted the documentation, the in-app explanations (including the Hindi and Spanish versions) and this submission text, which we edited.
- **Images and video:** no AI-generated images, audio or video are used. The demo slides use real screenshots of the app.
- **In the app:** the app itself uses no AI. Explanations are filled in from templates that only restate numbers in the data.

**Where this is marked:**

- In the code: `AI_USE.md` and the "Use of AI" section of the README.
- In the metadata: the `ai_assistance` field in `web/package.json`.
- On the slides: the last slide says so.

No NASA branding or design elements were used or modified.

---

## NASA Data

- **NISAR (NASA-ISRO SAR mission):** L2 GCOV, L2 GUNW and L2 GOFF products (PROVISIONAL), from NASA's Alaska Satellite Facility DAAC. We found them with NASA's Common Metadata Repository (CMR) and the ASF search API, and downloaded them with NASA Earthdata Login. https://nisar.jpl.nasa.gov/ · https://asf.alaska.edu/nisar/
- **NASA GIBS:** MODIS Terra corrected reflectance, true colour, for the Optical view when no Sentinel-2 photo is available. https://nasa-gibs.github.io/gibs-api-docs/
- **NASA FIRMS:** VIIRS S-NPP active fires, as context for fire places. https://firms.modaps.eosdis.nasa.gov/
- **NASA Earthdata Search and CMR**, for the "Check any area" coverage tool. https://www.earthdata.nasa.gov/

---

## Space Agency Partner Data and Other References

**Space agency partner data**

- **ISRO (Indian Space Research Organisation):** NISAR is a joint NASA-ISRO mission; all NISAR data above is shared with ISRO.
- **ESA (European Space Agency):** Copernicus Sentinel-2 L2A true-colour imagery (contains modified Copernicus Sentinel data, 2026) and ESA WorldCover 2021 land cover (CC BY 4.0), both read through the Microsoft Planetary Computer.

**Other data**

- **JRC Global Surface Water 1984 to 2020** (European Commission JRC / Google), through the Microsoft Planetary Computer, a Space Apps Global Offer.
- **USGS earthquake catalogue** (FDSN event web service, public domain).
- **Open-Meteo historical weather** (CC BY 4.0). Weather data by Open-Meteo.com.
- **WorldPop / JRC GHSL population** (CC BY 4.0).
- **Nevada Geodetic Laboratory GNSS time series** (format and stations).
- **OpenFreeMap basemap** with OpenStreetMap data (ODbL), **Natural Earth** (public domain) and **AWS Open Data Terrain Tiles**.

**Software (all free and open source)**

- **Pipeline:** NumPy, SciPy, h5py, rasterio, GDAL, asf_search, Shapely, Pillow, matplotlib, jsonschema and pytest.
- **Web app:** React, TypeScript, Vite and MapLibre GL JS.
- **Server:** FastAPI and Uvicorn.
- **Optional:** MintPy (GPL-3.0, a separate tool whose output files we read).
- **Fonts:** Archivo and Source Serif 4 (SIL OFL).

The README lists each library with its licence.

**Code and text**

All project code and text are our own (MIT licence), written with the AI assistance described in the SI section. No copyrighted material is used without permission.

**References**

- NISAR mission and data user guide, NASA JPL. https://nisar.jpl.nasa.gov/
- ASF DAAC NISAR documentation and the asf_search API. https://docs.asf.alaska.edu/
- NASA GIBS API documentation. https://nasa-gibs.github.io/gibs-api-docs/
- Microsoft Planetary Computer data catalogue. https://planetarycomputer.microsoft.com/catalog
- Pekel, J.-F., Cottam, A., Gorelick, N. and Belward, A. S. (2016). "High-resolution mapping of global surface water and its long-term changes." *Nature* 540, 418–422.
- Zanaga, D. et al. (2022). *ESA WorldCover 10 m 2021 v200*. Zenodo.
- Yunjun, Z., Fattahi, H. and Amelung, F. (2019). "Small baseline InSAR time series analysis: unwrapping error correction and noise reduction." *Computers & Geosciences* 133.

---

## Team

- **Mind (Ravada Siddharth):** team lead, pipeline and deployment.

Teammates are listed on our Space Apps team page.
