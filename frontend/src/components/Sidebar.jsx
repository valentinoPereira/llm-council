import { useEffect, useRef, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import CouncilMark from './CouncilMark';
import ThemeToggle from './ThemeToggle';
import './Sidebar.css';

export default function Sidebar({
  conversations,
  isLoading = false,
  onNewConversation,
  onDeleteConversation,
  isCreating = false,
  isDeleting = false,
}) {
  const { conversationId: activeId } = useParams();
  const listRef = useRef(null);
  const [isOpen, setIsOpen] = useState(false);

  // When the route changes (or after first paint), scroll the active
  // conversation item into view in the sidebar list.
  useEffect(() => {
    if (!listRef.current) return;
    if (!activeId) return;
    const el = listRef.current.querySelector(
      `[data-conversation-id="${CSS.escape(activeId)}"]`
    );
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest' });
    }
  }, [activeId, conversations]);

  // Selecting a conversation on mobile closes the overlay sidebar.
  const handleNavigate = () => setIsOpen(false);

  // Shimmer placeholder rows shown only during the very first conversations
  // fetch, so the sidebar doesn't flash "No conversations yet".
  const skeletonRows = [0, 1, 2, 3, 4, 5];

  return (
    <>
      <button
        className="sidebar-menu-toggle"
        onClick={() => setIsOpen((v) => !v)}
        aria-label={isOpen ? 'Close conversation list' : 'Open conversation list'}
        aria-expanded={isOpen}
      >
        <span className="menu-toggle-line" />
        <span className="menu-toggle-line" />
      </button>

      {isOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside className={`sidebar ${isOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <div className="brand">
            <CouncilMark className="brand-mark" />
            <h1 className="brand-wordmark">LLM Council</h1>
          </div>
          <div className="brand-rule" aria-hidden="true" />
          <button
            className="new-conversation-btn"
            onClick={onNewConversation}
            disabled={isCreating}
            aria-label="Summon a Council — start a new conversation"
          >
            Summon a Council
          </button>
        </div>

        <nav
          className="conversation-list"
          ref={listRef}
          aria-label="Conversations"
          aria-busy={isLoading || undefined}
        >
          {isLoading ? (
            skeletonRows.map((i) => (
              <div
                key={`conversation-skeleton-${i}`}
                className="conversation-skeleton"
                aria-hidden="true"
              >
                <div
                  className="skeleton-bar skeleton-title"
                  style={{ animationDelay: `${i * 0.1}s` }}
                />
                <div
                  className="skeleton-bar skeleton-meta"
                  style={{ animationDelay: `${i * 0.1}s` }}
                />
              </div>
            ))
          ) : conversations.length === 0 ? (
            <div className="no-conversations">No conversations yet</div>
          ) : (
            conversations.map((conv) => (
              <NavLink
                key={conv.id}
                to={`/c/${conv.id}`}
                data-conversation-id={conv.id}
                onClick={handleNavigate}
                className={({ isActive }) =>
                  `conversation-item ${isActive ? 'active' : ''}`
                }
              >
                <div className="conversation-item-content">
                  <div className="conversation-title">
                    {conv.title || 'New Conversation'}
                  </div>
                  <div className="conversation-meta">
                    {conv.message_count}{' '}
                    {conv.message_count === 1 ? 'message' : 'messages'}
                  </div>
                </div>
                <button
                  type="button"
                  className="delete-conversation-btn"
                  title="Delete conversation"
                  aria-label="Delete conversation"
                  disabled={isDeleting}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    onDeleteConversation?.(conv.id);
                  }}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    <line x1="10" y1="11" x2="10" y2="17" />
                    <line x1="14" y1="11" x2="14" y2="17" />
                  </svg>
                </button>
              </NavLink>
            ))
          )}
        </nav>

        <div className="sidebar-footer">
          <ThemeToggle />
        </div>
      </aside>
    </>
  );
}
