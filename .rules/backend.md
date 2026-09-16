# Backend Rules (backend/ and tests/)

## Ports

- Backend runs on **port 8001** — NOT 8000 (user has another app on 8000).
- If ports change, update both `backend/main.py` and `frontend/src/api.js` (Vite dev server: port 5173).
- Requires `OPENROUTER_API_KEY` in `.env`. Set `USE_SIMULATED_MODELS=true` to run the full pipeline with synthetic responses (UI testing without credits or an API key).

## CORS

- CORS is enabled for `localhost:5173` and `localhost:3000`. Any change to frontend origin must be reflected in the allowed origins in `backend/main.py`.

## Pipeline semantics

- Stage 1 and Stage 2 fan out model calls in parallel (`asyncio.gather()` via `query_models_parallel()`); do not run them sequentially.
- Stage 3 (chairman synthesis) receives full context: original query, all Stage 1 responses, and all Stage 2 evaluations/rankings.
- The backend builds and returns the `label_to_model` mapping for Stage 2 anonymization.

## Chairman (stage 3)

- The chairman model is `glm-5.3` on NeuralWatt (OpenAI-compatible API, OpenAI SDK), called via `backend/neuralwatt.py` under the app-level timeout `CHAIRMAN_TIMEOUT_S`. There is **no fallback model** — the previous OpenRouter `x-ai/grok-4.6` vice-chairman was removed permanently.
- On timeout or failure the stage returns a graceful error result (`response: null` + `error` message); stages 1–2 results and rankings still persist.
- The NeuralWatt client is closed by the FastAPI lifespan alongside the OpenRouter client.
- The OpenRouter `session_id` is **not** sent on the chairman leg (NeuralWatt has no session concept).

## Error handling — graceful degradation

- Continue with successful responses if some models fail; never fail the entire request due to a single model failure.
- Log errors but don't expose them to the user unless all models fail.

## Storage schema

- Conversations persist in SQLite via `backend/storage.py` (aiosqlite) — DB file is `data/conversations/council.db`.
- Tables: `conversations(id, created_at, title)` and `messages(id, conversation_id, role, content, stage1, stage2, stage3, metadata, created_at)`. Stage payloads and `metadata` are stored as JSON blobs — keep this shape; don't add new persisted columns without updating `storage.py`.
- Legacy JSON files in `data/conversations/*.json` are pre-migration leftovers — only `backend/migrate_json_to_sqlite.py` reads them; never write new JSON conversation files.

## Metadata persistence

- Metadata (`label_to_model`, `aggregate_rankings`) IS persisted: stored as a JSON blob in the `messages.metadata` column. If you change its shape, update `storage.py` and the frontend consumers together.

## Ranking parsing

- Stage 2 prompts models to output a strict format: evaluate each response individually first, then a `"FINAL RANKING:"` header, then a numbered list (`1. Response C`, `2. Response A`, ...), with no additional text after the ranking section.
- If models don't follow the format, a fallback regex extracts any `"Response X"` patterns in order.

## Rankings endpoint (/api/rankings)

- `GET /api/rankings?top=N` (default `RANKINGS_TOP_N_DEFAULT = 4`) returns peer-review win-rate statistics for the **current** `COUNCIL_MODELS` only — historical models no longer on the council are not ranked.
- The computation lives **only** in `storage.get_model_rankings()`; `main.py` stays thin (slice + share normalization). All knobs (`RANKINGS_TOP_N_DEFAULT`, `RANKINGS_PRIOR_WEIGHT`, `RANKINGS_MIN_APPEARANCES`, `RANKINGS_WILSON_Z`, `RANKINGS_DUMMY_TITLES`) live in `config.py`.
- Semantics per message: appearance = model present in `metadata.label_to_model`; win = model tops `metadata.aggregate_rankings` (`average_rank == 1.0`, ties count for every co-leader).
- **Dummy-run exclusion**: conversations whose title full-matches `RANKINGS_DUMMY_TITLES` (case-insensitive) are dropped from stats entirely — if a real dummy title pattern is found, add it to the set in `config.py` rather than special-casing in code.
- **Small-sample protection (two layers)**:
  1. Quorum — models with fewer than `RANKINGS_MIN_APPEARANCES` are excluded from the leaderboard (new council members sit out until they accumulate runs).
  2. Wilson ranking — sort key is the Wilson-score **lower bound** on the raw win rate (`confidence_floor`), so leaders must have a proven win sample, not a lucky streak. Tie-breaks: shrunk rate, then appearances.
- **Share normalization**: the endpoint divides each shown model's empirical-Bayes shrunk rate (`adjusted_win_rate`, prior = pool mean, weight `RANKINGS_PRIOR_WEIGHT`) by the sum across the returned top-N slice, so displayed percentages add up to exactly 100%.
- Known data caveat (as of 2026-09): grok-4.6 (1 win / 7 runs) vs claude-opus-5 (2/22) are statistically indistinguishable — Wilson floors 2.6% vs 2.5%. This is a genuine ambiguity in the data, not a bug; the order between near-tied models can flip as samples grow.
- Tests: `tests/test_rankings.py` (sandboxed DB) covers raw stats, tie wins, dummy exclusion, quorum, shrinkage bounds, Wilson ordering, share normalization, and `?top` slicing.

## Observability

- Every successful response from `query_model()` includes `duration_ms` (round-trip wall time from `time.perf_counter()`); keep this contract on any new response path.
- `query_model()` / `query_models_parallel()` accept an optional `stage` label (`"stage1"`, `"stage2"`, `"stage3"`, `"title"`) used for per-call `[timing]` logs; stage totals log as `[timing] stage=<stage> total=Xs slowest=<model>`.
- Long stages emit SSE `stage_progress` heartbeat events every `STAGE_HEARTBEAT_S` so the UI can show live elapsed time.
- `reasoning_details` from the SDK are serialized to plain JSON-safe dicts inside `openrouter.py` before leaving the adapter — never leak SDK types to callers.

## Testing (mock injection)

- OpenRouter calls: inject a mock via `OpenRouter(async_client=httpx.AsyncClient(transport=httpx.MockTransport(...)))` and patch `openrouter.get_client()` — the SDK applies auth itself; the injected client only supplies the transport.
- NeuralWatt calls: inject a mock via `AsyncOpenAI(base_url=..., api_key="test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(...)))` and patch `neuralwatt.get_client()` (see `tests/test_neuralwatt.py`). Follow the pattern in `tests/test_pipeline.py` for new model-call tests.

## OpenRouter sessions

- One conversation = one OpenRouter session (grouping + sticky routing in the console): `main.openrouter_session_id(conversation_id)` builds a deterministic id `llm-council-<conversation_id>` (max 256 chars per OpenRouter limit), derived purely from the conversation id so it never changes mid-conversation.
- The same session id must be passed to **every** OpenRouter model call in the conversation — stages 1–2 and title generation, on both the REST and streaming endpoints. The SDK accepts it as `session_id=` on `chat.send_async()`. The chairman (stage 3) goes through NeuralWatt and is **not** given the OpenRouter session id.
- Sessions are routing/observability only — OpenRouter does NOT store conversation memory; full message history must still be sent per request.
