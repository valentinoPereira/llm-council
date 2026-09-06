import { useEffect, useLayoutEffect, useRef } from 'react';

/**
 * Owns all chat auto-scroll policy.
 *
 * Follow-scroll only fires while the user is pinned near the bottom AND has
 * not started reading the deliberation. Once the user signals reading intent
 * (scrolled up, switched a stage tab, or selected text) follow-scroll is
 * suppressed until they explicitly return to the bottom with no active
 * selection. This keeps newly arrived sections (e.g. Peer Review appearing
 * while the user reads Deliberation) from yanking the viewport.
 */
const scrollPositions = new Map();

const BOTTOM_THRESHOLD = 80;

function hasActiveSelection() {
  const sel = window.getSelection();
  return !!sel && !sel.isCollapsed;
}

export default function useCouncilAutoScroll({ conversation, conversationId }) {
  const containerRef = useRef(null);
  const messagesEndRef = useRef(null);
  const isAtBottomRef = useRef(true);
  const userReadingRef = useRef(false);
  const hasRestoredScrollRef = useRef(false);
  const isInitialScrollRef = useRef(true);
  const prevMessagesCountRef = useRef(conversation?.messages?.length ?? 0);
  const conversationIdRef = useRef(conversationId);

  // Keep the latest conversation id available to the synchronous onScroll.
  useEffect(() => {
    conversationIdRef.current = conversationId;
  }, [conversationId]);

  const onScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const cid = conversationIdRef.current;
    if (cid) scrollPositions.set(cid, el.scrollTop);

    const atBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < BOTTOM_THRESHOLD;
    isAtBottomRef.current = atBottom;

    // Resume following only once the user is back at the bottom AND has no
    // active selection. Position alone, or an active highlight alone, is not
    // enough to declare "done reading".
    if (atBottom && !hasActiveSelection()) {
      userReadingRef.current = false;
    }
  };

  const markUserReading = () => {
    userReadingRef.current = true;
  };

  // A new conversation starts from a clean state. ChatInterface doesn't remount
  // across conversation switches, so the reading refs must be reset here.
  useEffect(() => {
    userReadingRef.current = false;
    isAtBottomRef.current = true;
  }, [conversationId]);

  // Treat in-container text selections as reading intent. Filtered to only the
  // messages container so the composer / other inputs never count.
  useEffect(() => {
    const onSelectionChange = () => {
      const el = containerRef.current;
      const sel = window.getSelection();
      if (!el || !sel || sel.isCollapsed) return;
      const { anchorNode, focusNode } = sel;
      if (
        anchorNode &&
        focusNode &&
        el.contains(anchorNode) &&
        el.contains(focusNode)
      ) {
        userReadingRef.current = true;
      }
    };
    document.addEventListener('selectionchange', onSelectionChange);
    return () =>
      document.removeEventListener('selectionchange', onSelectionChange);
  }, []);

  // Restore saved scroll position synchronously before the browser paints.
  // useLayoutEffect ensures there's no visible flash of the wrong position.
  // Deps intentionally omit `conversation`: per-stream-tick scrollTop writes
  // fight the browser's anchor preserving the user's place.
  //
  // With no saved position this conversation starts FRESH: restore/initial
  // refs could still be set by a previously visited conversation (the
  // component doesn't remount across switches) leaving auto-scroll disabled
  // for this one. The reset lives here — layout runs before paint and before
  // passive effects, so it can't clobber a restore performed this commit.
  // prevMessagesCount resets to 0: the initial-scroll path that follows
  // short-circuits before the count is read, so the placeholder is inert.
  useLayoutEffect(() => {
    if (!conversationId || !containerRef.current) return;
    const saved = scrollPositions.get(conversationId);
    if (saved != null) {
      containerRef.current.scrollTop = saved;
      hasRestoredScrollRef.current = true;
      isInitialScrollRef.current = false;
    } else {
      hasRestoredScrollRef.current = false;
      isInitialScrollRef.current = true;
      prevMessagesCountRef.current = 0;
    }
  }, [conversationId]);

  // Scroll to bottom when conversation data arrives.
  // First load (no saved position): instant. New message: smooth follow.
  // Streaming updates while in flight: only follow when the user is pinned
  // near the bottom AND not reading — never yank a reader.
  // Skipped entirely when a saved scroll position was restored.
  useEffect(() => {
    if (!conversation || hasRestoredScrollRef.current) return;
    if (isInitialScrollRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
      isInitialScrollRef.current = false;
      return;
    }
    // Reading intent wins over everything, even while pinned at the bottom —
    // "at the bottom" is where the annoyance most often happens (the user
    // followed the stream there and is reading Deliberation when Peer Review
    // mounts).
    if (userReadingRef.current) return;
    const messagesCount = conversation.messages?.length ?? 0;
    const messageCountGrew = messagesCount > prevMessagesCountRef.current;
    prevMessagesCountRef.current = messagesCount;
    if (messageCountGrew) {
      // New message from the user: unambiguous intent to follow along.
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      return;
    }
    if (isAtBottomRef.current) {
      // Instant pin — no smooth scroll — so there's no animation window for a
      // programmatic scroll to fight a user's wheel/touch input.
      const el = containerRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    }
  }, [conversation]);

  return { containerRef, messagesEndRef, onScroll, markUserReading };
}
