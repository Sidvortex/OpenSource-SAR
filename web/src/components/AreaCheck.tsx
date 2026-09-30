import { useEffect, useState } from 'react';
import { bboxToWkt, formatDate, vertexUrl } from '../catalog';

// NASA's free Common Metadata Repository answers from the browser, no key needed.
// Collection names come from ASF's NISAR guide; change them here if NASA renames them.
const COLLECTIONS: Record<string, string> = {
  GCOV: 'NISAR_L2_GCOV_PROVISIONAL_V1',
  GUNW: 'NISAR_L2_GUNW_PROVISIONAL_V1',
};
type Box = [number, number, number, number];

async function granuleDates(shortName: string, box: Box): Promise<string[]> {
  const url = `https://cmr.earthdata.nasa.gov/search/granules.json?short_name=${shortName}` +
    `&bounding_box=${box.map((v) => v.toFixed(4)).join(',')}&temporal=2026-06-17T00:00:00Z,&page_size=500&sort_key=start_date`;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`CMR answered ${response.status}`);
  const json = await response.json();
  return (json.feed?.entry ?? []).map((e: { time_start: string }) => e.time_start.slice(0, 10));
}

export function AreaCheck({ box, onClose }: { box: Box | null; onClose: () => void }) {
  const [result, setResult] = useState<Record<string, string[]> | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setResult(null); setError(null);
    if (!box) return;
    Promise.all(Object.entries(COLLECTIONS).map(async ([p, c]) => [p, await granuleDates(c, box)] as const))
      .then((pairs) => setResult(Object.fromEntries(pairs)))
      .catch((e: Error) => setError(e.message));
  }, [box]);
  const wkt = box ? bboxToWkt(box) : '';
  return (
    <section className="areacheck" aria-live="polite" aria-labelledby="area-title">
      <div className="inspector-head">
        <h2 id="area-title" className="card-subtitle">Check any area</h2>
        <button type="button" className="card-close inspector-close" onClick={onClose} aria-label="Stop checking areas">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" /></svg>
        </button>
      </div>
      {!box && <p className="hint">Click two opposite corners on the map to draw a box.</p>}
      {box && !result && !error && <p className="hint">Asking NASA's catalogue which NISAR passes cover this box…</p>}
      {error && <p className="status status-error">Couldn't reach NASA's catalogue ({error}). Use the links below instead.</p>}
      {result && Object.entries(result).map(([product, dates]) => {
        const unique = [...new Set(dates)];
        return (
          <p key={product} className="area-row">
            <strong>{product}</strong> {unique.length === 0 ? 'no passes yet' : `${dates.length} products on ${unique.length} dates, ${formatDate(unique[0])} to ${formatDate(unique[unique.length - 1])}`}
          </p>
        );
      })}
      {box && (
        <>
          <p className="card-links"><a href={vertexUrl(box)} target="_blank" rel="noreferrer">Open this box in ASF Vertex</a></p>
          <p className="fineprint">To analyse it yourself: <code>python pipeline/coverage_check.py --name my-area --wkt "{wkt}"</code></p>
        </>
      )}
    </section>
  );
}
