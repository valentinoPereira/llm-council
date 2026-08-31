---
paths:
  - "backend/**"
  - "tests/**"
---

# Backend Guidelines

## Ports

- Backend runs on **port 8001** — NOT 8000 (user has another app on 8000).
- If ports change, update both `backend/main.py` and `frontend/src/api.js` (Vite dev server: port 5173).
- Requires `OPENROUTER_API_KEY` in `.env`. Set `USE_SIMULATED_MODELS=true` to run the full pipeline with synthetic responses (UI testing without credits or an API key).

## CORS

- CORS is enabled for `localhost:5173` and `localhost:3000`. Any change to frontend origin must be reflected in the allowed origins in `backend/main.py`.

## Error handling — graceful degradation

- Continue with successful responses if some models fail; never fail the entire request due to a single model failure.
- Log errors but don't expose them to the user unless all models fail.

## Chairman failover

- Stage 3 runs under an app-level timeout (`CHAIRMAN_TIMEOUT_S` in `config.py`). On timeout or failure it retries once with `CHAIRMAN_FALLBACK_MODEL` and marks the result with `fallback: true`; if both fail, it returns a graceful error result instead of aborting.

## Metadata persistence

- Metadata (`label_to_model`, `aggregate_rankings`) IS persisted: stored as a JSON blob in the `messages.metadata` column. If you change its shape, update `storage.py` and the frontend consumers together.

## Ranking parsing

- Stage 2 prompts models to output a strict format: evaluate each response individually first, then a `"FINAL RANKING:"` header, then a numbered list (`1. Response C`, `2. Response A`, ...), with no additional text after the ranking section.
- If models don't follow the format, a fallback regex extracts any `"Response X"` patterns in order.

## Observability

- Every successful response from `query_model()` includes `duration_ms` (round-trip wall time from `time.perf_counter()`); keep this contract on any new response path.
- `query_model()` / `query_models_parallel()` accept an optional `stage` label (`"stage1"`, `"stage2"`, `"stage3"`, `"title"`) used for per-call `[timing]` logs; stage totals log as `[timing] stage=<stage> total=Xs slowest=<model>`.
- Long stages emit SSE `stage_progress` heartbeat events every `STAGE_HEARTBEAT_S` so the UI can show live elapsed time.
- `reasoning_details` from the SDK are serialized to plain JSON-safe dicts inside `openrouter.py` before leaving the adapter — never leak SDK types to callers.

## Testing (mock injection)

- Tests inject a mock via `OpenRouter(async_client=httpx.AsyncClient(transport=httpx.MockTransport(...)))` and patch `openrouter.get_client()` — the SDK applies auth itself; the injected client only supplies the transport. Follow the pattern in `tests/test_pipeline.py` for new model-call tests.

## OpenRouter sessions

- One conversation = one OpenRouter session (grouping + sticky routing in the console): `main.openrouter_session_id(conversation_id)` builds a deterministic id `llm-council-<conversation_id>` (max 256 chars per OpenRouter limit), derived purely from the conversation id so it never changes mid-conversation.
- The same session id must be passed to **every** model call in the conversation — stages 1–3 and title generation, on both the REST and streaming endpoints. The SDK accepts it as `session_id=` on `chat.send_async()`.
- Sessions are routing/observability only — OpenRouter does NOT store conversation memory; full message history must still be sent per request.