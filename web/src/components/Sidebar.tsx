import type { CSSProperties } from 'react';
import { DANCE_ORDER, DANCES, MODULE_ORDER, MODULES } from '../catalog';
import type { DanceId, Hotspot, ModuleId } from '../types';

interface Props {
  query: string;
  onQuery: (q: string) => void;
  modules: Set<ModuleId>;
  onToggleModule: (m: ModuleId) => void;
  dance: DanceId | null;
  onDance: (d: DanceId | null) => void;
  places: Hotspot[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  open: boolean;
  onToggleOpen: () => void;
}

const REPO_URL: string = import.meta.env.VITE_REPO_URL ?? 'https://github.com/';

export function Sidebar(props: Props) {
  const { query, onQuery, modules, onToggleModule, dance, onDance, places, selectedId, onSelect, open, onToggleOpen } = props;
  return (
    <aside className={`panel${open ? ' is-open' : ''}`} aria-label="Places and filters">
      <header className="panel-head">
        <h1 className="wordmark">SARabande</h1>
        <p className="tagline">Watch Earth's surface dance, measured by NISAR radar every 12 days.</p>
        <button type="button" className="sheet-toggle" aria-expanded={open} onClick={onToggleOpen}>
          {open ? 'Hide places' : `Show ${places.length} places`}
        </button>
      </header>

      <div className="panel-body">
        <label className="search">
          <span className="visually-hidden">Find a place</span>
          <input type="search" placeholder="Find a place" value={query} onChange={(e) => onQuery(e.target.value)} />
        </label>

        <fieldset className="group">
          <legend>What is changing</legend>
          <div className="chips">
            {MODULE_ORDER.map((m) => (
              <button key={m} type="button" className="chip" aria-pressed={modules.has(m)} onClick={() => onToggleModule(m)}
                style={{ '--c': MODULES[m].color } as CSSProperties}>
                <span className="swatch" aria-hidden="true" />
                {MODULES[m].name}
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset className="group">
          <legend>Every place has a dance</legend>
          <ul className="dances">
            {DANCE_ORDER.map((d) => (
              <li key={d}>
                <button type="button" className="dance-row" aria-pressed={dance === d} onClick={() => onDance(dance === d ? null : d)}>
                  <span className={`marker marker-demo dance-${d}`} aria-hidden="true">
                    <span className="marker-ring" /><span className="marker-dot" />
                  </span>
                  <span className="dance-name">{DANCES[d].name}</span>
                  <span className="dance-pattern">{DANCES[d].pattern}</span>
                </button>
              </li>
            ))}
          </ul>
        </fieldset>

        <section className="group" aria-labelledby="places-heading">
          <h2 id="places-heading" className="group-title">
            {places.length === 1 ? '1 place' : `${places.length} places`}
          </h2>
          {places.length === 0 ? (
            <p className="empty">No place matches these filters. Clear the search or switch a module back on.</p>
          ) : (
            <ul className="places">
              {places.map((p) => (
                <li key={p.id}>
                  <button type="button" className="place-row" aria-current={p.id === selectedId} onClick={() => onSelect(p.id)}>
                    <span className="swatch" style={{ '--c': MODULES[p.module].color } as CSSProperties} aria-hidden="true" />
                    <span className="place-name">{p.name}</span>
                    <span className="place-country">{p.country}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <footer className="panel-foot">
          <p>Free and open source under the MIT licence. No paid services, no API keys.</p>
          <p>NISAR data from NASA/JPL and ISRO via ASF DAAC. <a href={REPO_URL}>Source code</a></p>
        </footer>
      </div>
    </aside>
  );
}
