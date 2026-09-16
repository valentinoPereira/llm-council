import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api';
import './RankingsModal.css';

const MEDALS = ['🥇', '🥈', '🥉', '4'];

function displayModel(model) {
  // Strip provider prefix for readability: "moonshotai/kimi-k3" → "kimi-k3".
  const id = model.split('/').pop();
  return id.startsWith('@preset/') ? id.slice('@preset/'.length) : id;
}

/**
 * Top-N council leaderboard, fetched on open via React Query.
 */
function useRankings(top) {
  return useQuery({
    queryKey: ['rankings', top],
    queryFn: () => api.getRankings(top),
    enabled: top > 0,
    staleTime: 60_000,
  });
}

/**
 * Themed modal showing the top council models by peer-review win rate.
 *
 * Winner determination (see backend /api/rankings): a model "wins" a message
 * when it tops that message's aggregate ranking (ties count as wins for
 * every co-leader); dummy/test runs are excluded. Average rank is
 * intentionally NOT shown here. This component is presentational; state
 * lives in the parent (open/close) and React Query (data).
 */
export default function RankingsModal({ top = 4, onClose }) {
  const { data, isLoading, isError } = useRankings(top);

  // Close on Escape — standard modal affordance (accessibility).
  useEffect(() => {
    if (!onClose) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="rankings-backdrop" onClick={onClose} aria-hidden="true">
      <div
        className="rankings-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Council rankings by peer-review win rate"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="rankings-header">
          <div className="rankings-title-group">
            <h2 className="rankings-title">Council Rankings</h2>
            <p className="rankings-subtitle">
              Top {top} models — share of peer-review wins
            </p>
          </div>
          <button
            type="button"
            className="rankings-close-btn"
            onClick={onClose}
            aria-label="Close rankings"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <div className="rankings-body">
          {isLoading ? (
            <div className="rankings-placeholder">Summoning the tally…</div>
          ) : isError ? (
            <div className="rankings-placeholder rankings-error">
              Failed to load rankings
            </div>
          ) : !data?.length ? (
            <div className="rankings-placeholder">
              No council runs recorded yet
            </div>
          ) : (
            <ol className="rankings-list">
              {data.map((entry, index) => (
                <li key={entry.model} className="rankings-row">
                  <span className="rankings-medal" aria-hidden="true">
                    {MEDALS[index] ?? index + 1}
                  </span>
                  <span
                    className="rankings-name"
                    title={`${entry.wins} of ${entry.appearances} council runs won`}
                  >
                    {displayModel(entry.model)}
                  </span>
                  <span className="rankings-rate">
                    {(entry.share * 100).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}
