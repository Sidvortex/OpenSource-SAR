import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type maplibregl from 'maplibre-gl';
import { AreaCheck } from './components/AreaCheck';
import { Globe } from './components/Globe';
import { Inspector } from './components/Inspector';
import { PlaceCard } from './components/PlaceCard';
import { RadarExplainer } from './components/RadarExplainer';
import { Showcase3D, overlayFor } from './components/Showcase3D';
import { Sidebar } from './components/Sidebar';
import { StoryMode } from './components/StoryMode';
import type { Story, StoryStep } from './components/StoryMode';
import { TimeBar } from './components/TimeBar';
import { MODULE_ORDER } from './catalog';
import type { ExplainData } from './explain';
import { siteUrl } from './mapStyle';
import type { Overlay } from './mapStyle';
import { loadSeries, pixelAt } from './series';
import type { Pick, SeriesData } from './series';
import { startFrame } from './types';
import type { Coverage, DanceId, Hotspot, LayerIndex, LayerManifest, ModuleId } from './types';

const STEP_MS = 1200;
type Box = [number, number, number, number];
type Want = { layer?: string; frame?: StoryStep['frame'] };

async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(siteUrl(path), { cache: 'no-cache' });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function readHash() {
  const p = new URLSearchParams(window.location.hash.slice(1));
  const frame = p.get('frame');
  return { place: p.get('place'), want: { layer: p.get('layer') ?? undefined, frame: frame === null ? undefined : Number(frame) } as Want };
}

function resolveFrame(m: LayerManifest, f?: StoryStep['frame']) {
  if (f === undefined || f === 'event') return startFrame(m);
  if (f === 'first') return 0;
  if (f === 'last') return m.frames.length - 1;
  return Math.min(Math.max(Math.round(f), 0), m.frames.length - 1);
}

export default function App() {
  const [hotspots, setHotspots] = useState<Hotspot[] | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [modules, setModules] = useState<Set<ModuleId>>(new Set(MODULE_ORDER));
  const [dance, setDance] = useState<DanceId | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [layerIndex, setLayerIndex] = useState<LayerIndex>({ layers: {} });
  const [manifest, setManifest] = useState<LayerManifest | null>(null);
  const [dateIndex, setDateIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [kind, setKind] = useState('water');
  const [showcase, setShowcase] = useState(false);
  const [seriesData, setSeriesData] = useState<SeriesData | null>(null);
  const [pick, setPick] = useState<Pick | null>(null);
  const [explainData, setExplainData] = useState<ExplainData | null>(null);
  const [stories, setStories] = useState<Story[]>([]);
  const [story, setStory] = useState<{ story: Story; step: number } | null>(null);
  const [radarOpen, setRadarOpen] = useState(false);
  const [areaMode, setAreaMode] = useState(false);
  const [corners, setCorners] = useState<[number, number][]>([]);
  const want = useRef<Want | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    loadJson<{ hotspots: Hotspot[] }>('data/hotspots.json').then((d) => setHotspots(d.hotspots)).catch((e: Error) => setError(e.message));
    loadJson<Coverage>('data/coverage.json').then(setCoverage).catch(() => setCoverage(null));
    loadJson<LayerIndex>('data/layers/index.json').then(setLayerIndex).catch(() => undefined);
    loadJson<ExplainData>('data/explain.json').then(setExplainData).catch(() => undefined);
    loadJson<{ stories: Story[] }>('data/stories.json').then((d) => setStories(d.stories)).catch(() => undefined);
    const fromLink = readHash();
    if (fromLink.place) { want.current = fromLink.want; setSelectedId(fromLink.place); }
    const onHash = () => {
      const h = readHash();
      if (h.place) { want.current = h.want; setSelectedId(h.place); }
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // Load the selected place's layers, then apply any requested layer and frame (from a link or a story).
  useEffect(() => {
    setPlaying(false); setShowcase(false); setPick(null);
    if (!selectedId || !layerIndex.layers[selectedId]) { setManifest(null); setSeriesData(null); return; }
    if (manifest?.hotspot === selectedId) {
      const w = want.current; want.current = null;
      if (w?.layer && manifest.layers.some((l) => l.id === w.layer)) setKind(w.layer);
      if (w?.frame !== undefined) setDateIndex(resolveFrame(manifest, w.frame));
      return;
    }
    let cancelled = false;
    loadJson<LayerManifest>(`data/layers/${selectedId}/manifest.json`).then((m) => {
      if (cancelled) return;
      const w = want.current; want.current = null;
      setManifest(m);
      setDateIndex(resolveFrame(m, w?.frame));
      setKind(w?.layer && m.layers.some((l) => l.id === w.layer) ? w.layer : m.layers[0].id);
      setSeriesData(null);
      loadSeries(m).then((d) => { if (!cancelled) setSeriesData(d); }).catch(() => undefined);
      for (const f of m.frames) for (const file of Object.values(f.files)) new Image().src = siteUrl(`data/layers/${m.hotspot}/${file}`);
    }).catch(() => setManifest(null));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, layerIndex]);

  // Every view is a shareable link: place, layer and frame.
  useEffect(() => {
    const p = new URLSearchParams();
    if (selectedId) p.set('place', selectedId);
    if (manifest && manifest.hotspot === selectedId) { p.set('layer', kind); p.set('frame', String(dateIndex)); }
    const hash = p.toString() ? `#${p}` : ' ';
    if (window.location.hash !== hash.trim()) history.replaceState(null, '', hash);
  }, [selectedId, manifest, kind, dateIndex]);

  useEffect(() => {
    if (!playing || !manifest) return;
    const timer = window.setInterval(() => setDateIndex((i) => (i + 1) % manifest.frames.length), STEP_MS);
    return () => window.clearInterval(timer);
  }, [playing, manifest]);

  const overlay = useMemo<Overlay | null>(() => {
    if (!manifest || showcase || manifest.hotspot !== selectedId) return null;
    return overlayFor(manifest, Math.min(dateIndex, manifest.frames.length - 1), kind);
  }, [manifest, dateIndex, kind, showcase, selectedId]);

  const visible = useMemo(() => {
    if (!hotspots) return [];
    const q = query.trim().toLowerCase();
    return hotspots.filter((h) => modules.has(h.module) && (dance === null || h.dances.includes(dance)) &&
      (q === '' || `${h.name} ${h.country}`.toLowerCase().includes(q)));
  }, [hotspots, query, modules, dance]);
  const visibleIds = useMemo(() => new Set(visible.map((h) => h.id)), [visible]);

  const moving = useMemo(() => {
    if (!hotspots) return [];
    return Object.entries(layerIndex.layers)
      .map(([id, info]) => ({ id, info, spot: hotspots.find((h) => h.id === id) }))
      .filter((x) => x.spot)
      .sort((a, b) => (b.info.latest ?? '').localeCompare(a.info.latest ?? ''))
      .map((x) => ({ id: x.id, name: x.spot!.name, dance: x.info.dance ?? null, latest: x.info.latest ?? null }));
  }, [hotspots, layerIndex]);

  const box = useMemo<Box | null>(() => (corners.length === 2
    ? [Math.min(corners[0][0], corners[1][0]), Math.min(corners[0][1], corners[1][1]), Math.max(corners[0][0], corners[1][0]), Math.max(corners[0][1], corners[1][1])]
    : null), [corners]);

  const onMapClick = useCallback((lng: number, lat: number) => {
    if (areaMode) { setCorners((c) => (c.length >= 2 ? [[lng, lat]] : [...c, [lng, lat]])); return; }
    if (!manifest || !seriesData || manifest.hotspot !== selectedId) return;
    const p = pixelAt(manifest, lng, lat);
    if (p) setPick(p);
  }, [areaMode, manifest, seriesData, selectedId]);

  const select = useCallback((id: string) => { setAreaMode(false); setSelectedId(id); setSheetOpen(false); }, []);

  const goToStep = useCallback((s: Story, i: number) => {
    const step = s.steps[Math.max(0, Math.min(i, s.steps.length - 1))];
    setStory({ story: s, step: s.steps.indexOf(step) });
    setAreaMode(false);
    want.current = { layer: step.layer, frame: step.frame };
    if (step.place === selectedId) {
      // Same place: apply straight away (the load effect won't run again).
      if (manifest?.hotspot === step.place) {
        want.current = null;
        if (manifest.layers.some((l) => l.id === step.layer)) setKind(step.layer);
        setDateIndex(resolveFrame(manifest, step.frame));
        setPlaying(false);
      }
    } else {
      setSelectedId(step.place);
    }
  }, [selectedId, manifest]);

  const snapshot = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    map.once('render', () => {
      const link = document.createElement('a');
      link.download = `sarabande-${selectedId ?? 'globe'}.png`;
      link.href = map.getCanvas().toDataURL('image/png');
      link.click();
    });
    map.triggerRepaint();
  }, [selectedId]);

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
  const placeManifest = manifest && manifest.hotspot === selectedId ? manifest : null;
  return (
    <main className="app">
      <Globe hotspots={hotspots} visibleIds={visibleIds} selectedId={selectedId} onSelect={select} overlay={overlay}
        onMapClick={onMapClick} pick={pick && !showcase ? [pick.lng, pick.lat] : null}
        drawBox={areaMode ? box : null} onReady={(m) => { mapRef.current = m; }} />
      <Sidebar
        query={query} onQuery={setQuery} modules={modules} onToggleModule={(m) => setModules((prev) => {
          const next = new Set(prev); if (next.has(m)) next.delete(m); else next.add(m); return next;
        })}
        dance={dance} onDance={setDance} places={visible} selectedId={selectedId} onSelect={select}
        open={sheetOpen} onToggleOpen={() => setSheetOpen((o) => !o)}
        moving={moving} stories={stories} onStory={(s) => goToStep(s, 0)}
        onRadar={() => setRadarOpen(true)}
        onArea={() => { setSelectedId(null); setCorners([]); setAreaMode(true); setSheetOpen(false); }}
      />
      {selected && !areaMode && (
        <PlaceCard spot={selected} coverage={coverage} manifest={placeManifest} explainData={explainData}
          canInspect={!!seriesData && !!placeManifest}
          inspector={placeManifest && seriesData && pick ? <Inspector manifest={placeManifest} data={seriesData} pick={pick} onClose={() => setPick(null)} /> : null}
          onOpen3D={() => { setPlaying(false); setShowcase(true); }}
          onClose={() => setSelectedId(null)} />
      )}
      {areaMode && <AreaCheck box={box} onClose={() => { setAreaMode(false); setCorners([]); }} />}
      {placeManifest && !showcase && (
        <TimeBar manifest={placeManifest} index={Math.min(dateIndex, placeManifest.frames.length - 1)} onIndex={setDateIndex}
          playing={playing} onPlaying={setPlaying} kind={kind} onKind={setKind} onSnapshot={snapshot} />
      )}
      {story && (
        <StoryMode story={story.story} step={story.step}
          onStep={(i) => goToStep(story.story, i)} onExit={() => setStory(null)} />
      )}
      {placeManifest && selected && showcase && (
        <Showcase3D spot={selected} manifest={placeManifest} kind={kind} onClose={() => setShowcase(false)} />
      )}
      {radarOpen && <RadarExplainer onClose={() => setRadarOpen(false)} />}
    </main>
  );
}
