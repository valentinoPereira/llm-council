import Markdown from './Markdown';
import { formatDuration } from '../utils';
import './Stage3.css';

export default function Stage3({ finalResponse }) {
  if (!finalResponse) {
    return null;
  }

  return (
    <div className="stage stage3">
      <div className="stage-header">
        <span className="stage-numeral">III</span>
        <div className="stage-heading">
          <h3 className="stage-title">Synthesis</h3>
          <span className="stage-subtitle">The Council's verdict</span>
        </div>
      </div>
      <div className="final-response">
        <div className="chairman-label">
          Delivered by the Chairman ·{' '}
          {finalResponse.model.split('/')[1] || finalResponse.model}
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
