import type { DanceId, ModuleId } from './types';

export const MODULES: Record<ModuleId, { name: string; color: string; product: string }> = {
  ground: { name: 'Ground motion', color: '#7A5AF8', product: 'GUNW interferograms' },
  water: { name: 'Water and wetlands', color: '#1F8FD1', product: 'GCOV backscatter' },
  fire: { name: 'Fire and forest', color: '#E0552B', product: 'GCOV cross-polarised backscatter' },
  farming: { name: 'Farming', color: '#8FA61E', product: 'GCOV time series and SME2 soil moisture' },
  ice: { name: 'Ice', color: '#2FA7B4', product: 'GOFF pixel offsets' },
};

export const MODULE_ORDER: ModuleId[] = ['ground', 'water', 'fire', 'farming', 'ice'];

export const DANCES: Record<DanceId, { name: string; pattern: string }> = {
  waltz: { name: 'Waltz', pattern: 'A seasonal cycle that repeats' },
  march: { name: 'March', pattern: 'A steady trend in one direction' },
  tango: { name: 'Tango', pattern: 'A sudden jump or break' },
  crescendo: { name: 'Crescendo', pattern: 'Movement that keeps speeding up' },
  still: { name: 'Still', pattern: 'No significant change' },
};

export const DANCE_ORDER: DanceId[] = ['waltz', 'march', 'tango', 'crescendo', 'still'];

export function bboxToWkt([w, s, e, n]: [number, number, number, number]): string {
  return `POLYGON((${w} ${s},${e} ${s},${e} ${n},${w} ${n},${w} ${s}))`;
}

/** ASF Vertex search for PROVISIONAL NISAR products over an area. Free, no login to browse. */
export function vertexUrl(bbox: [number, number, number, number]): string {
  const polygon = encodeURIComponent(bboxToWkt(bbox));
  return `https://search.asf.alaska.edu/#/?dataset=NISAR&dataMaturity=PROVISIONAL&polygon=${polygon}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return 'unknown';
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString('en', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
}
