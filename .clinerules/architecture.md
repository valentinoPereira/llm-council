# Architecture Rules

Enforced structure of the LLM Council codebase. Universal — applies to any file.

## Layering (backend)

- Model access goes **only** through `backend/openrouter.py` (thin adapter over the official `openrouter` SDK). Never call the OpenRouter REST API directly, never use another HTTP client for model calls, never put SDK calls in `council.py`, `storage.py`, or `main.py`.
- The 3-stage pipeline lives **only** in `backend/council.py`: `stage1_collect_responses()`, `stage2_collect_rankings()`, `stage3_synthesize_final()`, `parse_ranking_from_text()`, `calculate_aggregate_rankings()`. Endpoints in `main.py` orchestrate these functions; they must not re-implement stage logic.
- Storage logic lives **only** in `backend/storage.py` (the sole DB access layer).
- Model identifiers live **only** in `backend/config.py` (`COUNCIL_MODELS`, `CHAIRMAN_MODEL`). Never hardcode model ids elsewhere.
- FastAPI app and endpoints live in `backend/main.py`.

## Pipeline semantics

- Stage 2 must anonymize responses before sending them to models: council members receive "Response A", "Response B", ... labels only. The backend builds and returns the `label_to_model` mapping.
- Stage 1 and Stage 2 fan out model calls in parallel (`asyncio.gather()` via `query_models_parallel()`); do not run them sequentially.
- Stage 3 (chairman synthesis) receives full context: original query, all Stage 1 responses, and all Stage 2 evaluations/rankings.
- A single model failure must never abort the pipeline — see graceful degradation in `backend.md`.

## Storage schema

- Conversations persist in SQLite via `backend/storage.py` (aiosqlite) — DB file is `data/conversations/council.db`. No other module reads/writes the database; storage is the only DB access layer.
- Tables: `conversations(id, created_at, title)` and `messages(id, conversation_id, role, content, stage1, stage2, stage3, metadata, created_at)`. Stage payloads and `metadata` are stored as JSON blobs — keep this shape; don't add new persisted columns without updating `storage.py`.
- Legacy JSON files in `data/conversations/*.json` are pre-migration leftovers — only `backend/migrate_json_to_sqlite.py` reads them; never write new JSON conversation files.

## Frontend structure

- React Router v7: `<BrowserRouter>` in `src/main.jsx` (wrapped in `next-themes` ThemeProvider); only two routes exist: `/` (new chat / home) and `/c/:conversationId`, defined in `App.jsx`.
- Routing is derived from the URL via `useParams()` — never from local state (see `frontend.md`).
- Server state is owned by **@tanstack/react-query**: `useConversations` / `useConversation` / `useSendMessage` live in `App.jsx` and update the query cache (`setQueryData`) — don't duplicate fetch/state logic in components.
- The SSE streaming loop (optimistic assistant message + `api.sendMessageStream` events) lives in `useSendMessage()` in `App.jsx`; don't duplicate it elsewhere.
- `ChatRoute`/`HomeRoute` are internal components of `App.jsx` handling route-specific behavior (fetch + 404 redirect; submit-then-navigate with `replace: true`).
- Stage display stays in `Stage1.jsx` / `Stage2.jsx` / `Stage3.jsx` as tabbed, presentational components.

## Transparency requirement

- All raw model outputs must remain inspectable in the UI (tab views), and parsed rankings must be shown below the raw evaluation text so users can validate parsing. Never display only the parsed/synthesized result.
