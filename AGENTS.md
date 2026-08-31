# AGENTS.md — LLM Council

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Data Flow

```
User Query
    ↓
Stage 1: Parallel queries → [individual responses]
    ↓
Stage 2: Anonymize → Parallel ranking queries → [evaluations + parsed rankings]
    ↓
Aggregate Rankings Calculation → [sorted by avg position]
    ↓
Stage 3: Chairman synthesis with full context
    ↓
Return: {stage1, stage2, stage3, metadata}
    ↓
Frontend: Display with tabs + validation UI
```

The entire flow is async/parallel where possible to minimize latency.

## Hard rules (always apply)

- Backend runs on **port 8001** — NOT 8000 (user has another app on 8000). Frontend dev server: port 5173. If ports change, update both `backend/main.py` and `frontend/src/api.js`.
- Model access goes **only** through `backend/openrouter.py`. The 3-stage pipeline lives **only** in `backend/council.py`. Storage logic lives **only** in `backend/storage.py`. Model identifiers live **only** in `backend/config.py`. FastAPI endpoints live in `backend/main.py` and must not re-implement stage logic.
- One conversation = one OpenRouter session; the deterministic session id (`llm-council-<conversation_id>`) must be passed to every model call in that conversation.
- A single model failure must never abort the pipeline — continue with the responses that succeeded.
- Stage 2 must always anonymize responses ("Response A", "Response B", ...) before sending them to models. De-anonymization happens client-side for display only.
- All backend modules use relative imports (`from .config import ...`), never absolute imports.
- Always run the backend as `python -m backend.main` from the project root, never from the `backend/` directory.
- Prefer established libraries over hand-rolled hooks/utils — current stack: react-router-dom, @tanstack/react-query, next-themes. Custom hooks are fine when wrapping library primitives or composing app-specific state; reach for a package the moment the DIY version would reimplement a known wheel.

## Scoped rules (read before working in these areas)

- Before editing anything in `backend/` or `tests/`: read `.rules/backend.md`.
- Before editing anything in `frontend/`: read `.rules/frontend.md`.
