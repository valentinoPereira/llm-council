---
paths:
  - "backend/**"
  - "tests/**"
---

# OpenRouter Session Rules

One conversation = one OpenRouter session (grouping + sticky routing in the OpenRouter console).

- `main.openrouter_session_id(conversation_id)` builds a deterministic id: `llm-council-<conversation_id>` (max 256 chars per OpenRouter limit).
- The same session id must be passed to **every** model call in the conversation: stages 1–3 and title generation, on both the REST and streaming endpoints.
- The id is derived purely from the conversation id so it never changes mid-conversation — a session id that changes would break sticky routing and split the group in the console.
- `session_id` is a request body field on `/chat/completions` (also accepted as `x-session-id` header); the SDK accepts it as `session_id=` on `chat.send_async()`.
- Sessions are routing/observability only — OpenRouter does NOT store conversation memory; full message history must still be sent per request.
