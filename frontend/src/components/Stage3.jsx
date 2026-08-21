import Markdown from './Markdown';
import './Stage3.css';

function formatDuration(durationMs) {
  if (durationMs == null) return null;
  const secs = durationMs / 1000;
  return secs >= 1 ? `${secs.toFixed(1)}s` : `${Math.round(durationMs)}ms`;
}

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  return (
    <div className="stage stage3">
      <h3 className="stage-title">Stage 3: Final Council Answer</h3>
      <div className="final-response">
        <div className="chairman-label">
          Chairman: {finalResponse.model.split('/')[1] || finalResponse.model}
          {finalResponse.duration_ms != null && (
            <span className="duration-detail">
              ⏱ {formatDuration(finalResponse.duration_ms)}
            </span>
          )}
        </div>
        <div className="final-text markdown-content">
          <Markdown>{finalResponse.response}</Markdown>
        </div>
      </div>
    </div>
  );
}
