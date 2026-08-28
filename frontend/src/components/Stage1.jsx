import * as Tabs from '@radix-ui/react-tabs';
import Markdown from './Markdown';
import { formatDuration } from '../utils';
import './Stage1.css';

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

      <Tabs.Root defaultValue="tab-0" orientation="horizontal">
        <Tabs.List className="tabs">
          {responses.map((resp, index) => (
            <Tabs.Trigger
              key={index}
              value={`tab-${index}`}
              className="tab"
            >
              {resp.model.split('/')[1] || resp.model}
              {resp.duration_ms != null && (
                <span className="duration-badge">{formatDuration(resp.duration_ms)}</span>
              )}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {responses.map((resp, index) => (
          <Tabs.Content key={index} value={`tab-${index}`} className="tab-content">
            <div className="model-name">
              {resp.model}
              {resp.duration_ms != null && (
                <span className="duration-detail">
                  {formatDuration(resp.duration_ms)}
                </span>
              )}
            </div>
            <div className="response-text markdown-content">
              <Markdown>{resp.response}</Markdown>
            </div>
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </div>
  );
}
