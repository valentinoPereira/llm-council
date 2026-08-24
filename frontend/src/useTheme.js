import { useEffect } from 'react';

/**
 * Standalone theme hook.
 *
 * Three modes:
 *   - "system" (default / after clicking toggle back to auto) – no
 *     data-theme attribute on <html>; :root { color-scheme: light dark }
 *     makes light-dark() follow the OS.
 *   - "light"  – data-theme="light";  color-scheme: light
 *   - "dark"   – data-theme="dark";   color-scheme: dark
 *
 * The stored value is only written when the user explicitly chooses;
 * on first load with nothing in localStorage we stay in "system" mode.
 */
export function useTheme() {
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');

    const applyStored = () => {
      const stored = localStorage.getItem('theme');
      if (stored === 'light' || stored === 'dark') {
        document.documentElement.dataset.theme = stored;
      } else {
        delete document.documentElement.dataset.theme; // follow OS
      }
    };

    applyStored();

    // If no explicit choice, follow live OS changes
    const onChange = () => {
      if (!localStorage.getItem('theme')) applyStored();
    };
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  const current = localStorage.getItem('theme') || 'system';

  const cycle = () => {
    const next =
      current === 'system' ? 'light' : current === 'light' ? 'dark' : 'system';

    if (next === 'system') {
      localStorage.removeItem('theme');
    } else {
      localStorage.setItem('theme', next);
    }
    // Re-apply immediately
    if (next === 'system') {
      delete document.documentElement.dataset.theme;
    } else {
      document.documentElement.dataset.theme = next;
    }
    // Force re-render in the component that called us via a storage event
    // (not needed – see ThemeToggle which handles its own state)
  };

  return { current, cycle };
}