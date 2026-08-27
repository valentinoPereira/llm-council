# Architecture Rules

Enforced structure of the LLM Council codebase. Universal — applies to any file.

## Layering (backend)

- Model access goes **only** through `backend/openrouter.py` (thin adapter over the official `openrouter` SDK). Never call the OpenRouter REST API directly, never use another HTTP client for model calls, never put SDK calls in `council.py`, `storage.py`, or `main.py`.
- The 3-stage pipeline lives **only** in `backend/council.py`: `stage1_collect_responses()`, `stage2_collect_rankings()`, `stage3_synthesize_final()`, `parse_ranking_from_text()`, `calculate_aggregate_rankings()`. Endpoints in `main.py` orchestrate these functions; they must not re-implement stage logic.
- Storage logic lives **only** in `backend/storage.py`. No other module reads/writes `data/conversations/` directly.
- Model identifiers live **only** in `backend/config.py` (`COUNCIL_MODELS`, `CHAIRMAN_MODEL`). Never hardcode model ids elsewhere.
- FastAPI app and endpoints live in `backend/main.py`.

## Pipeline semantics

- Stage 2 must anonymize responses before sending them to models: council members receive "Response A", "Response B", ... labels only. The backend builds and returns the `label_to_model` mapping.
- Stage 1 and Stage 2 fan out model calls in parallel (`asyncio.gather()` via `query_models_parallel()`); do not run them sequentially.
- Stage 3 (chairman synthesis) receives full context: original query, all Stage 1 responses, and all Stage 2 evaluations/rankings.
- A single model failure must never abort the pipeline — see graceful degradation in `backend.md`.

## Storage schema

- Conversations persist as JSON files in `data/conversations/`: `{id, created_at, messages[]}`.
- Assistant messages contain `{role, stage1, stage2, stage3}` — keep this shape; don't add new persisted top-level message fields without updating `storage.py`.
- Metadata (`label_to_model`, `aggregate_rankings`) is never written to storage (see `backend.md`).

## Frontend structure

- React Router v7 with `<BrowserRouter>` in `src/main.jsx`; only two routes exist: `/` (new chat / home) and `/c/:conversationId`.
- Routing is derived from the URL via `useParams()` — never from local state (see `frontend.md`).
- `useConversationStream()` owns the optimistic-message + SSE streaming loop; don't duplicate streaming logic in components.
- `App.jsx` owns the conversations list, current conversation state, and ephemeral metadata state.
- `ChatRoute`/`HomeRoute` handle route-specific behavior (fetch + 404 redirect; submit-then-navigate with `replace: true`).
- Stage display stays in `Stage1.jsx` / `Stage2.jsx` / `Stage3.jsx` as tabbed, presentational components.

## Transparency requirement

- All raw model outputs must remain inspectable in the UI (tab views), and parsed rankings must be shown below the raw evaluation text so users can validate parsing. Never display only the parsed/synthesized result.
