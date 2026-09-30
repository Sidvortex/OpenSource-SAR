import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import type { FeatureCollection } from 'geojson';
import 'maplibre-gl/dist/maplibre-gl.css';
import { DANCES, MODULES } from '../catalog';
import type { Hotspot } from '../types';
import { STYLE_URL, applyOverlay, useOfflineFallback } from '../mapStyle';
import type { Overlay } from '../mapStyle';

const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] };

interface Props {
  hotspots: Hotspot[];
  visibleIds: Set<string>;
  selectedId: string | null;
  onSelect: (id: string) => void;
  overlay: Overlay | null;
  onMapClick?: (lng: number, lat: number) => void;
  pick?: [number, number] | null;
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

function pickPoint(p: [number, number] | null): FeatureCollection {
  return p ? { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: p } }] } : EMPTY;
}

function addAreaLayer(map: maplibregl.Map) {
  if (map.getSource('area')) return;
  map.addSource('area', { type: 'geojson', data: EMPTY });
  map.addLayer({ id: 'area-fill', type: 'fill', source: 'area', paint: { 'fill-color': '#1A2233', 'fill-opacity': 0.06 } });
  map.addLayer({ id: 'area-line', type: 'line', source: 'area', paint: { 'line-color': '#1A2233', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
}

export function Globe({ hotspots, visibleIds, selectedId, onSelect, overlay, onMapClick, pick = null }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markers = useRef(new Map<string, HTMLButtonElement>());
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const spotsRef = useRef(hotspots);
  spotsRef.current = hotspots;
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const clickRef = useRef(onMapClick);
  clickRef.current = onMapClick;
  const pickRef = useRef(pick);
  pickRef.current = pick;

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

    useOfflineFallback(map);
    map.on('style.load', () => {
      map.setProjection({ type: 'globe' });
      addAreaLayer(map);
      const current = spotsRef.current.find((h) => h.id === selectedRef.current);
      (map.getSource('area') as maplibregl.GeoJSONSource).setData(areaOutline(current));
      applyOverlay(map, overlayRef.current, 'area-fill');
      if (!map.getSource('pick')) {
        map.addSource('pick', { type: 'geojson', data: pickPoint(pickRef.current) });
        map.addLayer({ id: 'pick', type: 'circle', source: 'pick', paint: { 'circle-radius': 7, 'circle-color': '#1a2233', 'circle-stroke-color': '#ffffff', 'circle-stroke-width': 2.5 } });
      }
    });
    map.on('click', (e) => clickRef.current?.(e.lngLat.lng, e.lngLat.lat));

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
      new maplibregl.Marker({ element: el, opacityWhenCovered: '0' }).setLngLat([spot.lon, spot.lat]).addTo(map);
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
        ? { top: 60, bottom: 280, left: 400, right: 440 }
        : { top: 40, bottom: window.innerHeight * 0.5, left: 30, right: 30 },
      maxZoom: 9,
      duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 2200,
    });
  }, [selectedId, hotspots]);

  useEffect(() => {
    (mapRef.current?.getSource('pick') as maplibregl.GeoJSONSource | undefined)?.setData(pickPoint(pick));
  }, [pick]);

  // The radar layer for the current date and layer choice.
  useEffect(() => {
    const map = mapRef.current;
    if (map) applyOverlay(map, overlay, 'area-fill');
  }, [overlay]);

  return <div ref={container} className="globe" aria-label="Globe of NISAR hotspots" role="region" />;
}
