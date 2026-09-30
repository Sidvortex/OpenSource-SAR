export type ModuleId = 'ground' | 'water' | 'fire' | 'farming' | 'ice';
export type DanceId = 'waltz' | 'march' | 'tango' | 'crescendo' | 'still';

export interface Hotspot {
  id: string;
  name: string;
  country: string;
  lon: number;
  lat: number;
  /** west, south, east, north */
  bbox: [number, number, number, number];
  module: ModuleId;
  dances: DanceId[];
  hero?: boolean;
  layerPart: number;
  products: string[];
  why: string;
  event?: string;
  sensitive?: string;
  caution?: string;
}

export interface CoverageProduct {
  stacks: number;
  items: number;
  best_stack: string | null;
  best_items: number;
  first: string | null;
  last: string | null;
  size_gb: number;
}

export interface CoverageEntry {
  verdict: 'pass' | 'fail' | null;
  score: number | null;
  need: number;
  rule: string;
  products: Record<string, CoverageProduct>;
  errors: string[];
}

export interface Coverage {
  checked: string | null;
  maturity?: string;
  note?: string;
  hotspots: Record<string, CoverageEntry>;
}

export interface Ramp {
  colors: string[];
  min: number;
  max: number;
  unit: string;
  low: string;
  high: string;
}

export interface LayerDef {
  id: string;
  label: string;
  opacity: number;
  legend?: { label: string; color: string }[];
  ramp?: Ramp;
  note?: string;
}

export interface StatDef {
  id: string;
  label: string;
  unit: string;
  color?: string;
}

export interface Frame {
  date: string;
  start?: string;
  label: string;
  files: Record<string, string>;
  stats: Record<string, number>;
  sources: string[];
}

export interface LayerManifest {
  hotspot: string;
  module: ModuleId;
  title: string;
  headline: string;
  synthetic: boolean;
  created: string;
  product: string;
  bounds: [[number, number], [number, number], [number, number], [number, number]];
  event: string | null;
  frame_noun: string;
  sides?: [string, string];
  side_stat?: StatDef;
  compare?: [number, number];
  layers: LayerDef[];
  stats: StatDef[];
  chart: { area: string; line: string | null; label: string };
  method: string[];
  frames: Frame[];
  series?: SeriesDef;
  dance?: MeasuredDance;
}

export interface SeriesDef {
  file: string;
  sigma_file?: string;
  count: number;
  width: number;
  height: number;
  factor: number;
  full_width: number;
  full_height: number;
  dates: string[];
  label: string;
  unit: string;
  sigma?: number;
  threshold?: number;
  threshold_label?: string;
}

export interface MeasuredDance {
  dance: DanceId;
  confidence: 'high' | 'medium' | 'low';
  reason: string;
  basis?: string;
}

export interface LayerIndex {
  layers: Record<string, { module: ModuleId; synthetic: boolean; updated: string }>;
}

/** The frame to show first: the one spanning the event, or the latest. */
export function startFrame(m: LayerManifest): number {
  if (m.event) {
    const i = m.frames.findIndex((f) => f.start !== undefined && f.start < m.event! && m.event! < f.date);
    if (i >= 0) return i;
  }
  return m.frames.length - 1;
}
