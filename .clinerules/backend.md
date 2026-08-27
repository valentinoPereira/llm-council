---
paths:
  - "backend/**"
  - "tests/**"
---

# Backend Guidelines

## Ports

- Backend runs on **port 8001** — NOT 8000 (user has another app on 8000).
- If ports change, update both `backend/main.py` and `frontend/src/api.js`.

## CORS

- CORS is enabled for `localhost:5173` and `localhost:3000`. Any change to frontend origin must be reflected in the allowed origins in `backend/main.py`.

## Error handling — graceful degradation

- Continue with successful responses if some models fail; never fail the entire request due to a single model failure.
- Log errors but don't expose them to the user unless all models fail.

## Metadata persistence

- Metadata (`label_to_model`, `aggregate_rankings`) IS persisted: stored as a JSON blob in the `messages.metadata` column. If you change its shape, update `storage.py` and the frontend consumers together.

## Ranking parsing

- Stage 2 prompts models to output a strict format: evaluate each response individually first, then a `"FINAL RANKING:"` header, then a numbered list (`1. Response C`, `2. Response A`, ...), with no additional text after the ranking section.
- If models don't follow the format, a fallback regex extracts any `"Response X"` patterns in order.

## Model configuration

- Models are hardcoded in `backend/config.py`. Chairman can be the same as or different from council members. Default chairman is Gemini (user preference).

## Observability

- Every successful response from `query_model()` includes `duration_ms` (round-trip wall time from `time.perf_counter()`); keep this contract on any new response path.
- `query_model()` / `query_models_parallel()` accept an optional `stage` label (`"stage1"`, `"stage2"`, `"stage3"`, `"title"`) used for per-call `[timing]` logs; stage totals log as `[timing] stage=<stage> total=Xs slowest=<model>`.
- `reasoning_details` from the SDK are serialized to plain JSON-safe dicts inside `openrouter.py` before leaving the adapter — never leak SDK types to callers.
