import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import './ThemeToggle.css';

const LABELS = { system: 'System', light: 'Light', dark: 'Dark' };

/**
 * Refined inline SVG icons (stroke-based, inherit currentColor) — no emoji.
 */
function ThemeIcon({ theme }) {
  const common = {
    width: 14,
    height: 14,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
  };

  if (theme === 'light') {
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    );
  }
  if (theme === 'dark') {
    return (
      <svg {...common}>
        <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  );
}

// System → Light → Dark → System (matches the previous three-state cycle).
const NEXT = { system: 'light', light: 'dark', dark: 'system' };

/**
 * Three-state theme toggle backed by `next-themes`.
 *
 * `next-themes` owns all persistence (localStorage key "theme"), OS-preference
 * listening (prefers-color-scheme), cross-tab sync, and the `data-theme`
 * attribute on <html>. This component just reads the active theme and cycles it.
 */
export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // `next-themes` resolves `theme` in an effect after first render, so we gate
  // the visible UI on mount to avoid a flash of the wrong label/icon. This is
  // the canonical next-themes mount-guard pattern (a one-shot external-system
  // sync), hence the targeted rule exception.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  // `theme` is undefined until next-themes resolves on mount; render a
  // same-shaped placeholder to avoid a flash of the wrong label/icon.
  if (!mounted) {
    return <button className="theme-toggle" aria-hidden disabled />;
  }

  const current = theme === 'light' || theme === 'dark' ? theme : 'system';

  return (
    <button
      className="theme-toggle"
      onClick={() => setTheme(NEXT[current])}
      title={`Theme: ${LABELS[current]} (click to cycle)`}
      aria-label={`Current theme: ${LABELS[current]}`}
    >
      <span className="theme-toggle-icon">
        <ThemeIcon theme={current} />
      </span>
      <span className="theme-toggle-label">{LABELS[current]}</span>
    </button>
  );
}