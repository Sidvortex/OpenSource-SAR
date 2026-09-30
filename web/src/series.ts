// Part 4: per-pixel histories. The pipeline writes float32 cubes laid out [time][row][column].
import { siteUrl } from './mapStyle';
import type { LayerManifest } from './types';

export interface SeriesData {
  values: Float32Array;
  sigma: Float32Array | null;
}

export interface Pick {
  lng: number;
  lat: number;
  row: number;
  col: number;
}

async function loadCube(url: string): Promise<Float32Array> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return new Float32Array(await response.arrayBuffer());   // the pipeline writes little-endian, like every browser
}

export async function loadSeries(m: LayerManifest): Promise<SeriesData | null> {
  if (!m.series) return null;
  const base = `data/layers/${m.hotspot}/`;
  const values = await loadCube(siteUrl(base + m.series.file));
  const sigma = m.series.sigma_file ? await loadCube(siteUrl(base + m.series.sigma_file)) : null;
  return { values, sigma };
}

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));

/** Which inspector pixel sits under a clicked point, or null outside the layer. */
export function pixelAt(m: LayerManifest, lng: number, lat: number): Pick | null {
  const s = m.series;
  if (!s) return null;
  const [tl, tr, , bl] = m.bounds;
  const fx = (lng - tl[0]) / (tr[0] - tl[0]);
  const fy = (mercY(tl[1]) - mercY(lat)) / (mercY(tl[1]) - mercY(bl[1]));
  if (fx < 0 || fx >= 1 || fy < 0 || fy >= 1) return null;
  const col = Math.floor((fx * s.full_width) / s.factor);
  const row = Math.floor((fy * s.full_height) / s.factor);
  if (col >= s.width || row >= s.height) return null;
  return { lng, lat, row, col };
}

export function seriesAt(m: LayerManifest, data: SeriesData, pick: Pick) {
  const s = m.series!;
  const at = (cube: Float32Array, i: number) => cube[i * s.width * s.height + pick.row * s.width + pick.col];
  const values = s.dates.map((_, i) => at(data.values, i));
  const sigma = s.dates.map((_, i) => (data.sigma ? at(data.sigma, i) : s.sigma ?? NaN));
  return { values, sigma };
}
