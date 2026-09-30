import { useEffect, useRef, useState } from 'react';

const BANDS = [
  { id: 'X', cm: 3, depth: 0.12, note: 'Stops at the top leaves.' },
  { id: 'C', cm: 5.6, depth: 0.25, note: 'Gets into the upper canopy.' },
  { id: 'S', cm: 10, depth: 0.45, note: 'Reaches branches: good for crops. NISAR carries one.' },
  { id: 'L', cm: 24, depth: 0.9, note: 'Reaches trunks and ground: NISAR\'s main radar.' },
];
const QUIZ = [
  { q: 'Why can NISAR see through clouds and at night?', options: ['It makes its own microwave "light"', 'It uses infrared cameras', 'It waits for clear days'], answer: 0 },
  { q: 'One rainbow fringe in an interferogram means the ground moved about…', options: ['1 cm', '12 cm', '1 metre'], answer: 1 },
  { q: 'Why does flooded forest look bright to radar?', options: ['Water glows', 'The pulse bounces off water and trunks straight back', 'Leaves are shiny'], answer: 1 },
];

export function RadarExplainer({ onClose }: { onClose: () => void }) {
  const [band, setBand] = useState(3);
  const [move, setMove] = useState(30);
  const [answers, setAnswers] = useState<(number | null)[]>(QUIZ.map(() => null));
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const b = BANDS[band];
  const fringes = move / 12;
  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby="radar-title">
      <div className="modal-body">
        <div className="modal-head">
          <h2 id="radar-title" className="showcase-title">How radar sees</h2>
          <button ref={close} type="button" className="showcase-close" onClick={onClose}>Close</button>
        </div>

        <section className="lesson">
          <h3>1. It brings its own light</h3>
          <p>NISAR sends microwave pulses down and times the echoes. Clouds, smoke and darkness don't block microwaves, so it sees every 12 days, rain or shine.</p>
        </section>

        <section className="lesson">
          <h3>2. Longer waves reach deeper</h3>
          <label className="lesson-control">Radar band: <strong>{b.id}-band, {b.cm} cm waves</strong>
            <input type="range" min={0} max={3} step={1} value={band} onChange={(e) => setBand(Number(e.target.value))} aria-valuetext={`${b.id}-band`} />
          </label>
          <svg viewBox="0 0 300 120" className="lesson-art" role="img" aria-label={`${b.id}-band reaches ${Math.round(b.depth * 100)}% of the way down a tree`}>
            <rect x="0" y="108" width="300" height="12" fill="#b9a27f" />
            <rect x="142" y="50" width="16" height="58" fill="#7a5a3a" />
            <ellipse cx="150" cy="45" rx="70" ry="38" fill="#5f9a4e" />
            <line x1="60" y1="0" x2="60" y2={8 + b.depth * 100} stroke="#1f8fd1" strokeWidth="6" strokeLinecap="round" />
            <text x="72" y="16" fontSize="11" fill="#1a2233">{b.note}</text>
          </svg>
        </section>

        <section className="lesson">
          <h3>3. Fringes count centimetres</h3>
          <label className="lesson-control">Ground moves: <strong>{move} cm</strong>
            <input type="range" min={0} max={60} step={1} value={move} onChange={(e) => setMove(Number(e.target.value))} />
          </label>
          <div className="fringe-bar" style={{ background: `repeating-linear-gradient(90deg, red, yellow, lime, cyan, blue, magenta, red ${100 / Math.max(fringes, 0.01)}%)` }} aria-hidden="true" />
          <p>That is <strong>{fringes.toFixed(1)} fringes</strong>: each full colour cycle is about 12 cm (half of NISAR's 24 cm wavelength).</p>
        </section>

        <section className="lesson">
          <h3>4. Water is dark, flooded forest is bright</h3>
          <p>Calm water reflects the pulse away like a mirror, so it looks dark. In flooded forest the pulse bounces off the water, then a trunk, and straight back: a bright "double bounce".</p>
        </section>

        <section className="lesson">
          <h3>Quick quiz</h3>
          {QUIZ.map((item, qi) => (
            <fieldset key={item.q} className="quiz">
              <legend>{item.q}</legend>
              {item.options.map((o, oi) => (
                <button key={o} type="button" aria-pressed={answers[qi] === oi}
                  className={answers[qi] === oi ? (oi === item.answer ? 'right' : 'wrong') : ''}
                  onClick={() => setAnswers((a) => a.map((v, i) => (i === qi ? oi : v)))}>{o}</button>
              ))}
              {answers[qi] !== null && <p className="fineprint">{answers[qi] === item.answer ? 'Right.' : 'Not quite: try another answer.'}</p>}
            </fieldset>
          ))}
        </section>
      </div>
    </div>
  );
}
