import * as Tabs from '@radix-ui/react-tabs';
import Markdown from './Markdown';
import { displayModelName, formatDuration } from '../utils';
import './Stage1.css';

/**
 * Stage 1 renders every member's independent response, one per tab.
 *
 * Members are presented in a Radix tab strip matching the Peer Review
 * section, so the reader can step through each answer individually. Raw
 * output stays fully inspectable; only the display name is prettified
 * (tooltip holds the raw id).
 */
export default function Stage1({ responses, onUserReading }) {
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

      <Tabs.Root
        defaultValue="tab-0"
        orientation="horizontal"
        onValueChange={onUserReading}
      >
        <Tabs.List className="tabs">
          {responses.map((resp, index) => (
            <Tabs.Trigger
              key={index}
              value={`tab-${index}`}
              className="tab"
            >
              {displayModelName(resp.model)}
              {resp.duration_ms != null && (
                <span className="duration-badge">
                  {formatDuration(resp.duration_ms)}
                </span>
              )}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {responses.map((resp, index) => (
          <Tabs.Content
            key={index}
            value={`tab-${index}`}
            className="tab-content"
          >
            <article className="response-card">
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
          </Tabs.Content>
        ))}
      </Tabs.Root>
    </div>
  );
}
