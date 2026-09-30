import type { CSSProperties, ReactNode } from 'react';
import { DANCES, MODULES, formatDate, vertexUrl } from '../catalog';
import type { Coverage, Hotspot, LayerManifest } from '../types';

interface Props {
  spot: Hotspot;
  coverage: Coverage | null;
  manifest: LayerManifest | null;
  canInspect?: boolean;
  inspector?: ReactNode;
  onOpen3D: () => void;
  onClose: () => void;
}

function CoverageStatus({ spot, coverage }: { spot: Hotspot; coverage: Coverage | null }) {
  const entry = coverage?.hotspots[spot.id];
  if (!coverage || !entry) {
    return (
      <p className="status status-unknown">
        Not checked yet. Run <code>python pipeline/update_coverage.py</code>, or wait for the weekly check.
      </p>
    );
  }
  if (entry.verdict === null) {
    return <p className="status status-error">The last check could not reach ASF: {entry.errors[0]}</p>;
  }
  const good = entry.verdict === 'pass';
  return (
    <>
      <p className={`status ${good ? 'status-pass' : 'status-fail'}`}>
        {good ? 'Enough NISAR data to build on' : 'Not enough NISAR data yet'}: {entry.score} {entry.rule}, {entry.need} needed.
      </p>
      <ul className="products">
        {Object.entries(entry.products).map(([name, p]) => (
          <li key={name}>
            <strong>{name}</strong>{' '}
            {p.items === 0
              ? 'none found'
              : `${p.items} over ${p.stacks === 1 ? '1 track' : `${p.stacks} tracks`}, ${formatDate(p.first)} to ${formatDate(p.last)}, about ${p.size_gb} GB`}
          </li>
        ))}
      </ul>
      <p className="checked">Checked {formatDate(coverage.checked)}, {coverage.maturity ?? 'PROVISIONAL'} products.</p>
    </>
  );
}

export function PlaceCard({ spot, coverage, manifest, canInspect, inspector, onOpen3D, onClose }: Props) {
  const module = MODULES[spot.module];
  return (
    <article className="card" aria-labelledby="card-title" style={{ '--c': module.color } as CSSProperties}>
      <button type="button" className="card-close" onClick={onClose} aria-label="Close place">
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
      </button>
      <p className="card-module"><span className="swatch" aria-hidden="true" />{module.name}</p>
      <h2 id="card-title" className="card-title">{spot.name}</h2>
      <p className="card-country">{spot.country}</p>

      <p className="card-why">{spot.why}</p>
      {manifest && (
        <button type="button" className="cta" onClick={onOpen3D}>See before and after in 3D</button>
      )}
      {inspector ?? (canInspect && <p className="hint">Click anywhere on the layer to see that spot's history and its own dance.</p>)}
      {spot.sensitive && <p className="card-note">{spot.sensitive}</p>}
      {spot.caution && <p className="card-note">{spot.caution}</p>}

      <section className="card-section" aria-label="Dance style">
        {spot.dances.map((d) => (
          <p key={d} className="card-dance">
            <span className={`marker marker-demo dance-${d}`} aria-hidden="true"><span className="marker-ring" /><span className="marker-dot" /></span>
            <span><strong>{DANCES[d].name}.</strong> {DANCES[d].pattern}.</span>
          </p>
        ))}
        {manifest?.dance ? (
          <p className="card-dance measured">
            <span className={`marker marker-demo dance-${manifest.dance.dance}`} aria-hidden="true"><span className="marker-ring" /><span className="marker-dot" /></span>
            <span><strong>Measured: {DANCES[manifest.dance.dance].name}.</strong> {manifest.dance.reason}{manifest.dance.basis ? ` Based on ${manifest.dance.basis}.` : ''}</span>
          </p>
        ) : (
          <p className="fineprint">This is the expected pattern until radar layers arrive for this place.</p>
        )}
      </section>

      <section className="card-section" aria-labelledby="coverage-title">
        <h3 id="coverage-title" className="card-subtitle">NISAR coverage</h3>
        <CoverageStatus spot={spot} coverage={coverage} />
        <p className="card-links">
          <a href={vertexUrl(spot.bbox)} target="_blank" rel="noreferrer">Browse this area in ASF Vertex</a>
        </p>
      </section>

      {manifest ? (
        <details className="card-section method">
          <summary>How this layer is made</summary>
          <ul>{manifest.method.map((line) => <li key={line}>{line}</li>)}</ul>
          <p className="fineprint">{manifest.product}. Built {formatDate(manifest.created)}.</p>
        </details>
      ) : (
        <p className="fineprint">Radar layers for this place arrive in Part {spot.layerPart} of the build, from {module.product}.</p>
      )}
    </article>
  );
}
