# Project Conventions

Always-on rules for this repository.

## Packages over DIY

Prefer established libraries (react-router-dom, zustand, etc.) over hand-rolled hooks/utils. Custom hooks are fine when wrapping library primitives or composing app-specific state; reach for a package the moment the DIY version would reimplement a known wheel.

## Python imports and execution

- All backend modules use relative imports (e.g., `from .config import ...`), never absolute imports. This is critical for Python's module system.
- Always run the backend as `python -m backend.main` from the project root, never from the `backend/` directory.

