---
paths:
  - "frontend/**"
---

# Frontend Guidelines

## Routing

- URL is the source of truth — `useParams()` drives which chat is loaded, not local state.
- Routes: `/` (new chat / home) and `/c/:conversationId`.
- Production hosts must serve `index.html` for all `/c/*` paths (SPA fallback). Vite dev server handles this automatically.

## Rendering

- All ReactMarkdown components must be wrapped in `<div className="markdown-content">` for proper spacing. This class is defined globally in `index.css`.

## De-anonymization

- De-anonymization happens CLIENT-SIDE for display only — models always receive anonymous labels ("Response A", "Response B", ...). The backend creates the `label_to_model` mapping.

## Metadata

- Metadata comes from the backend stream and lives in the React Query cache for display (see `architecture.md` → Frontend structure).
