import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, PointerEvent } from 'react';
import maplibregl from 'maplibre-gl';
import { formatDate } from '../catalog';
import { STYLE_URL, TERRAIN_ATTRIBUTION, TERRAIN_URL, applyOverlay, siteUrl, useOfflineFallback } from '../mapStyle';
import type { Overlay } from '../mapStyle';
import type { Hotspot, LayerKind, LayerManifest } from '../types';

interface Props {
  spot: Hotspot;
  manifest: LayerManifest;
  kind: LayerKind;
  onClose: () => void;
}

const REVEAL_MS = 7000;
const km2 = (n: number) => `${Math.round(n).toLocaleString('en')} km²`;
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function overlayFor(manifest: LayerManifest, index: number, kind: LayerKind): Overlay {
  const d = manifest.dates[index];
  return {
    url: siteUrl(`data/layers/${manifest.hotspot}/${kind === 'water' ? d.water : d.radar}`),
    coordinates: manifest.bounds,
    opacity: kind === 'water' ? 0.85 : 0.9,
  };
}

/** A 3D map: free basemap, free terrain draped with the chosen pass. */
function createMap(container: HTMLElement, spot: Hotspot, exaggeration: number, overlay: () => Overlay) {
  const map = new maplibregl.Map({
    container,
    style: STYLE_URL,
    bounds: [[spot.bbox[0], spot.bbox[1]], [spot.bbox[2], spot.bbox[3]]],
    fitBoundsOptions: { padding: 40 },
    pitch: 58,
    bearing: -24,
    maxPitch: 80,
    attributionControl: false,
  });
  useOfflineFallback(map);
  map.once('load', () => map.jumpTo({ zoom: map.getZoom() + 0.6 }));   // frame the place, not the whole box
  // If elevation tiles can't load (offline, blocked), drop terrain so the layers still show flat.
  map.on('error', (event) => {
    const sourceId = (event as { sourceId?: string }).sourceId;
    if ((sourceId === 'dem' || sourceId === 'dem-shade') && map.getTerrain()) {
      map.setTerrain(null);
      if (map.getLayer('hillshade')) map.removeLayer('hillshade');
    }
  });
  map.on('style.load', () => {
    if (TERRAIN_URL) {
      for (const id of ['dem', 'dem-shade']) {
        if (!map.getSource(id)) {
          map.addSource(id, { type: 'raster-dem', tiles: [TERRAIN_URL], tileSize: 256, encoding: 'terrarium', maxzoom: 14, attribution: TERRAIN_ATTRIBUTION });
        }
      }
      if (!map.getLayer('hillshade')) {
        map.addLayer({ id: 'hillshade', type: 'hillshade', source: 'dem-shade', paint: { 'hillshade-exaggeration': 0.35 } });
      }
      map.setTerrain({ source: 'dem', exaggeration });
    }
    map.setSky({ 'sky-color': '#1c2536', 'horizon-color': '#51607a', 'fog-color': '#c9d3de', 'sky-horizon-blend': 0.6, 'horizon-fog-blend': 0.7, 'fog-ground-blend': 0.85 });
    applyOverlay(map, overlay());
  });
  return map;
}

export function Showcase3D({ spot, manifest, kind: initialKind, onClose }: Props) {
  const last = manifest.dates.length - 1;
  const [before, setBefore] = useState(0);
  const [after, setAfter] = useState(last);
  const [kind, setKind] = useState<LayerKind>(initialKind);
  const [split, setSplit] = useState(50);
  const [exaggeration, setExaggeration] = useState(1.5);
  const [revealing, setRevealing] = useState(false);

  const stage = useRef<HTMLDivElement>(null);
  const beforeBox = useRef<HTMLDivElement>(null);
  const afterBox = useRef<HTMLDivElement>(null);
  const maps = useRef<{ before: maplibregl.Map; after: maplibregl.Map } | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const state = useRef({ before, after, kind });
  state.current = { before, after, kind };

  // Build both maps once and keep their cameras locked together.
  useEffect(() => {
    if (!beforeBox.current || !afterBox.current) return;
    const a = createMap(beforeBox.current, spot, exaggeration, () => overlayFor(manifest, state.current.before, state.current.kind));
    const b = createMap(afterBox.current, spot, exaggeration, () => overlayFor(manifest, state.current.after, state.current.kind));
    b.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
    b.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
    let syncing = false;
    const follow = (source: maplibregl.Map, target: maplibregl.Map) => () => {
      if (syncing) return;
      syncing = true;
      target.jumpTo({ center: source.getCenter(), zoom: source.getZoom(), bearing: source.getBearing(), pitch: source.getPitch() });
      syncing = false;
    };
    a.on('move', follow(a, b));
    b.on('move', follow(b, a));
    maps.current = { before: a, after: b };
    closeButton.current?.focus();
    return () => {
      a.remove();
      b.remove();
      maps.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [spot, manifest]);

  useEffect(() => { if (maps.current) applyOverlay(maps.current.before, overlayFor(manifest, before, kind)); }, [before, kind, manifest]);
  useEffect(() => { if (maps.current) applyOverlay(maps.current.after, overlayFor(manifest, after, kind)); }, [after, kind, manifest]);
  useEffect(() => {
    if (!maps.current || !TERRAIN_URL) return;
    for (const m of [maps.current.before, maps.current.after]) {
      if (m.getSource('dem')) m.setTerrain({ source: 'dem', exaggeration });
    }
  }, [exaggeration]);

  // The reveal: the "after" view sweeps across while the camera circles the place.
  const reveal = useCallback(() => {
    if (!maps.current) return;
    if (reducedMotion()) { setSplit(50); return; }
    setRevealing(true);
    const start = performance.now();
    const bearing = maps.current.after.getBearing();
    maps.current.after.easeTo({ bearing: bearing + 55, duration: REVEAL_MS, easing: (t) => t });
    const tick = (now: number) => {
      const t = Math.min((now - start) / REVEAL_MS, 1);
      setSplit(100 - 100 * (t * t * (3 - 2 * t)));
      if (t < 1) requestAnimationFrame(tick);
      else setRevealing(false);
    };
    setSplit(100);
    requestAnimationFrame(tick);
  }, []);

  const dragTo = (event: PointerEvent<HTMLDivElement>) => {
    const rect = stage.current?.getBoundingClientRect();
    if (!rect) return;
    setSplit(Math.min(100, Math.max(0, ((event.clientX - rect.left) / rect.width) * 100)));
  };
  const onDividerKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 10 : 2;
    if (event.key === 'ArrowLeft') setSplit((s) => Math.max(0, s - step));
    if (event.key === 'ArrowRight') setSplit((s) => Math.min(100, s + step));
    if (event.key === 'Home') setSplit(0);
    if (event.key === 'End') setSplit(100);
  };
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const b = manifest.dates[before];
  const a = manifest.dates[after];
  const total = (d: typeof a) => d.open_water_km2 + d.flooded_veg_km2;
  const change = total(b) > 0 ? Math.round((total(a) / total(b)) * 10) / 10 : null;

  return (
    <div className="showcase" role="dialog" aria-modal="true" aria-labelledby="showcase-title">
      <header className="showcase-head">
        <div>
          <h2 id="showcase-title" className="showcase-title">{spot.name} in 3D</h2>
          <p className="showcase-sub">
            {change && change > 1 ? `Water covered ${change} times more ground on ${formatDate(a.date)} than on ${formatDate(b.date)}.` : 'Drag the divider to compare the two passes.'}
          </p>
        </div>
        <button ref={closeButton} type="button" className="showcase-close" onClick={onClose}>Close 3D view</button>
      </header>
      {manifest.synthetic && <p className="synthetic synthetic-dark">Synthetic demo data, not NISAR measurements.</p>}

      <div ref={stage} className="stage">
        <div ref={beforeBox} className="stage-map" />
        <div ref={afterBox} className="stage-map" style={{ clipPath: `inset(0 0 0 ${split}%)` }} />
        <div className="side-label side-before">
          <strong>Before, {formatDate(b.date)}</strong>
          <span>Open water {km2(b.open_water_km2)}</span>
        </div>
        <div className="side-label side-after">
          <strong>After, {formatDate(a.date)}</strong>
          <span>Open water {km2(a.open_water_km2)}</span>
        </div>
        <div className="divider" style={{ left: `${split}%` }}
          role="slider" tabIndex={0} aria-label="Before and after divider" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(split)}
          onKeyDown={onDividerKey}
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); dragTo(e); }}
          onPointerMove={(e) => { if (e.buttons) dragTo(e); }}>
          <span className="divider-handle" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M9 6l-6 6 6 6M15 6l6 6-6 6" /></svg>
          </span>
        </div>
      </div>

      <footer className="showcase-controls">
        <button type="button" className="primary" onClick={reveal} disabled={revealing}>{revealing ? 'Revealing' : 'Play reveal'}</button>
        <label>Before
          <select value={before} onChange={(e) => setBefore(Number(e.target.value))}>
            {manifest.dates.map((d, i) => <option key={d.date} value={i} disabled={i >= after}>{formatDate(d.date)}</option>)}
          </select>
        </label>
        <label>After
          <select value={after} onChange={(e) => setAfter(Number(e.target.value))}>
            {manifest.dates.map((d, i) => <option key={d.date} value={i} disabled={i <= before}>{formatDate(d.date)}</option>)}
          </select>
        </label>
        <div className="segmented segmented-dark" role="group" aria-label="Layer">
          <button type="button" aria-pressed={kind === 'water'} onClick={() => setKind('water')}>Water map</button>
          <button type="button" aria-pressed={kind === 'radar'} onClick={() => setKind('radar')}>Radar image</button>
        </div>
        <label className="range">Terrain height x{exaggeration.toFixed(1)}
          <input type="range" min={1} max={4} step={0.5} value={exaggeration} onChange={(e) => setExaggeration(Number(e.target.value))} />
        </label>
      </footer>
    </div>
  );
}
