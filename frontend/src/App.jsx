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

            const currentConversation = queryClient.getQueryData([
              'conversation',
              targetId,
            ]);
            notifyChairmanDone({
              conversationId: targetId,
              conversationTitle: currentConversation?.title,
              hasError: Boolean(event.data?.error),
            });
          }

          if (eventType === 'title_complete') {
            queryClient.setQueryData(
              ['conversation', targetId],
              (old) =>
                old ? { ...old, title: event.data.title } : old
            );
            queryClient.setQueryData(['conversations'], (old) => {
              if (!old) return old;
              return old.map((c) =>
                c.id === targetId
                  ? { ...c, title: event.data.title }
                  : c
              );
            });
            return;
          }

          queryClient.setQueryData(['conversation', targetId], (old) => {
            if (!old) return old;
            const messages = [...old.messages];
            const lastIdx = messages.length - 1;
            const last = messages[lastIdx];
            if (!last || last.role !== 'assistant') return old;

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
              default:
                break;
            }

            messages[lastIdx] = nextLast;
            return { ...old, messages };
          });
        });
      } catch (error) {
        // Network/parse errors become stream errors too.
        streamError = streamError ?? error;
      }

      if (streamError && !stageCompleted) {
        // Roll back only when the stream broke BEFORE stage3 completed.
        // If stage3 reported an error object, the assistant message stays so
        // its partial data can be displayed.
        queryClient.setQueryData(['conversation', targetId], (old) => {
          if (!old) return old;
          const messages = old.messages;
          const tail = messages.slice(-2);
          if (
            tail.length === 2 &&
            tail[0].role === 'user' &&
            tail[0].content === content &&
            tail[1].role === 'assistant'
          ) {
            return { ...old, messages: messages.slice(0, -2) };
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
  const { data: conversations = [] } = useConversations();
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
      isLoading={send.isPending}
    />
  );
}

export default function AppWithProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <App />
      <Toaster
        position="top-right"
        richColors
        closeButton={false}
        toastOptions={{
          closeButton: false,
          style: {
            fontFamily:
              "var(--font-body), system-ui, -apple-system, 'Segoe UI', sans-serif",
          },
        }}
      />
    </QueryClientProvider>
  );
}
