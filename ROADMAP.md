# What else to add

Everything in the ten-part plan has a working first version. These are the next steps, roughly in order of value for judging.

## Before submission (must)

1. **Real data for the heroes.** Replace each synthetic demo (DEPLOY.md section 3), starting with whatever `update_coverage.py` passes.
2. **Confirm the GUNW sign convention**, and the collection names in `web/src/components/AreaCheck.tsx`, against NASA's current documentation.
3. **Event markers from live feeds** (planned for Part 7, not built yet): USGS earthquakes (free GeoJSON feed), NASA FIRMS fires (free CSVs) and GPM IMERG rain, drawn on the time-bar chart.
4. The 30-second video, the project page, and the AI-use statement.

## Science upgrades

- **MintPy time series** for the ground-motion heroes: run MintPy on the GUNW stack, then write a small converter from its `timeseries.h5` and `velocity.h5` into our manifest format (`pipeline/layers.py` has every helper needed).
- **Vertical vs sideways motion:** combine ascending and descending tracks.
- **Tropospheric correction:** for example with ERA5 weather data through PyAPS.
- **Change-point detection:** use `ruptures` to date when a place's dance changed.
- **Active deformation areas:** DBSCAN clusters of fast-moving pixels, drawn as outlines.
- **Flood segmentation:** a small U-Net trained on OPERA DSWx as weak labels, compared openly with the threshold method.
- **Landslide hazard fusion:** motion + slope + rainfall + land cover, trained on NASA's Global Landslide Catalog, and labelled experimental.
- **Fault-slip sketch** for Venezuela: an Okada elastic model fitted to the coseismic map.
- **Exposure layer:** people and buildings on changing ground (WorldPop or GHSL, open building footprints).
- **Longer history:** Sentinel-1 (ESA) before NISAR, clearly labelled; ISRO S-band beside L-band for crops.

## Product upgrades

- **Optional in-browser language model:** WebLLM (Apache-2.0) with an Apache-2.0 or MIT model to polish the explanations. It must only restate numbers that are in the data, and fall back to the templates.
- **More languages:** add a language code to `data/explain.json`, and translate `data/stories.json` and the interface labels.
- **Exaggerated 3D ground motion:** turn displacement into a terrain source, so the land visibly lifts and sinks.
- **High-resolution tiles:** switch from PNG overlays to COG or PMTiles for big areas.
- **Citizen reports on the map:** read labelled GitHub issues through the public API and plot them.
- **Classroom packs:** printable lessons built from the stories and the quiz.
- **Desk "Earth pulse" display:** an ESP32 with an LED ring that pulses with a watched place's latest dance, using the public manifest URL.

## Engineering

- Unit tests for each pipeline with small synthetic files (the demo generators already make them).
- An automated accessibility audit (axe) in CI, plus a screen-reader pass.
- Lazy-load MapLibre and the 3D view to speed up the first paint.
- Validate every manifest against a JSON schema in CI.
