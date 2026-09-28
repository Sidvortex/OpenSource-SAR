import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import type { StyleSpecification } from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';
import { DANCES, MODULES } from '../catalog';
import type { Hotspot } from '../types';

// Free, open basemap with no API key. Override with VITE_BASEMAP_STYLE, for example
// a self-hosted Protomaps style, if you want to be independent of any tile service.
const STYLE_URL: string =
  import.meta.env.VITE_BASEMAP_STYLE ?? 'https://tiles.openfreemap.org/styles/positron';

// Used when the basemap cannot load (offline demo, blocked network): public-domain
// Natural Earth land outlines shipped with the site, so the globe never goes blank.
const LAND_URL = new URL(`${import.meta.env.BASE_URL}data/basemap/land.geojson`, window.location.href).href;
const OFFLINE_STYLE: StyleSpecification = {
  version: 8,
  sources: { land: { type: 'geojson', data: LAND_URL } },
  layers: [
    { id: 'ocean', type: 'background', paint: { 'background-color': '#dfe6ee' } },
    { id: 'land', type: 'fill', source: 'land', paint: { 'fill-color': '#b9c5d3' } },
    { id: 'coast', type: 'line', source: 'land', paint: { 'line-color': '#9fb0c3', 'line-width': 0.6 } },
  ],
};

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };

interface Props {
  hotspots: Hotspot[];
  visibleIds: Set<string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
}

function areaOutline(spot: Hotspot | undefined): FeatureCollection {
  if (!spot) return EMPTY;
  const [w, s, e, n] = spot.bbox;
  return {
    type: 'FeatureCollection',
    features: [{
      type: 'Feature',
      properties: {},
      geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
    }],
  };
}

function addAreaLayer(map: maplibregl.Map) {
  if (map.getSource('area')) return;
  map.addSource('area', { type: 'geojson', data: EMPTY });
  map.addLayer({ id: 'area-fill', type: 'fill', source: 'area', paint: { 'fill-color': '#1A2233', 'fill-opacity': 0.06 } });
  map.addLayer({ id: 'area-line', type: 'line', source: 'area', paint: { 'line-color': '#1A2233', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
}

export function Globe({ hotspots, visibleIds, selectedId, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef(new Map<string, HTMLButtonElement>());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const spotsRef = useRef(hotspots);
  spotsRef.current = hotspots;
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;

  // Create the map and the markers once per hotspot list.
  useEffect(() => {
    if (!container.current) return;
    const wide = window.innerWidth > 900;
    const map = new maplibregl.Map({
      container: container.current,
      style: STYLE_URL,
      center: [30, 20],
      zoom: wide ? 1.85 : 1.1,
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    // Centre the globe in the space beside the panel rather than behind it.
    if (wide) map.easeTo({ center: map.getCenter(), offset: [180, 0], duration: 0 });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'bottom-right');

    let fellBack = false;
    map.on('error', () => {
      if (!fellBack && !map.isStyleLoaded()) {
        fellBack = true;
        map.setStyle(OFFLINE_STYLE);
      }
    });
    map.on('style.load', () => {
      map.setProjection({ type: 'globe' });
      addAreaLayer(map);
      const current = spotsRef.current.find((h) => h.id === selectedRef.current);
      (map.getSource('area') as maplibregl.GeoJSONSource).setData(areaOutline(current));
    });

    for (const spot of hotspots) {
      const el = document.createElement('button');
      el.type = 'button';
      el.className = `marker dance-${spot.dances[0]}${spot.hero ? ' is-hero' : ''}`;
      el.style.setProperty('--c', MODULES[spot.module].color);
      el.setAttribute(
        'aria-label',
        `${spot.name}, ${spot.country}. ${MODULES[spot.module].name}, dance: ${spot.dances.map((d) => DANCES[d].name).join(' and ')}`,
      );
      el.title = spot.name;
      el.innerHTML = '<span class="marker-ring"></span><span class="marker-dot"></span>';
      el.addEventListener('click', (event) => {
        event.stopPropagation();
        onSelectRef.current(spot.id);
      });
      new maplibregl.Marker({ element: el }).setLngLat([spot.lon, spot.lat]).addTo(map);
      markers.current.set(spot.id, el);
    }

    return () => {
      markers.current.clear();
      map.remove();
      mapRef.current = null;
    };
  }, [hotspots]);

  // Show only markers that pass the current filters.
  useEffect(() => {
    markers.current.forEach((el, id) => {
      el.hidden = !visibleIds.has(id);
    });
  }, [visibleIds]);

  // Highlight the selection, outline its area and fly to it.
  useEffect(() => {
    markers.current.forEach((el, id) => el.classList.toggle('is-selected', id === selectedId));
    const map = mapRef.current;
    if (!map) return;
    const spot = hotspots.find((h) => h.id === selectedId);
    const source = map.getSource('area') as maplibregl.GeoJSONSource | undefined;
    source?.setData(areaOutline(spot));
    if (!spot) return;
    const wide = window.innerWidth > 900;
    const [w, s, e, n] = spot.bbox;
    map.fitBounds([[w, s], [e, n]], {
      padding: wide
        ? { top: 80, bottom: 80, left: 400, right: 440 }
        : { top: 40, bottom: window.innerHeight * 0.5, left: 30, right: 30 },
      maxZoom: 9,
      duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 2200,
    });
  }, [selectedId, hotspots]);

  return <div ref={container} className="globe" aria-label="Globe of NISAR hotspots" role="region" />;
}
