import { useMemo } from 'react';
import { DANCES, formatDate } from '../catalog';
import { classify } from '../dance';
import { seriesAt } from '../series';
import type { Pick, SeriesData } from '../series';
import type { LayerManifest } from '../types';

const W = 320;
const H = 130;
const P = { l: 40, r: 10, t: 10, b: 22 };
const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 864e5;
const short = (iso: string) => formatDate(iso).replace(/, \d{4}$/, '');
const coord = (v: number, pos: string, neg: string) => `${Math.abs(v).toFixed(3)}°${v >= 0 ? pos : neg}`;

/** Part 10: hear the spot's history. Higher pitch = higher value; one note per pass. */
function sonify(values: number[]) {
  const finite = values.filter(Number.isFinite);
  if (!finite.length) return;
  const lo = Math.min(...finite), hi = Math.max(...finite);
  const ctx = new AudioContext();
  values.forEach((v, i) => {
    if (!Number.isFinite(v)) return;
    const osc = ctx.createOscillator(), gain = ctx.createGain(), t = ctx.currentTime + i * 0.35;
    osc.type = 'triangle';
    osc.frequency.value = 220 + (hi > lo ? (v - lo) / (hi - lo) : 0.5) * 660;
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(0.25, t + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.3);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t); osc.stop(t + 0.32);
  });
  window.setTimeout(() => ctx.close(), values.length * 350 + 500);
}

function downloadCsv(name: string, dates: string[], values: number[], sigma: number[], unit: string) {
  const rows = [`date,value_${unit.replace(/\W+/g, '')},uncertainty`, ...dates.map((d, i) => `${d},${Number.isFinite(values[i]) ? values[i].toFixed(3) : ''},${Number.isFinite(sigma[i]) ? sigma[i].toFixed(3) : ''}`)];
  const link = document.createElement('a');
  link.href = URL.createObjectURL(new Blob([rows.join('\n')], { type: 'text/csv' }));
  link.download = name;
  link.click();
  URL.revokeObjectURL(link.href);
}

interface Props {
  manifest: LayerManifest;
  data: SeriesData;
  pick: Pick;
  onClose: () => void;
}

export function Inspector({ manifest, data, pick, onClose }: Props) {
  const s = manifest.series!;
  const { values, sigma } = useMemo(() => seriesAt(manifest, data, pick), [manifest, data, pick]);
  const valid = values.filter(Number.isFinite);

  const view = useMemo(() => {
    if (valid.length < 2) return null;
    const t0 = day(s.dates[0]), t1 = day(s.dates[s.dates.length - 1]);
    const lows = values.map((v, i) => v - (Number.isFinite(sigma[i]) ? sigma[i] : 0));
    const highs = values.map((v, i) => v + (Number.isFinite(sigma[i]) ? sigma[i] : 0));
    const extra = s.threshold !== undefined ? [s.threshold] : [];
    let lo = Math.min(...lows.filter(Number.isFinite), ...extra);
    let hi = Math.max(...highs.filter(Number.isFinite), ...extra);
    if (hi - lo < 1e-6) { lo -= 1; hi += 1; }
    const pad = (hi - lo) * 0.08;
    lo -= pad; hi += pad;
    const x = (iso: string) => P.l + ((day(iso) - t0) / Math.max(t1 - t0, 1)) * (W - P.l - P.r);
    const y = (v: number) => P.t + ((hi - v) / (hi - lo)) * (H - P.t - P.b);
    const pts = s.dates.map((d, i) => ({ d, v: values[i], x: x(d), lo: lows[i], hi: highs[i] })).filter((p) => Number.isFinite(p.v));
    const band = [...pts.map((p) => `${p.x},${y(p.hi)}`), ...[...pts].reverse().map((p) => `${p.x},${y(p.lo)}`)].join(' ');
    const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p.x.toFixed(1)} ${y(p.v).toFixed(1)}`).join(' ');
    const event = manifest.event && day(manifest.event) > t0 && day(manifest.event) < t1 ? x(manifest.event) : null;
    return { pts, band, line, y, lo, hi, event, threshold: s.threshold !== undefined ? y(s.threshold) : null };
  }, [values, sigma, s, manifest.event, valid.length]);

  const measured = useMemo(() => {
    if (valid.length < 2) return null;
    const t = s.dates.map((d) => day(d) - day(s.dates[0]));
    return classify(t, values, sigma, s.unit, s.dates.map(short));
  }, [values, sigma, s, valid.length]);

  const meanSigma = sigma.filter(Number.isFinite);
  const typical = meanSigma.length ? meanSigma.reduce((a, b) => a + b, 0) / meanSigma.length : null;

  return (
    <section className="inspector" aria-labelledby="inspector-title">
      <div className="inspector-head">
        <h3 id="inspector-title" className="card-subtitle">This spot, {coord(pick.lat, 'N', 'S')} {coord(pick.lng, 'E', 'W')}</h3>
        <button type="button" className="card-close inspector-close" onClick={onClose} aria-label="Close this spot">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
        </button>
      </div>
      {!view ? (
        <p className="status status-unknown">No reliable measurements here. Radar loses the signal over open sea, in radar shadow, or where the ground changed too much between passes.</p>
      ) : (
        <>
          <svg className="inspector-chart" viewBox={`0 0 ${W} ${H}`} role="img"
            aria-label={`${s.label} at this spot: ${view.pts.map((p) => `${short(p.d)} ${p.v.toFixed(1)} ${s.unit}`).join('; ')}`}>
            <text className="axis" x={P.l - 6} y={view.y(view.hi) + 8} textAnchor="end">{view.hi.toFixed(0)}</text>
            <text className="axis" x={P.l - 6} y={view.y(view.lo)} textAnchor="end">{view.lo.toFixed(0)}</text>
            <text className="axis" x={P.l} y={H - 6}>{short(s.dates[0])}</text>
            <text className="axis" x={W - P.r} y={H - 6} textAnchor="end">{short(s.dates[s.dates.length - 1])}</text>
            {view.threshold !== null && <line className="threshold" x1={P.l} x2={W - P.r} y1={view.threshold} y2={view.threshold} />}
            {view.event !== null && <line className="event-line" x1={view.event} x2={view.event} y1={P.t} y2={H - P.b} />}
            <polygon className="band" points={view.band} />
            <path className="series-line" d={view.line} />
            {view.pts.map((p) => <circle key={p.d} className="series-dot" cx={p.x} cy={view.y(p.v)} r={3} />)}
          </svg>
          <p className="fineprint">
            {s.label}, {s.unit}. The shaded band is the measurement uncertainty{typical !== null ? ` (about ±${typical.toFixed(1)} ${s.unit})` : ''}.
            {s.threshold_label ? ` ${s.threshold_label}.` : ''}
          </p>
          <p className="inspector-actions">
            <button type="button" className="chip" onClick={() => sonify(values)}>Hear it</button>
            <button type="button" className="chip" onClick={() => downloadCsv(`sarabande-${manifest.hotspot}-${pick.lat.toFixed(3)}-${pick.lng.toFixed(3)}.csv`, s.dates, values, sigma, s.unit)}>Download CSV</button>
          </p>
          {measured && (
            <p className="card-dance measured">
              <span className={`marker marker-demo dance-${measured.dance}`} aria-hidden="true"><span className="marker-ring" /><span className="marker-dot" /></span>
              <span><strong>{DANCES[measured.dance].name} here.</strong> {measured.reason}{measured.confidence === 'low' ? ' Low confidence.' : ''}</span>
            </p>
          )}
        </>
      )}
    </section>
  );
}
