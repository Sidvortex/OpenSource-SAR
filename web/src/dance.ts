// The dance classifier, v1 (rules). Mirrors pipeline/dance.py exactly; both must pass
// data/dance_tests.json (npm run test:dance and python pipeline/dance.py --test).
import type { DanceId } from './types';

export interface DanceResult {
  dance: DanceId;
  confidence: 'high' | 'medium' | 'low';
  reason: string;
}

const median = (v: number[]) => {
  const s = [...v].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/** Least-squares polynomial fit; returns coefficients lowest power first. */
function polyfit(x: number[], y: number[], degree: 1 | 2): number[] {
  const k = degree + 1;
  const a = Array.from({ length: k }, () => new Array(k + 1).fill(0));
  x.forEach((xi, i) => {
    for (let r = 0; r < k; r++) {
      for (let c = 0; c < k; c++) a[r][c] += xi ** (r + c);
      a[r][k] += xi ** r * y[i];
    }
  });
  for (let p = 0; p < k; p++) {                        // Gaussian elimination with pivoting
    let best = p;
    for (let r = p + 1; r < k; r++) if (Math.abs(a[r][p]) > Math.abs(a[best][p])) best = r;
    [a[p], a[best]] = [a[best], a[p]];
    for (let r = 0; r < k; r++) {
      if (r === p || a[p][p] === 0) continue;
      const f = a[r][p] / a[p][p];
      for (let c = p; c <= k; c++) a[r][c] -= f * a[p][c];
    }
  }
  return a.map((row, i) => (row[i] === 0 ? 0 : row[k] / row[i]));
}

const evalPoly = (c: number[], x: number) => c.reduce((sum, ci, i) => sum + ci * x ** i, 0);
const rss = (c: number[], x: number[], y: number[]) => x.reduce((s, xi, i) => s + (evalPoly(c, xi) - y[i]) ** 2, 0);
const fmt = (v: number, unit: string) => `${v >= 0 ? '+' : ''}${v.toFixed(Math.abs(v) >= 10 ? 0 : 1)}${unit ? ` ${unit}` : ''}`;

export function classify(tIn: number[], yIn: number[], sigmaIn?: number | number[] | null, unit = '', when?: string[]): DanceResult {
  const idx = yIn.map((_, i) => i).filter((i) => Number.isFinite(yIn[i]));
  const labels = idx.map((i) => when?.[i] ?? `day ${tIn[i].toFixed(0)}`);
  const t = idx.map((i) => tIn[i]);
  const y = idx.map((i) => yIn[i]);
  const sig = idx.map((i) => (Array.isArray(sigmaIn) ? sigmaIn[i] : sigmaIn ?? NaN));
  const n = y.length;
  if (n < 3) return { dance: 'still', confidence: 'low', reason: 'Too few measurements to tell yet.' };
  const goodSig = sig.filter((s) => Number.isFinite(s) && s > 0);
  const diffs = y.slice(1).map((v, i) => Math.abs(v - y[i]));
  const noise = Math.max(goodSig.length ? median(goodSig) : median(diffs) / 0.6745 / Math.SQRT2, 1e-9);
  const amp = Math.max(...y) - Math.min(...y);
  if (amp < 3 * noise) return { dance: 'still', confidence: 'high', reason: 'Every change stays within the measurement noise.' };
  const span = t[n - 1] - t[0] || 1;
  const x = t.map((ti) => (ti - t[0]) / span);
  const lin = polyfit(x, y, 1);
  const quad = polyfit(x, y, 2);
  const rssLin = rss(lin, x, y);
  const rssQuad = rss(quad, x, y);
  let bestK = 1, rssStep = Infinity, jump = 0;
  for (let k = 1; k < n; k++) {
    const a = y.slice(0, k), b = y.slice(k);
    const ma = a.reduce((s, v) => s + v, 0) / a.length, mb = b.reduce((s, v) => s + v, 0) / b.length;
    const r = a.reduce((s, v) => s + (v - ma) ** 2, 0) + b.reduce((s, v) => s + (v - mb) ** 2, 0);
    if (r < rssStep) { bestK = k; rssStep = r; jump = mb - ma; }
  }
  const confidence = amp > 10 * noise ? 'high' : 'medium';
  const floor = n * noise ** 2;
  if (Math.abs(jump) > 4 * noise && rssStep < 0.35 * Math.max(rssLin, floor) && rssStep < 0.5 * Math.max(rssQuad, floor)) {
    return { dance: 'tango', confidence, reason: `A sudden change of ${fmt(jump, unit)} between ${labels[bestK - 1]} and ${labels[bestK]}.` };
  }
  const [, c1, c2] = quad;
  if (rssQuad < 0.6 * Math.max(rssLin, floor) && Math.abs(c2) * 0.25 > 1.5 * noise) {
    const vertex = c2 ? -c1 / (2 * c2) : -1;
    if (vertex > 0.15 && vertex < 0.85) {
      return { dance: 'waltz', confidence, reason: `It ${c2 < 0 ? 'rose and then fell' : 'fell and then rose'} within the period, like a seasonal cycle.` };
    }
    const slopeStart = c1, slopeEnd = c1 + 2 * c2;
    if (Math.abs(slopeEnd) > Math.abs(slopeStart) && Math.sign(slopeEnd) === Math.sign(lin[1])) {
      return { dance: 'crescendo', confidence, reason: 'The change keeps getting faster.' };
    }
  }
  if (Math.abs(lin[1]) > 3 * noise) {
    return { dance: 'march', confidence, reason: `A steady trend of about ${fmt((lin[1] / span) * 12, unit)} every 12 days.` };
  }
  return { dance: 'still', confidence: 'medium', reason: 'No clear pattern beyond the noise.' };
}
