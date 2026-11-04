# Roadmap

*Maintained by Mind (Ravada Siddharth), team lead.*

The ten-part plan is built, along with the final-version extras: context events, radar beside optical, people on changed ground, MintPy import, ground reports on the map, a real-data smoke test, schema validation and pipeline tests. This page lists what I want us to do next, in order of value for judging.

## Before submission (must)

1. **Run the smoke test on real data.** `python pipeline/smoke_test.py` with an Earthdata login. Every FAIL tells us which dataset name to add in `pipeline/nisar_io.py`.
2. **Replace the synthetic heroes with real NISAR products** (DEPLOY.md, section 4), starting with whichever passes coverage first.
3. **Confirm the GUNW sign convention** and the collection names in `web/src/components/AreaCheck.tsx` against NASA's current product specification.
4. **Swap the synthetic population for WorldPop or GHSL** on the heroes that show people on changed ground.
5. The 30-second video, the project page and the AI-use statement. Drafts are in [SUBMISSION.md](SUBMISSION.md).

## Ideas that need money (parked)

**A SatDump ground station.** [SatDump](https://github.com/SatDump/SatDump) (GPL-3.0) is free software that decodes weather satellites (NOAA APT, Meteor-M LRPT, GOES/Himawari HRIT) from a cheap software-defined radio. It does not handle SAR, and NISAR's downlink is far beyond hobby hardware, so it can't replace our radar data. What it could add is a live optical or infrared image that the team receives ourselves, shown beside the radar layers in the same way as the NASA GIBS optical toggle.

- **Cost:** an RTL-SDR dongle and antenna (about US$40–60 for VHF; much more for an L-band dish and LNA for HRIT). This is the only reason it is parked: everything else in the project is free.
- **Licence:** GPL-3.0. That's fine as a separate tool feeding images into `data/`; we would not link its code into ours.
- **How it would fit:** SatDump writes georeferenced images, and a small `pipeline/satdump_import.py` would turn a pass into an extra optical frame for any place it covers.

## Science upgrades

- **Vertical vs sideways motion:** combine ascending and descending tracks.
- **Tropospheric correction,** for example with ERA5 through PyAPS (or MintPy's own correction, which our importer already reads).
- **Change-point detection:** use `ruptures` to date when a place's dance changed.
- **Active deformation areas:** DBSCAN clusters of fast-moving pixels, drawn as outlines.
- **Flood segmentation:** a small U-Net trained on OPERA DSWx as weak labels, compared openly with the threshold method.
- **Landslide hazard fusion:** motion, slope, rainfall (we already fetch it) and land cover, trained on NASA's Global Landslide Catalog and labelled experimental.
- **Fault-slip sketch** for Venezuela: an Okada elastic model fitted to the coseismic map.
- **Buildings on changing ground:** add open building footprints (Overture, Microsoft, Google) beside the population count.
- **Longer history:** Sentinel-1 (ESA) before NISAR, clearly labelled; ISRO S-band beside L-band for crops.

## Product upgrades

- **Optional in-browser language model:** WebLLM (Apache-2.0) with an Apache-2.0 or MIT model to polish explanations. It must only restate numbers in the data, and fall back to the templates.
- **More languages:** add a code to `data/explain.json`, then translate `data/stories.json` and the interface labels.
- **Exaggerated 3D ground motion:** turn displacement into a terrain source so the land visibly lifts and sinks.
- **High-resolution tiles:** move from PNG overlays to COG or PMTiles for big areas.
- **Classroom packs:** printable lessons built from the stories and the quiz.
- **Desk "Earth pulse" display:** an ESP32 with an LED ring that pulses with a place's latest dance (hardware cost, so parked with SatDump).

## Engineering

- An automated accessibility audit (axe) in CI, plus a screen-reader pass.
- End-to-end browser tests (Playwright) for the stories and the inspector.
- Split MapLibre into its own lazily loaded chunk for a faster first paint (the 3D view and radar lesson already load on demand).

## Done since the first roadmap

Event markers from USGS and FIRMS, rain from Open-Meteo, the MintPy converter, the exposure layer, citizen reports on the map, pipeline unit tests, manifest schema validation in CI, and lazy loading for the 3D view.
