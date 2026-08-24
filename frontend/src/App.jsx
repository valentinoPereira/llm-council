import { useState, useEffect, useCallback, useRef } from 'react';
import { Routes, Route, useParams, useNavigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import './App.css';

// Single source of truth for the optimistic-message + SSE-stream loop.
// Shared by both the home route (creates a new convo on first send) and the
// /c/:conversationId route (streams against an existing one).
//
// Returns:
//   messages       — full message list (user + assistant) for the active chat
//   isLoading      — true while a stream is in flight
//   loadMessages   — fetch an existing conversation's history by id
//   submit         — send a user message; creates a new convo if id is null
function useConversationStream() {
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  // Tracks the conversation we are currently bound to. Guards against
  // stale async resolves (e.g. user navigates away mid-fetch).
  const activeIdRef = useRef(null);

  const loadMessages = useCallback(async (conversationId) => {
    activeIdRef.current = conversationId;
    setMessages([]);
    setIsLoading(false);
    const conv = await api.getConversation(conversationId);
    // Drop the result if the user has navigated away mid-fetch.
    if (activeIdRef.current === conversationId) {
      setMessages(conv.messages ?? []);
    }
    return conv;
  }, []);

  const submit = useCallback(async (content, conversationId) => {
    let targetId = conversationId;

    if (!targetId) {
      const newConv = await api.createConversation();
      targetId = newConv.id;
    }

    activeIdRef.current = targetId;

    // Optimistic: append user message + skeleton assistant message.
    const userMessage = { role: 'user', content };
    const assistantMessage = {
      role: 'assistant',
      stage1: null,
      stage2: null,
      stage3: null,
      metadata: null,
      loading: { stage1: false, stage2: false, stage3: false },
    };
    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setIsLoading(true);

    const updateLast = (mutator) => {
      setMessages((prev) => {
        const next = [...prev];
        const last = next[next.length - 1];
        if (last && last.role === 'assistant') {
          mutator(last);
        }
        return next;
      });
    };

    try {
      await api.sendMessageStream(targetId, content, (eventType, event) => {
        switch (eventType) {
          case 'stage1_start':
            updateLast((m) => {
              m.loading.stage1 = true;
            });
            break;
          case 'stage1_complete':
            updateLast((m) => {
              m.stage1 = event.data;
              m.loading.stage1 = false;
            });
            break;
          case 'stage2_start':
            updateLast((m) => {
              m.loading.stage2 = true;
            });
            break;
          case 'stage2_complete':
            updateLast((m) => {
              m.stage2 = event.data;
              m.metadata = event.metadata;
              m.loading.stage2 = false;
            });
            break;
          case 'stage3_start':
            updateLast((m) => {
              m.loading.stage3 = true;
            });
            break;
          case 'stage3_complete':
            updateLast((m) => {
              m.stage3 = event.data;
              m.loading.stage3 = false;
            });
            break;
          case 'complete':
            setIsLoading(false);
            break;
          case 'error':
            console.error('Stream error:', event.message);
            setIsLoading(false);
            // Roll back the optimistic pair so the UI doesn't lie.
            setMessages((prev) => prev.slice(0, -2));
            break;
          default:
            break;
        }
      });
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages((prev) => prev.slice(0, -2));
      setIsLoading(false);
    }

    return targetId;
  }, []);

  return { messages, isLoading, loadMessages, submit };
}

function App() {
  const [conversations, setConversations] = useState([]);
  const navigate = useNavigate();

  // Load the sidebar conversation list once on mount.
  useEffect(() => {
    (async () => {
      try {
        const convs = await api.listConversations();
        setConversations(convs);
      } catch (error) {
        console.error('Failed to load conversations:', error);
      }
    })();
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const convs = await api.listConversations();
      setConversations(convs);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    }
  }, []);

  // "New Conversation" button — explicit create + navigate.
  const handleNewConversation = useCallback(async () => {
    try {
      const newConv = await api.createConversation();
      setConversations((prev) => [
        {
          id: newConv.id,
          created_at: newConv.created_at,
          title: newConv.title,
          message_count: 0,
        },
        ...prev,
      ]);
      navigate(`/c/${newConv.id}`);
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  }, [navigate]);

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        onNewConversation={handleNewConversation}
      />
      <Routes>
        <Route path="/" element={<HomeRoute onConversationsChanged={refreshConversations} />} />
        <Route
          path="/c/:conversationId"
          element={<ChatRouteContainer onConversationsChanged={refreshConversations} />}
        />
      </Routes>
    </div>
  );
}

// Home route — no active conversation. First send creates one and routes
// into /c/:id so reload preserves the session.
function HomeRoute({ onConversationsChanged }) {
  const { messages, isLoading, submit } = useConversationStream();
  const navigate = useNavigate();

  const handleSend = async (content) => {
    const newId = await submit(content, null);
    if (newId) {
      navigate(`/c/${newId}`, { replace: true });
      onConversationsChanged?.();
    }
  };

  return (
    <ChatInterface
      conversation={{ messages }}
      onSendMessage={handleSend}
      isLoading={isLoading}
    />
  );
}

// /c/:conversationId route — load existing chat, or redirect home on 404.
// The container passes :conversationId as React `key`, so the inner ChatRoute
// (and its useConversationStream hook) remounts on every chat switch. That
// gives us a clean slate: empty messages, no stale state from the previous
// chat, no manual resets.
function ChatRouteContainer({ onConversationsChanged }) {
  const { conversationId } = useParams();
  return (
    <ChatRoute
      key={conversationId}
      conversationId={conversationId}
      onConversationsChanged={onConversationsChanged}
    />
  );
}

function ChatRoute({ conversationId, onConversationsChanged }) {
  const navigate = useNavigate();
  const { messages, isLoading, submit, loadMessages } = useConversationStream();
  const [hasLoaded, setHasLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    loadMessages(conversationId)
      .then(() => {
        if (!cancelled) setHasLoaded(true);
      })
      .catch(() => {
        if (!cancelled) navigate('/', { replace: true });
      });
    return () => {
      cancelled = true;
    };
  }, [loadMessages, conversationId, navigate]);

  const handleSend = async (content) => {
    await submit(content, conversationId);
    onConversationsChanged?.();
  };

  // While the initial fetch is in flight, render an empty chat shell so
  // we don't flash the "Start a conversation" view over real history.
  if (!hasLoaded) {
    return (
      <ChatInterface
        conversation={null}
        onSendMessage={() => {}}
        isLoading={false}
      />
    );
  }

  return (
    <ChatInterface
      conversation={{ messages }}
      onSendMessage={handleSend}
      isLoading={isLoading}
    />
  );
}

export default App;
