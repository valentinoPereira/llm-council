---
paths:
  - "frontend/src/**/*.css"
  - "frontend/index.html"
---

# Styling Guidelines

## Theming

- Theming is managed by **next-themes**: `ThemeProvider` in `src/main.jsx` with `attribute="data-theme"` and `enableColorScheme={false}` (theme.css owns `color-scheme`).
- Semantic tokens defined in `src/theme.css` via `:root { --bg-app: light-dark(#fff, #1e1f22); ... }`; `:root[data-theme="light"|"dark"]` overrides pin `color-scheme`.
- Theme changes go through next-themes (`setTheme` in `ThemeToggle.jsx`) — never set the `data-theme` attribute or localStorage manually.
- Light values must be the original colors (pixel-identical in light mode); dark values tuned for readability.

## Colors

- Derived hovers use `color-mix(in oklch, ...)` instead of hardcoded hex.

## Markdown content

- 12px padding on all markdown content to prevent cluttered appearance.
- Global markdown styling lives in `index.css` with the `.markdown-content` class (uses nesting).

## Browser support

- `light-dark()` requires Safari ≥ 17.5 / Chrome ≥ 123 / Firefox ≥ 120.
