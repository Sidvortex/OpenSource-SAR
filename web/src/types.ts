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

export interface LayerDate {
  date: string;
  water: string;
  radar: string;
  open_water_km2: number;
  flooded_veg_km2: number;
  threshold_db: number;
  sources: string[];
}

export interface LayerManifest {
  hotspot: string;
  module: ModuleId;
  title: string;
  synthetic: boolean;
  created: string;
  product: string;
  bounds: [[number, number], [number, number], [number, number], [number, number]];
  reference_date: string;
  method: string[];
  legend: { id: string; label: string; color: string }[];
  dates: LayerDate[];
}

export interface LayerIndex {
  layers: Record<string, { module: ModuleId; synthetic: boolean; updated: string }>;
}

export type LayerKind = 'water' | 'radar';
