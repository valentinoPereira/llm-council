import { useState, useEffect } from 'react';
import './ThemeToggle.css';

const LABELS = { system: 'System', light: 'Light', dark: 'Dark' };
const ICONS  = { system: '🖥️',  light: '☀️',  dark: '🌙'  };

/**
 * Three-state theme toggle: System → Light → Dark → System.
 *
 * State is stored in localStorage["theme"] ("light" | "dark" | absent =
 * follow OS).  The :root[data-theme] attribute and color-scheme are
 * managed reactively so light-dark() values resolve correctly.
 */
export default function ThemeToggle() {
  const readMode = () => localStorage.getItem('theme') || 'system';
  const [mode, setMode] = useState(readMode);

  useEffect(() => {
    // Sync across tabs
    const onStorage = (e) => {
      if (e.key === 'theme') setMode(e.newValue || 'system');
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const cycle = () => {
    const next = mode === 'system' ? 'light' : mode === 'light' ? 'dark' : 'system';

    if (next === 'system') {
      localStorage.removeItem('theme');
      delete document.documentElement.dataset.theme;
    } else {
      localStorage.setItem('theme', next);
      document.documentElement.dataset.theme = next;
    }
    setMode(next);
  };

  return (
    <button
      className="theme-toggle"
      onClick={cycle}
      title={`Theme: ${LABELS[mode]} (click to cycle)`}
      aria-label={`Current theme: ${LABELS[mode]}`}
    >
      <span className="theme-toggle-icon">{ICONS[mode]}</span>
      <span className="theme-toggle-label">{LABELS[mode]}</span>
    </button>
  );
}