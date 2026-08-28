import { useEffect, useRef, useState } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import CouncilMark from './CouncilMark';
import ThemeToggle from './ThemeToggle';
import './Sidebar.css';

export default function Sidebar({
  conversations,
  onNewConversation,
  isCreating = false,
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

        <nav className="conversation-list" ref={listRef} aria-label="Conversations">
          {conversations.length === 0 ? (
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
                <div className="conversation-title">
                  {conv.title || 'New Conversation'}
                </div>
                <div className="conversation-meta">
                  {conv.message_count}{' '}
                  {conv.message_count === 1 ? 'message' : 'messages'}
                </div>
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
