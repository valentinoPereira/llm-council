import './CouncilProgress.css';

const STEPS = [
  { key: 'stage1', numeral: 'I', label: 'Deliberation', hint: 'Each member responds independently' },
  { key: 'stage2', numeral: 'II', label: 'Peer Review', hint: 'Anonymized ranking of every response' },
  { key: 'stage3', numeral: 'III', label: 'Synthesis', hint: 'The Chairman delivers the verdict' },
];

function formatElapsed(seconds) {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${mins}m ${rest.toString().padStart(2, '0')}s`;
}

function getLiveHint(stepKey, elapsed) {
  if (stepKey === 'stage3') {
    if (elapsed >= 230) return 'Failover imminent…';
    if (elapsed >= 120) return 'Still deliberating…';
    if (elapsed >= 60) return 'The Chairman is weighing every response…';
  }
  return null;
}

/**
 * Ceremonial progress indicator shown while a council run is in flight.
 * Replaces per-stage spinners: waiting time is brand experience.
 *
 * A step is `done` once its data has arrived, `active` while the backend
 * reports it running, and `pending` otherwise.
 */
export default function CouncilProgress({ message }) {
  const loading = message?.loading ?? {};
  const inFlight = STEPS.some((s) => loading[s.key]);

  if (!inFlight) return null;

  return (
    <div className="council-progress" role="status" aria-live="polite">
      <div className="council-progress-kicker">The Council is in session</div>
      <ol className="council-progress-steps">
        {STEPS.map((step, i) => {
          const done = Boolean(message[step.key]);
          const raw = loading[step.key];
          const active = Boolean(raw);
          const elapsed = raw?.elapsed_s ?? 0;
          const status = done ? 'done' : active ? 'active' : 'pending';
          const liveHint = active ? getLiveHint(step.key, elapsed) : null;
          return (
            <li key={step.key} className={`progress-step ${status}`}>
              <span className="step-marker" aria-hidden="true">
                {done ? (
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
                       strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                ) : (
                  step.numeral
                )}
              </span>
              <span className="step-text">
                <span className="step-label">{step.label}</span>
                <span className="step-hint">
                  {liveHint ?? step.hint}
                  {active && elapsed > 0 && (
                    <span className="step-elapsed"> — {formatElapsed(elapsed)}</span>
                  )}
                </span>
              </span>
              {i < STEPS.length - 1 && (
                <span className={`step-connector ${done ? 'done' : ''}`} aria-hidden="true" />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
