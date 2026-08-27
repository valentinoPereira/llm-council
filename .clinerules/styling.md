---
paths:
  - "frontend/src/**/*.css"
  - "frontend/index.html"
---

# Styling Guidelines

## Theming

- Semantic tokens defined in `src/theme.css` via `:root { --bg-app: light-dark(#fff, #1e1f22); ... }`.
- `color-scheme: light dark` on `:root` makes `light-dark()` follow the OS by default.
- Manual toggle: `data-theme="light"|"dark"` on `<html>` pins `color-scheme`; absent = follow OS.
- Light values must be the original colors (pixel-identical in light mode); dark values tuned for readability.

## Colors

- Derived hovers use `color-mix(in oklch, ...)` instead of hardcoded hex.

## Markdown content

- 12px padding on all markdown content to prevent cluttered appearance.
- Global markdown styling lives in `index.css` with the `.markdown-content` class (uses nesting).

## Browser support

- `light-dark()` requires Safari ≥ 17.5 / Chrome ≥ 123 / Firefox ≥ 120.
