import { useCallback, useEffect, useMemo, useState } from 'react';
import { Globe } from './components/Globe';
import { PlaceCard } from './components/PlaceCard';
import { Showcase3D } from './components/Showcase3D';
import { Sidebar } from './components/Sidebar';
import { TimeBar } from './components/TimeBar';
import { MODULE_ORDER } from './catalog';
import { siteUrl } from './mapStyle';
import type { Overlay } from './mapStyle';
import { startFrame } from './types';
import type { Coverage, DanceId, Hotspot, LayerIndex, LayerManifest, ModuleId } from './types';
import { overlayFor } from './components/Showcase3D';

const STEP_MS = 1200;

const BASE = import.meta.env.BASE_URL;

async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { cache: 'no-cache' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function placeFromHash(): string | null {
  const match = window.location.hash.match(/place=([\w-]+)/);
  return match ? match[1] : null;
}

export default function App() {
  const [hotspots, setHotspots] = useState<Hotspot[] | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [modules, setModules] = useState<Set<ModuleId>>(new Set(MODULE_ORDER));
  const [dance, setDance] = useState<DanceId | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(placeFromHash);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [layerIndex, setLayerIndex] = useState<LayerIndex>({ layers: {} });
  const [manifest, setManifest] = useState<LayerManifest | null>(null);
  const [dateIndex, setDateIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [kind, setKind] = useState<string>('water');
  const [showcase, setShowcase] = useState(false);

  useEffect(() => {
    loadJson<{ hotspots: Hotspot[] }>('data/hotspots.json')
      .then((d) => setHotspots(d.hotspots))
      .catch((e: Error) => setError(e.message));
    loadJson<Coverage>('data/coverage.json')
      .then(setCoverage)
      .catch(() => setCoverage(null));
    loadJson<LayerIndex>('data/layers/index.json')
      .then(setLayerIndex)
      .catch(() => setLayerIndex({ layers: {} }));
  }, []);

  // Load the selected place's layers, if the pipeline has built any.
  useEffect(() => {
    setManifest(null);
    setPlaying(false);
    setShowcase(false);
    if (!selectedId || !layerIndex.layers[selectedId]) return;
    let cancelled = false;
    loadJson<LayerManifest>(`data/layers/${selectedId}/manifest.json`)
      .then((m) => {
        if (cancelled) return;
        setManifest(m);
        setDateIndex(startFrame(m));
        setKind(m.layers[0].id);
        // Warm the cache so playback doesn't flicker.
        for (const f of m.frames) for (const file of Object.values(f.files)) new Image().src = siteUrl(`data/layers/${m.hotspot}/${file}`);
      })
      .catch(() => setManifest(null));
    return () => { cancelled = true; };
  }, [selectedId, layerIndex]);

  // Playback steps through the passes and loops.
  useEffect(() => {
    if (!playing || !manifest) return;
    const timer = window.setInterval(() => setDateIndex((i) => (i + 1) % manifest.frames.length), STEP_MS);
    return () => window.clearInterval(timer);
  }, [playing, manifest]);

  const overlay = useMemo<Overlay | null>(() => {
    if (!manifest || showcase) return null;
    return overlayFor(manifest, Math.min(dateIndex, manifest.frames.length - 1), kind);
  }, [manifest, dateIndex, kind, showcase]);

  // Keep the selected place in the URL so any view can be shared as a link.
  useEffect(() => {
    const hash = selectedId ? `#place=${selectedId}` : ' ';
    if (window.location.hash !== hash.trim()) history.replaceState(null, '', hash);
  }, [selectedId]);
  useEffect(() => {
    const onHash = () => setSelectedId(placeFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const visible = useMemo(() => {
    if (!hotspots) return [];
    const q = query.trim().toLowerCase();
    return hotspots.filter((h) =>
      modules.has(h.module) &&
      (dance === null || h.dances.includes(dance)) &&
      (q === '' || `${h.name} ${h.country}`.toLowerCase().includes(q)),
    );
  }, [hotspots, query, modules, dance]);
  const visibleIds = useMemo(() => new Set(visible.map((h) => h.id)), [visible]);

  const toggleModule = useCallback((m: ModuleId) => {
    setModules((prev) => {
      const next = new Set(prev);
      if (next.has(m)) next.delete(m); else next.add(m);
      return next;
    });
  }, []);

  const select = useCallback((id: string) => {
    setSelectedId(id);
    setSheetOpen(false);
  }, []);

  if (error) {
    return (
      <main className="fatal">
        <h1 className="wordmark">SARabande</h1>
        <p>The hotspot list did not load ({error}). Run <code>npm run dev</code> from the web folder so the data is copied in.</p>
      </main>
    );
  }
  if (!hotspots) return <main className="loading" aria-busy="true">Loading the globe</main>;

  const selected = hotspots.find((h) => h.id === selectedId) ?? null;
  return (
    <main className="app">
      <Globe hotspots={hotspots} visibleIds={visibleIds} selectedId={selectedId} onSelect={select} overlay={overlay} />
      <Sidebar
        query={query} onQuery={setQuery}
        modules={modules} onToggleModule={toggleModule}
        dance={dance} onDance={setDance}
        places={visible} selectedId={selectedId} onSelect={select}
        open={sheetOpen} onToggleOpen={() => setSheetOpen((o) => !o)}
      />
      {selected && (
        <PlaceCard spot={selected} coverage={coverage} manifest={manifest}
          onOpen3D={() => { setPlaying(false); setShowcase(true); }}
          onClose={() => setSelectedId(null)} />
      )}
      {manifest && !showcase && (
        <TimeBar manifest={manifest} index={Math.min(dateIndex, manifest.frames.length - 1)} onIndex={setDateIndex}
          playing={playing} onPlaying={setPlaying} kind={kind} onKind={setKind} />
      )}
      {manifest && selected && showcase && (
        <Showcase3D spot={selected} manifest={manifest} kind={kind} onClose={() => setShowcase(false)} />
      )}
    </main>
  );
}
