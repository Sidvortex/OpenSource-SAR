import { useMemo, useRef } from 'react';
import type { PointerEvent } from 'react';
import { formatDate } from '../catalog';
import type { Frame, LayerDef, LayerManifest, StatDef } from '../types';

const GAP = { start: '2026-07-27', end: '2026-08-10' };   // permanent NISAR instrument gap
const W = 560;
const H = 84;
const PAD = { left: 8, right: 8, top: 10, bottom: 18 };
const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 864e5;

export const frameLabel = (f: Frame) => (/^\d{4}-\d{2}-\d{2}$/.test(f.label) ? formatDate(f.label) : f.label);
export const statText = (s: StatDef, value: number | undefined) =>
  value === undefined ? `${s.label}: none` : `${s.label} ${Math.round(value).toLocaleString('en')} ${s.unit}`.trim();

export function Legend({ layer }: { layer: LayerDef }) {
  if (layer.legend) {
    return (
      <p className="legend">
        {layer.legend.map((item) => (
          <span key={item.label} className="legend-item"><span className="key" style={{ background: item.color }} aria-hidden="true" />{item.label}</span>
        ))}
      </p>
    );
  }
  if (!layer.ramp) return null;
  const r = layer.ramp;
  const range = r.unit === 'cm' || r.unit === 'dB' ? `${r.min} to ${r.max} ${r.unit}` : '';
  return (
    <div className="legend legend-ramp">
      <span className="ramp-end">{r.low}</span>
      <span className="ramp-bar" style={{ background: `linear-gradient(90deg, ${r.colors.join(', ')})` }} aria-hidden="true" />
      <span className="ramp-end">{r.high}</span>
      {range && <span className="ramp-range">{range}</span>}
    </div>
  );
}

interface Props {
  manifest: LayerManifest;
  index: number;
  onIndex: (i: number) => void;
  playing: boolean;
  onPlaying: (p: boolean) => void;
  kind: string;
  onKind: (k: string) => void;
}

export function TimeBar({ manifest, index, onIndex, playing, onPlaying, kind, onKind }: Props) {
  const frames = manifest.frames;
  const current = frames[index];
  const layer = manifest.layers.find((l) => l.id === kind) ?? manifest.layers[0];
  const svgRef = useRef<SVGSVGElement>(null);

  const chart = useMemo(() => {
    const t0 = day(frames[0].start ?? frames[0].date);
    const t1 = day(frames[frames.length - 1].date);
    const area = frames.map((f) => f.stats[manifest.chart.area] ?? 0);
    const line = manifest.chart.line ? frames.map((f) => f.stats[manifest.chart.line!] ?? 0) : null;
    const max = Math.max(...area, ...(line ?? [0]), 1) * 1.1;
    const x = (iso: string) => PAD.left + ((day(iso) - t0) / Math.max(t1 - t0, 1)) * (W - PAD.left - PAD.right);
    const y = (v: number) => H - PAD.bottom - (v / max) * (H - PAD.top - PAD.bottom);
    const path = (values: number[]) => values.map((v, i) => `${i ? 'L' : 'M'}${x(frames[i].date).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
    const base = y(0);
    const inRange = (iso: string | null) => !!iso && day(iso) > t0 && day(iso) < t1;
    return {
      x, base,
      area: `${path(area)} L${x(frames[frames.length - 1].date).toFixed(1)} ${base} L${x(frames[0].date).toFixed(1)} ${base} Z`,
      line: line ? path(line) : null,
      gap: day(GAP.end) > t0 && day(GAP.start) < t1
        ? { x0: Math.max(x(GAP.start), PAD.left), x1: Math.min(x(GAP.end), W - PAD.right) } : null,
      event: inRange(manifest.event) ? x(manifest.event!) : null,
    };
  }, [frames, manifest]);

  const scrub = (event: PointerEvent<SVGSVGElement>) => {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const px = ((event.clientX - rect.left) / rect.width) * W;
    let best = 0;
    frames.forEach((f, i) => { if (Math.abs(chart.x(f.date) - px) < Math.abs(chart.x(frames[best].date) - px)) best = i; });
    onPlaying(false);
    onIndex(best);
  };

  return (
    <section className="timebar" aria-label={manifest.title}>
      {manifest.synthetic && (
        <p className="synthetic">Synthetic demo data, not NISAR measurements. Run the pipeline to replace it with real {manifest.frame_noun}.</p>
      )}
      <div className="timebar-row">
        {frames.length > 1 && (
          <button type="button" className="play" onClick={() => onPlaying(!playing)} aria-label={playing ? 'Pause' : `Play through the ${manifest.frame_noun}`}>
            {playing
              ? <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2" width="3.5" height="12" /><rect x="9.5" y="2" width="3.5" height="12" /></svg>
              : <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2l10 6-10 6z" /></svg>}
          </button>
        )}
        <div className="now">
          <p className="now-date">{frameLabel(current)}</p>
          <p className="now-stats">
            {manifest.stats.map((s) => (
              <span key={s.id} className="stat">
                {s.color && <span className="key" style={{ background: s.color }} aria-hidden="true" />}
                {statText(s, current.stats[s.id])}
              </span>
            ))}
          </p>
        </div>
        <div className="segmented" role="group" aria-label="Layer">
          {manifest.layers.map((l) => (
            <button key={l.id} type="button" aria-pressed={kind === l.id} onClick={() => onKind(l.id)}>{l.label}</button>
          ))}
        </div>
      </div>

      <svg ref={svgRef} className="chart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true"
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); scrub(e); }}
        onPointerMove={(e) => { if (e.buttons) scrub(e); }}>
        {chart.gap && (
          <g className="chart-gap">
            <rect x={chart.gap.x0} y={PAD.top} width={chart.gap.x1 - chart.gap.x0} height={chart.base - PAD.top} />
            <text x={(chart.gap.x0 + chart.gap.x1) / 2} y={H - 5} textAnchor="middle">no data</text>
          </g>
        )}
        {chart.event !== null && (
          <g className="chart-event">
            <line x1={chart.event} x2={chart.event} y1={PAD.top - 6} y2={chart.base} />
            <text x={chart.event + 4} y={PAD.top + 4}>event</text>
          </g>
        )}
        <path className="chart-total" d={chart.area} />
        {chart.line && <path className="chart-open" d={chart.line} />}
        {frames.map((f, i) => (
          <circle key={f.date + (f.start ?? '')} className={i === index ? 'chart-dot is-current' : 'chart-dot'} cx={chart.x(f.date)} cy={chart.base} r={i === index ? 4 : 2.5} />
        ))}
        <line className="chart-now" x1={chart.x(current.date)} x2={chart.x(current.date)} y1={PAD.top - 4} y2={chart.base} />
      </svg>

      {frames.length > 1 && (
        <label className="scrubber">
          <span className="visually-hidden">Choose a {manifest.frame_noun === 'pairs' ? 'pair' : 'pass'}</span>
          <input type="range" min={0} max={frames.length - 1} step={1} value={index} aria-valuetext={frameLabel(current)}
            onChange={(e) => { onPlaying(false); onIndex(Number(e.target.value)); }} />
        </label>
      )}
      <Legend layer={layer} />
      {layer.note && <p className="timebar-foot">{layer.note}</p>}
      <p className="timebar-foot">
        {frames.length} {manifest.frame_noun}, {frameLabel(frames[0])} to {frameLabel(frames[frames.length - 1])}. Chart: {manifest.chart.label}.
        {chart.gap ? " The grey band is NISAR's instrument gap." : ''}
      </p>
    </section>
  );
}
