import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Routes,
  Route,
  useParams,
  useNavigate,
  useLocation,
} from 'react-router-dom';
import { Toaster, toast } from 'sonner';
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import Sidebar from './components/Sidebar';
import ChatInterface from './components/ChatInterface';
import { api } from './api';
import {
  ensureNotificationPermission,
  notifyChairmanDone,
  setActiveConversation,
  setNotificationNavigationCallback,
} from './notifications';
import './App.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
});

/**
 * Apply a single run SSE event to the React Query cache.
 *
 * Shared by `useSendMessage`'s stream callback and the ChatRoute attach
 * effect, so live streams and (re)played event logs converge on the same
 * reducer. Handles the last-message stage reducer plus the `title_complete`
 * side effects (conversation + list cache) and the `stage3_complete`
 * notification.
 */
function applyRunEvent(queryClient, targetId, eventType, event) {
  if (eventType === 'stage3_complete') {
    const currentConversation = queryClient.getQueryData([
      'conversation',
      targetId,
    ]);
    // The same run may be consumed by both the live send stream and the
    // global run-events watcher — fire the notification only once, from the
    // first consumer to process this terminal stage. (setQueryData below runs
    // synchronously within this call, so one of the two always sees the
    // message already complete and skips.)
    const lastMsg =
      currentConversation?.messages?.[
        (currentConversation?.messages?.length ?? 1) - 1
      ];
    const alreadyComplete =
      lastMsg?.role === 'assistant' &&
      (lastMsg.status === 'complete' || lastMsg.councilNotified);
    if (!alreadyComplete) {
      notifyChairmanDone({
        conversationId: targetId,
        conversationTitle: currentConversation?.title,
        hasError: Boolean(event.data?.error),
      });
    }
  }

  if (eventType === 'title_complete') {
    queryClient.setQueryData(['conversation', targetId], (old) =>
      old
        ? { ...old, title: event.data.title, category: event.data.category ?? old.category }
        : old
    );
    queryClient.setQueryData(['conversations'], (old) =>
      Array.isArray(old)
        ? old.map((c) =>
            c.id === targetId
              ? { ...c, title: event.data.title, category: event.data.category ?? c.category }
              : c
          )
        : old
    );
    return;
  }

  // `run_inactive` keeps the reducer pure; the caller performs the refetch
  // invalidation (see the ChatRoute attach effect).
  if (eventType === 'run_inactive') {
    return;
  }

  queryClient.setQueryData(['conversation', targetId], (old) => {
    if (!old) return old;
    const messages = [...old.messages];
    const lastIdx = messages.length - 1;
    const last = messages[lastIdx];
    // After a reconnect/refetch the last message may already be the
    // DB-persisted (partial or finished) assistant row — accept updates while
    // it is still in flight (status !== 'complete'). A finished message no
    // longer accepts updates (events and the refetch would otherwise race).
    if (!last || last.role !== 'assistant' || last.status === 'complete') return old;

    const nextLast = { ...last };

    switch (eventType) {
      case 'stage1_start':
        nextLast.loading = { ...nextLast.loading, stage1: true };
        break;
      case 'stage1_complete':
        nextLast.stage1 = event.data;
        nextLast.loading = { ...nextLast.loading, stage1: false };
        break;
      case 'stage2_start':
        nextLast.loading = { ...nextLast.loading, stage2: true };
        break;
      case 'stage2_complete':
        nextLast.stage2 = event.data;
        nextLast.metadata = event.metadata;
        nextLast.loading = { ...nextLast.loading, stage2: false };
        break;
      case 'stage3_start':
        nextLast.loading = { ...nextLast.loading, stage3: true };
        break;
      case 'stage3_progress':
        nextLast.loading = {
          ...nextLast.loading,
          stage3: { elapsed_s: event.elapsed_s },
        };
        break;
      case 'stage3_complete':
        nextLast.stage3 = event.data;
        nextLast.loading = { ...nextLast.loading, stage3: false };
        // Set the notification dedup flag at the same moment this consumer
        // processes the terminal stage, so a second consumer (live POST
        // stream + watcher GET /run/events both process the same event)
        // sees it set and skips — status is only 'complete' after the
        // later terminal 'complete' event, which doesn't help here. The
        // post-refetch DB row carries status 'complete', keeping the guard
        // effective across refetches too.
        nextLast.councilNotified = true;
        if (event.data?.error) {
          nextLast.stageError = event.data.error;
        }
        break;
      case 'stage_progress':
        // Generic per-stage heartbeat (stage3 gets richer handling above).
        nextLast.loading = {
          ...nextLast.loading,
          [event.stage]: { elapsed_s: event.elapsed_s },
        };
        break;
      case 'complete':
        // Terminal (attach/replay path): finalize the status so the attach
        // effect can stop and the refetchInterval loop ends.
        nextLast.status = 'complete';
        nextLast.loading = { stage1: false, stage2: false, stage3: false };
        break;
      case 'error':
        // Terminal (attach/replay path; the streaming path intercepts 'error'
        // in useSendMessage before reaching here).
        nextLast.status = 'error';
        nextLast.error = event.message;
        nextLast.loading = { stage1: false, stage2: false, stage3: false };
        break;
      default:
        break;
    }

    messages[lastIdx] = nextLast;
    return { ...old, messages };
  });
}

/**
 * App-level watcher for detached council runs.
 *
 * Event consumption was previously tied to a ChatRoute's auto-attach effect,
 * which unmounts on navigation — so a run completing while the user is on
 * another chat/browser-tab never delivered its `title_complete` (sidebar
 * title) or `stage3_complete` (notification) into the shared cache. This
 * hook scans the query cache for any conversation with a pending-assistant
 * tail and subscribes to its `/run/events` stream for as long as it stays
 * pending, regardless of the active route. Replaces the per-route attach
 * effect and survives navigation/reload.
 */
function useRunEventsWatcher() {
  const queryClient = useQueryClient();

  useEffect(() => {
    const controllers = new Map(); // conversationId -> AbortController

    const sync = () => {
      // Every cached conversation whose tail is a pending assistant row has a
      // live (or resumable) run we should be watching.
      const pending = new Set();
      for (const query of queryClient
        .getQueryCache()
        .findAll({ queryKey: ['conversation'] })) {
        const data = query.state.data;
        if (!data?.messages) continue;
        const last = data.messages[data.messages.length - 1];
        if (last?.role === 'assistant' && last?.status === 'pending') {
          pending.add(data.id);
        }
      }

      // Subscribe to newly-pending runs (replays buffered events, then tails
      // live). Re-running is idempotent because we skip already-tracked runs.
      for (const cid of pending) {
        if (controllers.has(cid)) continue;
        const ctrl = new AbortController();
        controllers.set(cid, ctrl);
        api
          .subscribeRun(
            cid,
            (type, parsed) => {
              if (type === 'run_inactive') {
                // No live job and nothing to replay — force a refetch; the
                // orphan sweep (or a just-finished run) resolves it.
                queryClient.invalidateQueries({
                  queryKey: ['conversation', cid],
                });
                return;
              }
              applyRunEvent(queryClient, cid, type, parsed);
            },
            { signal: ctrl.signal }
          )
          .catch(() => {
            // Connection dropped without a terminal event — retire this dead
            // controller so the next cache event (e.g. a refetchInterval
            // tick) re-establishes the subscription.
            if (controllers.get(cid) === ctrl) controllers.delete(cid);
          }); // non-fatal; refetchInterval is the fallback
      }

      // Drop watchers for runs that are no longer pending (completed/errored).
      for (const [cid, ctrl] of controllers) {
        if (!pending.has(cid)) {
          ctrl.abort();
          controllers.delete(cid);
        }
      }
    };

    sync();
    const unsubscribe = queryClient.getQueryCache().subscribe(sync);
    return () => {
      unsubscribe();
      for (const ctrl of controllers.values()) ctrl.abort();
    };
  }, [queryClient]);
}

function useConversations() {
  return useQuery({
    queryKey: ['conversations'],
    queryFn: api.listConversations,
  });
}

function useConversation(conversationId) {
  return useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.getConversation(conversationId),
    enabled: !!conversationId,
    retry: false,
    // Belt-and-braces against dropped SSE (e.g. a proxy killing idle GETs):
    // poll while a run is in flight, stop once it resolves.
    refetchInterval: (query) => {
      const msgs = query.state.data?.messages ?? [];
      const last = msgs[msgs.length - 1];
      return last?.role === 'assistant' && last.status === 'pending' ? 3000 : false;
    },
  });
}

function useCreateConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createConversation,
    onSuccess: (conversation) => {
      queryClient.setQueryData(['conversation', conversation.id], conversation);
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteConversation,
    onSuccess: (_, conversationId) => {
      queryClient.removeQueries({ queryKey: ['conversation', conversationId] });
      queryClient.setQueryData(['conversations'], (old) =>
        Array.isArray(old)
          ? old.filter((conv) => conv.id !== conversationId)
          : old
      );
    },
    onError: () => {
      toast.error('Failed to delete conversation');
    },
  });
}

function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ conversationId, content }) => {
      let targetId = conversationId;
      let newConversation = null;

      if (!targetId) {
        newConversation = await api.createConversation();
        targetId = newConversation.id;
      }

      const userMessage = { role: 'user', content };
      const assistantMessage = {
        role: 'assistant',
        stage1: null,
        stage2: null,
        stage3: null,
        metadata: null,
        status: 'pending',
        loading: { stage1: false, stage2: false, stage3: false },
      };

      queryClient.setQueryData(['conversation', targetId], (old) => ({
        ...(old ?? newConversation ?? { id: targetId }),
        messages: [...(old?.messages ?? []), userMessage, assistantMessage],
      }));

      let streamError = null;
      let stageCompleted = false;

      try {
        await api.sendMessageStream(targetId, content, (eventType, event) => {
          if (eventType === 'error') {
            streamError = new Error(event.message ?? 'Stream error');
            return;
          }

          if (eventType === 'stage3_complete') {
            stageCompleted = true;
          }

          applyRunEvent(queryClient, targetId, eventType, event);
        });
      } catch (error) {
        // Network/parse errors become stream errors too.
        streamError = streamError ?? error;
      }

      if (streamError && !stageCompleted) {
        // The assistant message now really exists in the DB (pending/error),
        // so the next refetch would resurrect it — do NOT remove the
        // user+assistant pair. Mark the last assistant message errored here;
        // the onSettled invalidation below refetches the authoritative state
        // the detached job persisted.
        queryClient.setQueryData(['conversation', targetId], (old) => {
          if (!old) return old;
          const messages = [...old.messages];
          const last = messages[messages.length - 1];
          if (last?.role === 'assistant') {
            messages[messages.length - 1] = {
              ...last,
              status: 'error',
              error: streamError.message,
              loading: { stage1: false, stage2: false, stage3: false },
            };
            return { ...old, messages };
          }
          return old;
        });
        throw streamError;
      }

      return targetId;
    },
    onMutate: async ({ conversationId }) => {
      if (!conversationId) return {};
      await queryClient.cancelQueries({
        queryKey: ['conversation', conversationId],
      });
      const previousConversation = queryClient.getQueryData([
        'conversation',
        conversationId,
      ]);
      return { previousConversation, conversationId };
    },
    onError: (error, variables, context) => {
      if (context?.previousConversation !== undefined) {
        queryClient.setQueryData(
          ['conversation', context.conversationId],
          context.previousConversation
        );
      }
    },
    onSettled: (targetId, error, variables) => {
      const id = targetId || variables.conversationId;
      if (id) {
        queryClient.invalidateQueries({ queryKey: ['conversation', id] });
      }
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });
}

function App() {
  useRunEventsWatcher();
  const {
    data: conversations = [],
    isLoading: isLoadingConversations,
  } = useConversations();
  const navigate = useNavigate();
  const location = useLocation();
  const create = useCreateConversation();
  const deleteConv = useDeleteConversation();

  // Register a React Router navigator for notification clicks so that focusing
  // the tab from a notification does not force a full page reload.
  useEffect(() => {
    setNotificationNavigationCallback((conversationId) => {
      navigate(`/c/${conversationId}#council-verdict`);
    });
    return () => setNotificationNavigationCallback(null);
  }, [navigate]);

  // The newest empty conversation is the canonical "new conversation".
  const emptyConversation = conversations.find(
    (conv) => conv.message_count === 0
  );

  const activeConversationId =
    location.pathname.match(/^\/c\/([^/]+)$/)?.[1] ?? null;

  // Tell the notification helper which conversation the user is viewing, so
  // it suppresses the completion ping only while they're watching that chat
  // (different chats should still notify).
  useEffect(() => {
    setActiveConversation(activeConversationId);
  }, [activeConversationId]);

  const handleNewConversation = useCallback(async () => {
    // If we already have an empty conversation, just open it instead of
    // creating another one.
    if (emptyConversation) {
      navigate(`/c/${emptyConversation.id}`);
      return;
    }

    try {
      const newConv = await create.mutateAsync();
      navigate(`/c/${newConv.id}`);
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }
  }, [create, navigate, emptyConversation]);

  const handleDeleteConversation = useCallback(
    async (conversationId) => {
      if (
        !window.confirm(
          'Delete this conversation? This action cannot be undone.'
        )
      ) {
        return;
      }

      try {
        await deleteConv.mutateAsync(conversationId);
        if (conversationId === activeConversationId) {
          navigate('/', { replace: true });
        }
        toast.success('Conversation deleted');
      } catch (err) {
        // Error toast is handled by the mutation's onError.
        console.error('Failed to delete conversation:', err);
      }
    },
    [activeConversationId, deleteConv, navigate]
  );

  return (
    <div className="app">
      <Sidebar
        conversations={conversations}
        isLoading={isLoadingConversations}
        onNewConversation={handleNewConversation}
        onDeleteConversation={handleDeleteConversation}
        isCreating={create.isPending}
        isDeleting={deleteConv.isPending}
      />
      <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route
          path="/c/:conversationId"
          element={
            <ChatRouteContainer onNewConversation={handleNewConversation} />
          }
        />
      </Routes>
    </div>
  );
}

function HomeRoute() {
  const navigate = useNavigate();
  const create = useCreateConversation();
  const [isCreating, setIsCreating] = useState(false);

  const handleSend = useCallback(
    async (content) => {
      ensureNotificationPermission().catch(() => {});
      setIsCreating(true);
      try {
        const newConv = await create.mutateAsync();
        navigate(`/c/${newConv.id}`, {
          state: { initialMessage: content },
          replace: true,
        });
      } catch (err) {
        console.error('Failed to start conversation:', err);
      } finally {
        setIsCreating(false);
      }
    },
    [create, navigate]
  );

  return (
    <ChatInterface
      conversation={{ messages: [] }}
      onSendMessage={handleSend}
      isLoading={isCreating || create.isPending}
    />
  );
}

function ChatRouteContainer({ onNewConversation }) {
  const { conversationId } = useParams();
  return (
    <ChatRoute
      key={conversationId}
      conversationId={conversationId}
      onNewConversation={onNewConversation}
    />
  );
}

function ChatRoute({ conversationId, onNewConversation }) {
  const navigate = useNavigate();
  const location = useLocation();
  const {
    data: conversation,
    isLoading,
    isError,
  } = useConversation(conversationId);
  const send = useSendMessage();
  const initialSentRef = useRef(false);

  useEffect(() => {
    if (isError) {
      navigate('/', { replace: true });
    }
  }, [isError, navigate]);

  // Made so `isLoading` also reflects a run owned by the backend (pending
  // tail) and not only this route's fresh mutation — keeps the floating
  // indicator visible and the composer locked when returning to a chat whose
  // run is still in flight. The run event stream itself is consumed
  // app-wide by `useRunEventsWatcher`, so it works on any route/tab.
  const msgs = conversation?.messages ?? [];
  const tail = msgs[msgs.length - 1];
  const pendingTail =
    tail?.role === 'assistant' && tail?.status === 'pending';

  useEffect(() => {
    const initialMessage = location.state?.initialMessage;
    if (
      initialMessage &&
      !send.isPending &&
      !initialSentRef.current &&
      conversation?.messages?.length === 0
    ) {
      ensureNotificationPermission().catch(() => {});
      initialSentRef.current = true;
      send.mutate({ conversationId, content: initialMessage });
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [conversationId, conversation, location, navigate, send]);

  const handleSend = useCallback(
    (content) => {
      ensureNotificationPermission().catch(() => {});
      send.mutate({ conversationId, content });
    },
    [send, conversationId]
  );

  if (isLoading || !conversation) {
    return (
      <ChatInterface
        conversation={null}
        conversationId={conversationId}
        onSendMessage={() => {}}
        isLoading={false}
        isConversationLoading={isLoading}
      />
    );
  }

  return (
    <ChatInterface
      conversation={conversation}
      conversationId={conversationId}
      onSendMessage={handleSend}
      onNewConversation={onNewConversation}
      // A run is in flight while this route's mutation is pending OR the tail
      // message is a pending assistant row (the latter covers returning to a
      // chat after switching away, where this fresh route's mutation is not
      // pending but the detached run still is). This keeps the floating
      // ConveningIndicator visible and the composer locked for the whole run.
      isLoading={send.isPending || pendingTail}
    />
  );
}

export default function AppWithProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            fontFamily:
              "var(--font-body), system-ui, -apple-system, 'Segoe UI', sans-serif",
          },
        }}
      />
    </QueryClientProvider>
  );
}
