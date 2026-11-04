import type maplibregl from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import type { LayerManifest } from './types';

// Free, open basemap with no API key. Override with VITE_BASEMAP_STYLE (for example a
// self-hosted Protomaps style) to be independent of any tile service.
export const STYLE_URL: string =
  import.meta.env.VITE_BASEMAP_STYLE || 'https://tiles.openfreemap.org/styles/positron';

// Free elevation tiles from the AWS Open Data programme (Terrarium encoding, no key).
export const TERRAIN_URL: string =
  import.meta.env.VITE_TERRAIN_TILES || 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
export const TERRAIN_ATTRIBUTION =
  '<a href="https://registry.opendata.aws/terrain-tiles/">Terrain Tiles</a> (AWS Open Data: SRTM, GMTED and others)';

/** Absolute URL for a file the site serves, so MapLibre's workers resolve it correctly. */
export function siteUrl(path: string): string {
  return new URL(`${import.meta.env.BASE_URL}${path}`, window.location.href).href;
}

/** Public-domain Natural Earth outlines shipped with the site, used when the basemap can't load. */
export function offlineStyle(): StyleSpecification {
  return {
    version: 8,
    sources: { land: { type: 'geojson', data: siteUrl('data/basemap/land.geojson') } },
    layers: [
      { id: 'ocean', type: 'background', paint: { 'background-color': '#dfe6ee' } },
      { id: 'land', type: 'fill', source: 'land', paint: { 'fill-color': '#b9c5d3' } },
      { id: 'coast', type: 'line', source: 'land', paint: { 'line-color': '#9fb0c3', 'line-width': 0.6 } },
    ],
  };
}

/** Switch to the offline style if the basemap style itself fails to load. */
export function useOfflineFallback(map: maplibregl.Map) {
  let fellBack = false;
  map.on('error', () => {
    if (!fellBack && !map.isStyleLoaded()) {
      fellBack = true;
      map.setStyle(offlineStyle());
    }
  });
}

export type Corners = [[number, number], [number, number], [number, number], [number, number]];

export interface Overlay {
  url: string;
  coordinates: Corners;
  opacity: number;
}

/** Add, update or remove the single radar overlay on a map. */
export function applyOverlay(map: maplibregl.Map, overlay: Overlay | null, beforeId?: string) {
  try {
    applyNow(map, overlay, beforeId);
  } catch {
    // The style isn't parsed yet: try again as soon as it is.
    map.once('style.load', () => applyOverlay(map, overlay, beforeId));
  }
}

function applyNow(map: maplibregl.Map, overlay: Overlay | null, beforeId?: string) {
  const source = map.getSource('overlay') as maplibregl.ImageSource | undefined;
  if (!overlay) {
    if (map.getLayer('overlay')) map.removeLayer('overlay');
    if (source) map.removeSource('overlay');
    return;
  }
  if (source) {
    source.updateImage({ url: overlay.url, coordinates: overlay.coordinates });
    map.setPaintProperty('overlay', 'raster-opacity', overlay.opacity);
    return;
  }
  map.addSource('overlay', { type: 'image', url: overlay.url, coordinates: overlay.coordinates });
  map.addLayer(
    { id: 'overlay', type: 'raster', source: 'overlay', paint: { 'raster-opacity': overlay.opacity, 'raster-fade-duration': 0 } },
    beforeId && map.getLayer(beforeId) ? beforeId : undefined,
  );
}

// Radar vs optical: NASA GIBS daily MODIS (Terra) true colour, free and keyless.
// Native resolution ends at zoom 9 (about 250 m); MapLibre scales beyond that.
export const GIBS_LAYER: string = import.meta.env.VITE_GIBS_LAYER || 'MODIS_Terra_CorrectedReflectance_TrueColor';
export const GIBS_ATTRIBUTION = 'Optical imagery: <a href="https://www.earthdata.nasa.gov/eosdis/science-system-description/eosdis-components/gibs">NASA GIBS</a>, MODIS Terra';
export const gibsTiles = (isoDate: string) =>
  `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${GIBS_LAYER}/default/${isoDate}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`;

/** Show the optical image for a date under any radar layer, or remove it (null). */
export function applyOptical(map: maplibregl.Map, isoDate: string | null, beforeId?: string) {
  try {
    if (!isoDate) {
      if (map.getLayer('optical')) map.removeLayer('optical');
      if (map.getSource('optical')) map.removeSource('optical');
      return;
    }
    const source = map.getSource('optical') as maplibregl.RasterTileSource | undefined;
    if (source) { source.setTiles([gibsTiles(isoDate)]); return; }
    map.addSource('optical', { type: 'raster', tiles: [gibsTiles(isoDate)], tileSize: 256, maxzoom: 9, attribution: GIBS_ATTRIBUTION });
    map.addLayer({ id: 'optical', type: 'raster', source: 'optical', paint: { 'raster-fade-duration': 0 } },
      beforeId && map.getLayer(beforeId) ? beforeId : undefined);
  } catch {
    map.once('style.load', () => applyOptical(map, isoDate, beforeId));
  }
}

/** The image overlay for one frame and layer of a place. */
export function overlayFor(manifest: LayerManifest, index: number, kind: string): Overlay {
  const frame = manifest.frames[index];
  const layer = manifest.layers.find((l) => l.id === kind && frame.files[l.id]) ?? manifest.layers.find((l) => frame.files[l.id])!;
  return {
    url: siteUrl(`data/layers/${manifest.hotspot}/${frame.files[layer.id]}`),
    coordinates: manifest.bounds,
    opacity: layer.opacity,
  };
}
