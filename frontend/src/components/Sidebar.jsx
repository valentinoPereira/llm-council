import { useEffect, useRef } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';
import './Sidebar.css';

export default function Sidebar({ conversations, onNewConversation }) {
  const { conversationId: activeId } = useParams();
  const listRef = useRef(null);

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

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-header-top">
          <h1>LLM Council</h1>
          <ThemeToggle />
        </div>
        <button className="new-conversation-btn" onClick={onNewConversation}>
          + New Conversation
        </button>
      </div>

      <div className="conversation-list" ref={listRef}>
        {conversations.length === 0 ? (
          <div className="no-conversations">No conversations yet</div>
        ) : (
          conversations.map((conv) => (
            <NavLink
              key={conv.id}
              to={`/c/${conv.id}`}
              data-conversation-id={conv.id}
              className={({ isActive }) =>
                `conversation-item ${isActive ? 'active' : ''}`
              }
            >
              <div className="conversation-title">
                {conv.title || 'New Conversation'}
              </div>
              <div className="conversation-meta">
                {conv.message_count} messages
              </div>
            </NavLink>
          ))
        )}
      </div>
    </div>
  );
}
