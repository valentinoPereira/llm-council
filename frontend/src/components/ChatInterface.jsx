import { useState, useEffect, useRef } from 'react';
import CouncilMark from './CouncilMark';
import CouncilProgress from './CouncilProgress';
import Markdown from './Markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import './ChatInterface.css';

/**
 * First-impression hero: the wordmark, a gold rule, one quiet line of copy.
 * Shown on the home route and in any conversation with no messages yet.
 */
function EmptyStateHero() {
  return (
    <div className="empty-state">
      <CouncilMark className="empty-state-mark" />
      <h2 className="empty-state-wordmark">LLM Council</h2>
      <div className="empty-state-rule" aria-hidden="true" />
      <p className="empty-state-copy">
        Pose a question. A council of frontier models deliberates, reviews its
        own answers, and delivers a single synthesized verdict.
      </p>
    </div>
  );
}

export default function ChatInterface({
  conversation,
  onSendMessage,
  isLoading,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [conversation]);

  // Return focus to the composer when a run finishes (loading → idle).
  // Skipped on mount and on touch-sized screens to avoid popping the keyboard.
  const wasLoadingRef = useRef(false);
  useEffect(() => {
    if (wasLoadingRef.current && !isLoading && window.innerWidth > 900) {
      inputRef.current?.focus();
    }
    wasLoadingRef.current = isLoading;
  }, [isLoading]);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (input.trim() && !isLoading) {
      onSendMessage(input);
      setInput('');
    }
  };

  const handleKeyDown = (e) => {
    // Submit on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  if (!conversation) {
    return (
      <div className="chat-interface">
        <div className="messages-container">
          <EmptyStateHero />
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container">
        <div className="reading-column">
          {conversation.messages.length === 0 ? (
            <EmptyStateHero />
          ) : (
            conversation.messages.map((msg, index) => (
              <div key={index} className="message-group">
                {msg.role === 'user' ? (
                  <div className="user-message">
                    <div className="message-label">You</div>
                    <div className="message-content">
                      <div className="markdown-content">
                        <Markdown>{msg.content}</Markdown>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="assistant-message">
                    <div className="message-label message-label-council">
                      <CouncilMark className="message-label-mark" />
                      The Council
                    </div>

                    {/* Ceremonial progress while any stage is in flight */}
                    <CouncilProgress message={msg} />

                    {msg.stage1 && <Stage1 responses={msg.stage1} />}

                    {msg.stage2 && (
                      <Stage2
                        rankings={msg.stage2}
                        labelToModel={msg.metadata?.label_to_model}
                        aggregateRankings={msg.metadata?.aggregate_rankings}
                      />
                    )}

                    {msg.stage3 && <Stage3 finalResponse={msg.stage3} />}
                  </div>
                )}
              </div>
            ))
          )}

          {isLoading && conversation.messages.length > 0 && (
            <div className="loading-indicator" role="status">
              <span className="loading-ellipsis">Convening the council</span>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      <div className="composer-area">
        <form className="composer" onSubmit={handleSubmit}>
          <textarea
            ref={inputRef}
            className="message-input"
            placeholder="Pose your question to the Council…"
            aria-label="Message the Council"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            rows={3}
          />
          <div className="composer-footer">
            <span className="composer-hint">
              Enter to send · Shift + Enter for a new line
            </span>
            <button
              type="submit"
              className="send-button"
              disabled={!input.trim() || isLoading}
            >
              Consult the Council
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
