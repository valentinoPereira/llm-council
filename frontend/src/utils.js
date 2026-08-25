export function formatDuration(durationMs) {
  if (durationMs == null) return null;
  const secs = durationMs / 1000;
  return secs >= 1 ? `${secs.toFixed(1)}s` : `${Math.round(durationMs)}ms`;
}
