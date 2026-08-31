import Markdown from './Markdown';
import { displayModelName, formatDuration } from '../utils';
import './Stage3.css';

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  // The chairman stage completed but reported a fatal error. Stages 1 and 2
  // are still available for inspection via the tabs.
  if (finalResponse.error) {
    return (
      <div
        id="council-verdict"
        className="stage stage3"
        tabIndex={-1}
        aria-label="Council verdict"
      >
        <div className="stage-header">
          <span className="stage-numeral">III</span>
          <div className="stage-heading">
            <h3 className="stage-title">Synthesis</h3>
            <span className="stage-subtitle">The Chair could not deliver a verdict</span>
          </div>
        </div>
        <div className="final-response">
          <div className="chairman-label">Chairman unavailable</div>
          <div className="final-text markdown-content stage3-error">
            <p>{finalResponse.error}</p>
            <p>
              The Council's deliberations (Stages I and II) are preserved
              above for review. You may summon a new council to try again.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      id="council-verdict"
      className="stage stage3"
      tabIndex={-1}
      aria-label="Council verdict"
    >
      <div className="stage-header">
        <span className="stage-numeral">III</span>
        <div className="stage-heading">
          <h3 className="stage-title">Synthesis</h3>
          <span className="stage-subtitle">The Council's verdict</span>
        </div>
      </div>
      <div className="final-response">
        <div className="chairman-label">
          {finalResponse.fallback ? 'A Vice-Chairman stepped in' : 'Delivered by the Chairman'}
          {' · '}
          {finalResponse.model && (
            <span title={finalResponse.model}>
              {displayModelName(finalResponse.model)}
            </span>
          )}
          {finalResponse.duration_ms != null && (
            <span className="duration-detail">
              {formatDuration(finalResponse.duration_ms)}
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
