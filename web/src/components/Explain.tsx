import { useState } from 'react';
import { explain } from '../explain';
import type { ExplainData, Level } from '../explain';
import type { Hotspot, LayerManifest } from '../types';

export function Explain({ data, manifest, spot }: { data: ExplainData; manifest: LayerManifest; spot: Hotspot }) {
  const [lang, setLang] = useState('en');
  const [level, setLevel] = useState<Level>('citizen');
  const out = explain(data, manifest, spot, lang, level);
  return (
    <section className="card-section explain" aria-labelledby="explain-title" lang={lang}>
      <div className="explain-controls">
        <h3 id="explain-title" className="card-subtitle">In plain words</h3>
        <select aria-label="Language" value={lang} onChange={(e) => setLang(e.target.value)}>
          {Object.entries(data.languages).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
        </select>
      </div>
      <div className="segmented" role="group" aria-label="Reading level">
        {(['kid', 'citizen', 'expert'] as Level[]).map((l) => (
          <button key={l} type="button" aria-pressed={level === l} onClick={() => setLevel(l)}>{data.levels[lang][l]}</button>
        ))}
      </div>
      <p className="explain-text">{out.text} {out.dance}</p>
      <p className="fineprint"><strong>{out.caveatTitle}:</strong> {out.caveat}</p>
    </section>
  );
}
