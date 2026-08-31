/**
 * API client for the LLM Council backend.
 */

import { fetchEventSource } from '@microsoft/fetch-event-source';

const API_BASE = 'http://localhost:8001';

export const api = {
  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) {
      throw new Error('Failed to list conversations');
    }
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({}),
    });
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`
    );
    if (!response.ok) {
      throw new Error('Failed to get conversation');
    }
    return response.json();
  },

  /**
   * Permanently delete a conversation and all of its messages.
   */
  async deleteConversation(conversationId) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}`,
      {
        method: 'DELETE',
      }
    );
    if (!response.ok) {
      throw new Error('Failed to delete conversation');
    }
  },

  /**
   * Send a message in a conversation.
   */
  async sendMessage(conversationId, content) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ content }),
      }
    );
    if (!response.ok) {
      throw new Error('Failed to send message');
    }
    return response.json();
  },

  /**
   * Send a message and receive streaming updates via Server-Sent Events.
   *
   * Uses @microsoft/fetch-event-source for spec-compliant SSE parsing (handles
   * multi-line data fields, comment lines, event IDs) and proper abort support.
   *
   * The backend stream is a one-shot POST: it runs the council once and then
   * closes the connection. There is no resumable event log, so auto-reconnect
   * would re-run the entire council — we therefore stop reconnection by
   * throwing in onclose/onerror and terminate the stream cleanly with an
   * internal AbortController once a terminal event (`complete` or `error`) is
   * received. The returned promise resolves on success and rejects on error,
   * matching the previous fetch-based contract.
   *
   * @param {string} conversationId - The conversation ID
   * @param {string} content - The message content
   * @param {function} onEvent - Callback function for each event: (eventType, data) => void
   * @returns {Promise<void>}
   */
  async sendMessageStream(conversationId, content, onEvent) {
    const url = `${API_BASE}/api/conversations/${conversationId}/message/stream`;
    // Internal controller so we can terminate the stream ourselves once the
    // backend signals completion. fetchEventSource has no built-in
    // "resolve when server closes" path for non-resumable streams.
    const ctrl = new AbortController();
    const TERMINAL_EVENTS = new Set(['complete', 'error']);

    try {
      await fetchEventSource(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ content }),
        signal: ctrl.signal,
        // Keep the stream alive while the tab is hidden; the council run can
        // take a while and the browser would otherwise pause EventSource.
        openWhenHidden: true,
        async onopen(response) {
          if (!response.ok) {
            // Client errors (4xx except 429) are non-retriable; everything
            // else (5xx, 429) we also surface as a rejection here — the
            // caller already wraps failures as "Failed to send message".
            throw new Error('Failed to send message');
          }
          const contentType = response.headers.get('content-type') ?? '';
          if (!contentType.startsWith('text/event-stream')) {
            throw new Error('Failed to send message');
          }
        },
        onmessage(event) {
          let parsed;
          try {
            parsed = JSON.parse(event.data);
          } catch (e) {
            console.error('Failed to parse SSE event:', e);
            return;
          }
          onEvent(parsed.type, parsed);
          if (TERMINAL_EVENTS.has(parsed.type)) {
            // Cleanly end the stream. The AbortError is swallowed below.
            ctrl.abort();
          }
        },
        onclose() {
          // Server closed before a terminal event — unexpected early close.
          // Throwing here prevents silent auto-reconnect and rejects the
          // promise (unless we already aborted after a terminal event, in
          // which case the abort wins and this throw is suppressed).
          throw new Error('Failed to send message');
        },
        onerror(err) {
          // Rethrow to stop fetchEventSource's retry loop. Non-abort errors
          // become rejections; AbortError is handled below.
          if (err.name === 'AbortError') throw err;
          throw new Error('Failed to send message');
        },
      });
    } catch (err) {
      // Intentional abort after a terminal event = success.
      if (ctrl.signal.aborted) return;
      throw err instanceof Error ? err : new Error('Failed to send message');
    }
  },
};
