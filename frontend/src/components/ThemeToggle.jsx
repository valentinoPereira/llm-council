import { useEffect, useState } from 'react';
import { useTheme } from 'next-themes';
import './ThemeToggle.css';

const LABELS = { system: 'System', light: 'Light', dark: 'Dark' };
const ICONS  = { system: '🖥️',  light: '☀️',  dark: '🌙'  };

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
      <span className="theme-toggle-icon">{ICONS[current]}</span>
      <span className="theme-toggle-label">{LABELS[current]}</span>
    </button>
  );
}