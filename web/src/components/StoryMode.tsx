export interface StoryStep { place: string; layer: string; frame: 'first' | 'last' | 'event' | number; text: string }
export interface Story { id: string; title: string; steps: StoryStep[] }

interface Props { story: Story; step: number; onStep: (i: number) => void; onExit: () => void }

export function StoryMode({ story, step, onStep, onExit }: Props) {
  const s = story.steps[step];
  const last = step === story.steps.length - 1;
  return (
    <section className="story" aria-live="polite" aria-labelledby="story-title">
      <p className="story-kicker">Story {step + 1} of {story.steps.length}</p>
      <h2 id="story-title" className="story-title">{story.title}</h2>
      <p className="story-text">{s.text}</p>
      <div className="story-controls">
        <button type="button" onClick={() => onStep(step - 1)} disabled={step === 0}>Back</button>
        <span className="story-dots" aria-hidden="true">{story.steps.map((_, i) => <span key={i} className={i === step ? 'on' : ''} />)}</span>
        {last ? <button type="button" className="primary-light" onClick={onExit}>Explore it yourself</button>
              : <button type="button" className="primary-light" onClick={() => onStep(step + 1)}>Next</button>}
      </div>
      <button type="button" className="story-exit" onClick={onExit}>Exit story</button>
    </section>
  );
}
