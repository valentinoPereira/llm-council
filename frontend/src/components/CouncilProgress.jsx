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
 * Ceremonial progress indicator for a council run. Replaces per-stage
 * spinners: waiting time is brand experience.
 *
 * A step is `done` once its data has arrived, `active` while the backend
 * reports it running, and `pending` otherwise.
 *
 * The box is never un-mounted once rendered: it stays open while the run is
 * in flight and, on completion, simply swaps its kicker line to "The Council
 * has reached a verdict". Deliberately keeping it on screen means the strip
 * never collapses, so nothing below it reflows when a run finishes.
 */
export default function CouncilProgress({ message }) {
  let loading = message?.loading ?? {};
  let inFlight = STEPS.some((s) => loading[s.key]);

  // Reattach/refetch loading inference. A refetch of the persisted
  // conversation (or a page reload) replaces the cached message with the raw
  // DB shape, which has stages but NO client-side `loading` flags. Wiping
  // them would make this progress view pop in and out on every refetch
  // (the backend's stage_progress heartbeat re-adds them ~every 10s). So when
  // `loading` is missing entirely, derive the in-flight stage from the
  // persisted stages: stages fill forward, so the first null stage is the one
  // still running. Only do this for a genuinely in-flight message — an
  // errored message (which may also have null early stages) must never show
  // as “in session”.
  if (message && message.status === 'pending' && message.loading == null) {
    const inferred = {};
    if (message.stage1 == null) inferred.stage1 = true;
    else if (message.stage2 == null) inferred.stage2 = true;
    else if (message.stage3 == null) inferred.stage3 = true;
    loading = inferred;
    inFlight = STEPS.some((s) => inferred[s.key]);
  }

  // On completion the strip stays rendered and just swaps its label: a
  // successful run announces the verdict; a chairman-failure run (graceful
  // error payload on stage 3) or an errored run says so instead — it must
  // never claim a verdict was reached (Stage 3 renders the error detail
  // below). Keeping it mounted means the strip never collapses, so nothing
  // below it reflows when the run finishes either way.
  const stage3Error = Boolean(message?.stage3 && message.stage3.error);
  const verdict = !inFlight && message?.status === 'complete' && !stage3Error;
  const failed = !inFlight && !verdict && (message?.status === 'error' || stage3Error);
  if (!inFlight && !verdict && !failed) return null;

  const kicker = verdict
    ? 'The Council has reached a verdict'
    : failed
      ? 'The Council could not reach a verdict'
      : 'The Council is in session';

  return (
    <div className="council-progress" role="status" aria-live="polite">
      <div className="council-progress-kicker">{kicker}</div>
      <ol className="council-progress-steps">
        {STEPS.map((step, i) => {
          // A stage payload carrying an error (stage 3's graceful failure)
          // was not completed successfully — no checkmark. Stage-1/2 arrays
          // have no `error` field, so the guard is inert for them.
          const done = Boolean(message[step.key]) && !message[step.key]?.error;
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
                  {/* Elapsed slot always rendered so its (varying) width can
                      never reflow the step strip; hidden until it's live. */}
                  <span
                    className={`step-elapsed${active && elapsed > 0 ? ' is-live' : ''}`}
                    aria-hidden={!(active && elapsed > 0)}
                  >
                    {' — '}
                    {active && elapsed > 0 ? formatElapsed(elapsed) : '0s'}
                  </span>
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
