# AGENTS.md - LLM Council

Minimal project context for AI agents. All coding rules and conventions live in `.clinerules/` (Cline rules format).

## Project Overview

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

## RESPONSE RULES
- use the caveman style in all your responses (except for any tool calling)
- always use the english language to respond
- do not automatically ship code, only do so when the user asks you to
- when responding in plan mode, always remember that the implementation is going to be done by a smaller model, hence you should provide as much detail as possible while keeping the plan robust
- always use powershell compatible commands for your `run_commands` tool
