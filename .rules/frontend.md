# Frontend Rules (frontend/)

## Routing

- URL is the source of truth — `useParams()` drives which chat is loaded, not local state.
- Routes: `/` (new chat / home) and `/c/:conversationId`.
- Production hosts must serve `index.html` for all `/c/*` paths (SPA fallback). The Vite dev server on port 5173 handles this automatically.

## Structure

- React Router v7: `<BrowserRouter>` in `src/main.jsx` (wrapped in `next-themes` ThemeProvider); only two routes exist: `/` (new chat / home) and `/c/:conversationId`, defined in `App.jsx`.
- Server state is owned by **@tanstack/react-query**: `useConversations` / `useConversation` / `useSendMessage` live in `App.jsx` and update the query cache (`setQueryData`) — don't duplicate fetch/state logic in components.
- The SSE streaming loop (optimistic assistant message + `api.sendMessageStream` events) lives in `useSendMessage()` in `App.jsx`; don't duplicate it elsewhere.
- `ChatRoute`/`HomeRoute` are internal components of `App.jsx` handling route-specific behavior (fetch + 404 redirect; submit-then-navigate with `replace: true`).
- Stage display stays in `Stage1.jsx` / `Stage2.jsx` / `Stage3.jsx` as tabbed, presentational components.

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

## Transparency requirement

- All raw model outputs must remain inspectable in the UI (tab views), and parsed rankings must be shown below the raw evaluation text so users can validate parsing. Never display only the parsed/synthesized result.
