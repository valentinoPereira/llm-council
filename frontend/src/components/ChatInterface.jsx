import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import CouncilMark from './CouncilMark';
import CouncilProgress from './CouncilProgress';
import Markdown from './Markdown';
import Stage1 from './Stage1';
import Stage2 from './Stage2';
import Stage3 from './Stage3';
import './ChatInterface.css';

/** Persists per-conversation scroll positions across unmount/remount cycles. */
const scrollPositions = new Map();

const CONVENING_PHRASES = [
  { text: 'Convening the council' },
  { text: 'The members take their seats' },
  {
    text: 'If I have seen further, it is by standing on the shoulders of giants',
    attribution: 'Isaac Newton',
  },
  { text: 'Voices rise around the table' },
  {
    text: 'It is the mark of an educated mind to entertain a thought without accepting it',
    attribution: 'Aristotle',
  },
  { text: 'Arguments are weighed in turn' },
  {
    text: 'If you want to go fast, go alone. If you want to go far, go together',
    attribution: 'African proverb',
  },
  { text: 'Counsel is being taken' },
  {
    text: 'Plans are worthless, but planning is everything',
    attribution: 'Dwight D. Eisenhower',
  },
  { text: 'The members deliberate among themselves' },
  {
    text: 'Doubt is not a pleasant condition, but certainty is absurd',
    attribution: 'Voltaire',
  },
  { text: 'The chamber grows quiet' },
  { text: 'The Chairman prepares the verdict' },
];

/**
 * Sticky ceremonial indicator shown while the council is in session.
 * Sits at the bottom of the chat viewport even when the user scrolls up,
 * and rotates through phrases that reinforce the deliberation metaphor.
 */
function ConveningIndicator() {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setIndex((prev) => (prev + 1) % CONVENING_PHRASES.length);
    }, 4200);
    return () => clearInterval(interval);
  }, []);

  const phrase = CONVENING_PHRASES[index];

  return (
    <div
      className="convening-indicator"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <div className="convening-pill">
        <CouncilMark className="convening-mark" aria-hidden="true" />
        <span className="convening-text" aria-hidden="true">
          {[
            <span key={`phrase-${index}`} className="convening-line">
              {phrase.text}
            </span>,
            phrase.attribution ? (
              <span key={`attr-${index}`} className="convening-attribution">
                — {phrase.attribution}
              </span>
            ) : null,
          ]}
        </span>
        <span className="convening-sr-only">The council is deliberating</span>
      </div>
    </div>
  );
}

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

/**
 * Shown while an existing conversation is being fetched from the API, so the
 * empty-state hero never flashes on top of a loading chat view.
 */
function LoadingState() {
  return (
    <div className="chat-loading" role="status" aria-live="polite">
      <div className="chat-loading-spinner" aria-hidden="true" />
      <span className="chat-loading-label loading-ellipsis">
        Retrieving the record
      </span>
    </div>
  );
}

export default function ChatInterface({
  conversation,
  conversationId,
  onSendMessage,
  onNewConversation,
  isLoading,
  isConversationLoading = false,
}) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const containerRef = useRef(null);
  const hasRestoredScrollRef = useRef(false);
  const isInitialScrollRef = useRef(true);

  // Save scroll position continuously so it's always up-to-date,
  // regardless of when/how the component unmounts.
  const conversationIdRef = useRef(conversationId);
  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  const onScroll = () => {
    const cid = conversationIdRef.current;
    if (cid && containerRef.current) {
      scrollPositions.set(cid, containerRef.current.scrollTop);
    }
  };

  // Restore saved scroll position synchronously before the browser paints.
  // useLayoutEffect ensures there's no visible flash of the wrong position.
  useLayoutEffect(() => {
    if (!conversationId || !containerRef.current) return;
    const saved = scrollPositions.get(conversationId);
    if (saved != null) {
      containerRef.current.scrollTop = saved;
      hasRestoredScrollRef.current = true;
      isInitialScrollRef.current = false;
    }
  }, [conversationId, conversation]);

  // Scroll to bottom when conversation data arrives.
  // First load (no saved position): instant. Streaming updates: smooth.
  // Skipped entirely when a saved scroll position was restored.
  useEffect(() => {
    if (!conversation || hasRestoredScrollRef.current) return;
    if (isInitialScrollRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
      isInitialScrollRef.current = false;
    } else {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
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
          {isConversationLoading ? <LoadingState /> : <EmptyStateHero />}
        </div>
      </div>
    );
  }

  return (
    <div className="chat-interface">
      <div className="messages-container" ref={containerRef} onScroll={onScroll}>
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

                    {msg.stage3 && (
                      <div className="deliberation-closed">
                        <div className="deliberation-closed-rule" aria-hidden="true" />
                        <p className="deliberation-closed-copy">
                          The Council has spoken — this deliberation is closed.
                          {onNewConversation && (
                            <>
                              {' '}
                              For your next question,{' '}
                              <button
                                type="button"
                                className="deliberation-closed-link"
                                onClick={onNewConversation}
                              >
                                summon a new council
                              </button>
                              .
                            </>
                          )}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}

          {isLoading && conversation.messages.length > 0 && <ConveningIndicator />}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Deliberations are one-shot: once the council has answered, the
          conversation is read-only and the composer disappears. */}
      {conversation.messages.length === 0 && (
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
      )}
    </div>
  );
}
