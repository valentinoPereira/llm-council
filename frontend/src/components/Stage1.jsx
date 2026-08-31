import Markdown from './Markdown';
import { displayModelName, formatDuration } from '../utils';
import './Stage1.css';

/**
 * Stage 1 renders every member's independent response side by side.
 *
 * Comparison is the product — models are shown as an aligned grid (2-up on
 * wide screens) rather than hidden behind tabs, so the reader can weigh each
 * answer against its peers without clicking. Raw output stays fully
 * inspectable; only the display name is prettified (tooltip holds the raw id).
 */
export default function Stage1({ responses }) {
  if (!responses || responses.length === 0) {
    return null;
  }

  return (
    <div className="stage stage1">
      <div className="stage-header">
        <span className="stage-numeral">I</span>
        <div className="stage-heading">
          <h3 className="stage-title">Deliberation</h3>
          <span className="stage-subtitle">
            Individual responses from each council member
          </span>
        </div>
      </div>

      <div className="stage1-grid">
        {responses.map((resp, index) => (
          <article key={index} className="response-card">
            <header className="response-card-header">
              <span className="response-card-name" title={resp.model}>
                {displayModelName(resp.model)}
              </span>
              <span className="duration-detail">
                {formatDuration(resp.duration_ms)}
              </span>
            </header>
            <div className="response-text markdown-content">
              <Markdown>{resp.response}</Markdown>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
