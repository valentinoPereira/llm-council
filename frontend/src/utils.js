export function formatDuration(durationMs) {
  if (durationMs == null) return null;
  const secs = durationMs / 1000;
  return secs >= 1 ? `${secs.toFixed(1)}s` : `${Math.round(durationMs)}ms`;
}

/**
 * Human-friendly model name. Providers are stripped, slugs prettified, and
 * well-known fragments (providers/acronyms) cased for print rather than dev.
 *
 *   "moonshotai/kimi-k3"      → "Kimi K3"
 *   "openai/gpt-5.6-sol"     → "GPT-5.6 Sol"
 *   "google/gemini-3.7-flash"→ "Gemini 3.7 Flash"
 *   "anthropic/claude-opus-5"→ "Claude Opus 5"
 *   "z-ai/glm-5.3"           → "GLM 5.3"
 */
const ACRONYM_FRAGMENTS = new Set([
  'gpt', 'ai', 'glm', 'lstm', 'bert', 't5', 'ocr', 'api', 'ui', 'sdk',
]);

const KNOWN_RENAMES = {
  'kimi-k3': 'Kimi K3',
  'gpt-5.6-sol': 'GPT-5.6 Sol',
  'gemini-3.7-flash': 'Gemini 3.7 Flash',
  'claude-opus-5': 'Claude Opus 5',
  'glm-5.3': 'GLM 5.3',
  'grok-4.6': 'Grok 4.6',
};

export function displayModelName(model) {
  if (!model) return '';
  const slug = model.split('/').pop() || model;
  if (KNOWN_RENAMES[slug]) return KNOWN_RENAMES[slug];

  return slug
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      if (ACRONYM_FRAGMENTS.has(lower)) return lower.toUpperCase();
      return part.charAt(0).toUpperCase() + part.slice(1);
    })
    .join(' ');
}

/**
 * Compact relative time for sidebar meta — no clock math the reader must do.
 * "Just now" < “<1m” < “5m ago” < “3h ago” < “Yesterday” < “12 Mar”.
 */
export function formatRelativeTime(iso) {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const diffMs = Date.now() - date.getTime();
  const secs = Math.floor(diffMs / 1000);
  if (secs < 60) return 'Just now';

  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;

  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;

  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
  });
}
