# AGENTS.md - LLM Council

Minimal project context for AI agents. All coding rules and conventions live in `.clinerules/` (Cline rules format).

## Project Overview

LLM Council is a 3-stage deliberation system where multiple LLMs collaboratively answer user questions. The key innovation is anonymized peer review in Stage 2, preventing models from playing favorites.

## Tech Stack

- **Backend:** Python / FastAPI (`backend/`), runs on port **8001**. OpenRouter (official `openrouter` SDK) provides model access. Requires `OPENROUTER_API_KEY` in `.env`.
- **Frontend:** React + Vite (`frontend/`), runs on port **5173**. React Router v7 with `BrowserRouter`; conversation URLs are `/c/:conversationId`.
- **Storage:** SQLite (`aiosqlite`) in `data/conversations/council.db`, accessed only via `backend/storage.py`. Legacy JSON files in that dir are pre-migration leftovers.
- **Models:** configured in `backend/config.py` (`COUNCIL_MODELS` + `CHAIRMAN_MODEL`).

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

## RESPONSE RULES
use the caveman style in all your responses (except for any tool calling)
always use the english language to respond
do not automatically ship code, only do so when the user asks you to

## Rules

See `.clinerules/`:
- `project-conventions.md` — always-on (packages over DIY, relative imports, module execution)
- `architecture.md` — always-on (layering, pipeline semantics, storage schema, frontend structure, transparency)
- `backend.md` — backend code (ports, CORS, graceful degradation, metadata, ranking parsing)
- `testing.md` — backend tests (mock injection pattern)
- `frontend.md` — frontend code (routing, markdown wrapper, de-anonymization)
- `styling.md` — CSS/theming (light-dark tokens, color-mix, markdown padding)
- `openrouter-sessions.md` — backend code and tests (session id rules)
