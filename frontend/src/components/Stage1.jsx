import { useState } from 'react';
import Markdown from './Markdown';
import './Stage1.css';

function formatDuration(durationMs) {
  if (durationMs == null) return null;
  const secs = durationMs / 1000;
  return secs >= 1 ? `${secs.toFixed(1)}s` : `${Math.round(durationMs)}ms`;
}

export default function Stage1({ responses }) {
  const [activeTab, setActiveTab] = useState(0);

  if (!responses || responses.length === 0) {
    return null;
  }

  return (
    <div className="stage stage1">
      <h3 className="stage-title">Stage 1: Individual Responses</h3>

      <div className="tabs">
        {responses.map((resp, index) => (
          <button
            key={index}
            className={`tab ${activeTab === index ? 'active' : ''}`}
            onClick={() => setActiveTab(index)}
          >
            {resp.model.split('/')[1] || resp.model}
            {resp.duration_ms != null && (
              <span className="duration-badge">{formatDuration(resp.duration_ms)}</span>
            )}
          </button>
        ))}
      </div>

      <div className="tab-content">
        <div className="model-name">
          {responses[activeTab].model}
          {responses[activeTab].duration_ms != null && (
            <span className="duration-detail">
              ⏱ {formatDuration(responses[activeTab].duration_ms)}
            </span>
          )}
        </div>
        <div className="response-text markdown-content">
          <Markdown>{responses[activeTab].response}</Markdown>
        </div>
      </div>
    </div>
  );
}
