---
paths:
  - "frontend/**"
---

# Frontend Guidelines

## Routing

- URL is the source of truth — `useParams()` drives which chat is loaded, not local state.
- Routes: `/` (new chat / home) and `/c/:conversationId`.
- Production hosts must serve `index.html` for all `/c/*` paths (SPA fallback). The Vite dev server on port 5173 handles this automatically.

## Rendering

- All ReactMarkdown components must be wrapped in `<div className="markdown-content">` for proper spacing. The class is defined globally in `index.css` (12px padding, nested rules).

## De-anonymization

- De-anonymization happens CLIENT-SIDE for display only — models always receive anonymous labels ("Response A", "Response B", ...). The backend creates the `label_to_model` mapping.

## Styling and theming

- Theming is managed by **next-themes**: `ThemeProvider` in `src/main.jsx` with `attribute="data-theme"` and `enableColorScheme={false}` (theme.css owns `color-scheme`).
- Semantic tokens defined in `src/theme.css` via `:root { --bg-app: light-dark(#fff, #1e1f22); ... }`; `:root[data-theme="light"|"dark"]` overrides pin `color-scheme`.
- Theme changes go through next-themes (`setTheme` in `ThemeToggle.jsx`) — never set the `data-theme` attribute or localStorage manually.
- Light values must be the original colors (pixel-identical in light mode); dark values tuned for readability.
- Derived hovers use `color-mix(in oklch, ...)` instead of hardcoded hex.