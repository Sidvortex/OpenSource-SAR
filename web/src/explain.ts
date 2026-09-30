// Part 6: explanations filled from data/explain.json. Numbers only ever come from the manifest.
import type { Hotspot, LayerManifest } from './types';

export type Level = 'kid' | 'citizen' | 'expert';
type ByLang<T> = Record<string, T>;
export interface ExplainData {
  languages: ByLang<string>;
  levels: ByLang<Record<Level, string>>;
  danceNames: ByLang<Record<string, string>>;
  danceLine: ByLang<string>;
  caveatTitle: ByLang<string>;
  templates: Record<string, ByLang<Record<Level, string>>>;
  caveats: Record<string, ByLang<string>>;
}

export const moduleKey = (m: LayerManifest) => (m.module === 'ground' ? (m.event ? 'quake' : 'subsidence') : m.module);

function vars(m: LayerManifest, spot: Hotspot, lang: string): Record<string, string> {
  const nf = (v: number, d = 0) => v.toLocaleString(lang, { maximumFractionDigits: d, minimumFractionDigits: d });
  const df = (iso: string) => new Date(`${iso}T00:00:00Z`).toLocaleDateString(lang, { day: 'numeric', month: 'long', timeZone: 'UTC' });
  const f = m.frames, first = f[0], last = f[f.length - 1];
  const s = (fr: typeof first, k: string) => fr.stats[k] ?? 0;
  const v: Record<string, string> = { place: spot.name, firstDate: df(first.date), lastDate: df(last.date), pairs: String(f.length) };
  switch (moduleKey(m)) {
    case 'water':
      v.first = nf(s(first, 'open_water_km2')); v.last = nf(s(last, 'open_water_km2'));
      v.ratio = nf(s(last, 'open_water_km2') / Math.max(s(first, 'open_water_km2'), 1), 1); break;
    case 'quake':
      v.event = df(m.event!); v.max = nf(Math.max(...f.map((x) => s(x, 'max_abs_cm')))); break;
    case 'subsidence': {
      const rate = m.layers.find((l) => l.id === 'velocity')?.ramp?.max ?? 0;
      v.rate = nf(rate); v.vert = nf(rate * 1.3);
      v.rms = m.validation?.rms_cm_yr != null ? nf(m.validation.rms_cm_yr, 1) : '—'; break;
    }
    case 'fire': v.burned = nf(s(last, 'burned_km2')); break;
    case 'farming': {
      const peak = f.reduce((a, b) => (s(b, 'growing_pct') > s(a, 'growing_pct') ? b : a));
      v.peak = nf(s(peak, 'growing_pct')); v.peakDate = df(peak.date); break;
    }
    case 'ice': v.first = nf(s(first, 'max_speed_m_day'), 1); v.last = nf(s(last, 'max_speed_m_day'), 1); break;
  }
  return v;
}

export function explain(data: ExplainData, m: LayerManifest, spot: Hotspot, lang: string, level: Level) {
  const key = moduleKey(m);
  const v = vars(m, spot, lang);
  const fill = (t: string) => t.replace(/\{(\w+)\}/g, (_, k: string) => v[k] ?? '');
  const template = data.templates[key]?.[lang]?.[level] ?? data.templates[key]?.en?.[level] ?? '';
  const dance = m.dance ? data.danceLine[lang].replace('{dance}', data.danceNames[lang][m.dance.dance]) : '';
  return { text: fill(template), dance, caveatTitle: data.caveatTitle[lang], caveat: data.caveats[key]?.[lang] ?? '' };
}
