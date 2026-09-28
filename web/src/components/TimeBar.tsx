import { useMemo, useRef } from 'react';
import type { PointerEvent } from 'react';
import { formatDate } from '../catalog';
import type { LayerKind, LayerManifest } from '../types';

const GAP = { start: '2026-07-27', end: '2026-08-10' };   // permanent NISAR instrument gap
const W = 560;
const H = 84;
const PAD = { left: 8, right: 8, top: 10, bottom: 18 };

interface Props {
  manifest: LayerManifest;
  index: number;
  onIndex: (i: number) => void;
  playing: boolean;
  onPlaying: (p: boolean) => void;
  kind: LayerKind;
  onKind: (k: LayerKind) => void;
}

const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / 864e5;
const km2 = (n: number) => `${Math.round(n).toLocaleString('en')} km²`;

export function TimeBar({ manifest, index, onIndex, playing, onPlaying, kind, onKind }: Props) {
  const dates = manifest.dates;
  const current = dates[index];
  const svgRef = useRef<SVGSVGElement>(null);

  const chart = useMemo(() => {
    const t0 = day(dates[0].date);
    const t1 = day(dates[dates.length - 1].date);
    const totals = dates.map((d) => d.open_water_km2 + d.flooded_veg_km2);
    const max = Math.max(...totals) * 1.1;
    const x = (iso: string) => PAD.left + ((day(iso) - t0) / Math.max(t1 - t0, 1)) * (W - PAD.left - PAD.right);
    const y = (v: number) => H - PAD.bottom - (v / max) * (H - PAD.top - PAD.bottom);
    const line = (values: number[]) => values.map((v, i) => `${i ? 'L' : 'M'}${x(dates[i].date).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
    const base = y(0);
    const area = (values: number[]) => `${line(values)} L${x(dates[dates.length - 1].date).toFixed(1)} ${base} L${x(dates[0].date).toFixed(1)} ${base} Z`;
    const gapIn = day(GAP.end) > t0 && day(GAP.start) < t1;
    return {
      x, base,
      totalArea: area(totals),
      openLine: line(dates.map((d) => d.open_water_km2)),
      gap: gapIn ? { x0: Math.max(x(GAP.start), PAD.left), x1: Math.min(x(GAP.end), W - PAD.right) } : null,
    };
  }, [dates]);

  // Click or drag on the chart to jump to the nearest pass.
  const scrub = (event: PointerEvent<SVGSVGElement>) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * W;
    let best = 0;
    dates.forEach((d, i) => {
      if (Math.abs(chart.x(d.date) - px) < Math.abs(chart.x(dates[best].date) - px)) best = i;
    });
    onPlaying(false);
    onIndex(best);
  };

  return (
    <section className="timebar" aria-label="Water dance over time">
      {manifest.synthetic && (
        <p className="synthetic">Synthetic demo data, not NISAR measurements. Run the pipeline to replace it with real passes.</p>
      )}
      <div className="timebar-row">
        <button type="button" className="play" onClick={() => onPlaying(!playing)} aria-label={playing ? 'Pause' : 'Play through the passes'}>
          {playing
            ? <svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2" width="3.5" height="12" /><rect x="9.5" y="2" width="3.5" height="12" /></svg>
            : <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2l10 6-10 6z" /></svg>}
        </button>
        <div className="now">
          <p className="now-date">{formatDate(current.date)}</p>
          <p className="now-stats">
            <span className="key" style={{ background: manifest.legend[0]?.color }} aria-hidden="true" />Open water {km2(current.open_water_km2)}
            <span className="key" style={{ background: manifest.legend[1]?.color }} aria-hidden="true" />Flooded vegetation {km2(current.flooded_veg_km2)}
          </p>
        </div>
        <div className="segmented" role="group" aria-label="Layer">
          <button type="button" aria-pressed={kind === 'water'} onClick={() => onKind('water')}>Water map</button>
          <button type="button" aria-pressed={kind === 'radar'} onClick={() => onKind('radar')}>Radar image</button>
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
        <path className="chart-total" d={chart.totalArea} />
        <path className="chart-open" d={chart.openLine} />
        {dates.map((d, i) => (
          <circle key={d.date} className={i === index ? 'chart-dot is-current' : 'chart-dot'} cx={chart.x(d.date)} cy={chart.base} r={i === index ? 4 : 2.5} />
        ))}
        <line className="chart-now" x1={chart.x(current.date)} x2={chart.x(current.date)} y1={PAD.top - 4} y2={chart.base} />
      </svg>

      <label className="scrubber">
        <span className="visually-hidden">Pass date</span>
        <input type="range" min={0} max={dates.length - 1} step={1} value={index}
          aria-valuetext={formatDate(current.date)}
          onChange={(e) => { onPlaying(false); onIndex(Number(e.target.value)); }} />
      </label>
      <p className="timebar-foot">
        {dates.length} passes, {formatDate(dates[0].date)} to {formatDate(dates[dates.length - 1].date)}. The grey band is NISAR's instrument gap.
      </p>
    </section>
  );
}
