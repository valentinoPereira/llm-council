import * as Tabs from '@radix-ui/react-tabs';
import Markdown from './Markdown';
import { formatDuration } from '../utils';
import './Stage2.css';

function deAnonymizeText(text, labelToModel) {
  if (!labelToModel) return text;

  let result = text;
  // Replace each "Response X" with the actual model name
  Object.entries(labelToModel).forEach(([label, model]) => {
    const modelShortName = model.split('/')[1] || model;
    result = result.replace(new RegExp(label, 'g'), `**${modelShortName}**`);
  });
  return result;
}

export default function Stage2({ rankings, labelToModel, aggregateRankings }) {
  if (!rankings || rankings.length === 0) {
    return null;
  }

  return (
    <div className="stage stage2">
      <div className="stage-header">
        <span className="stage-numeral">II</span>
        <div className="stage-heading">
          <h3 className="stage-title">Peer Review</h3>
          <span className="stage-subtitle">
            Anonymized evaluation &amp; ranking
          </span>
        </div>
      </div>

      <h4>Raw Evaluations</h4>
      <p className="stage-description">
        Each member evaluated every response under anonymous labels
        (Response A, B, C, …) and returned a ranking. Model names are shown in{' '}
        <strong>bold</strong> below for readability; the evaluations themselves
        were conducted blind.
      </p>

      <Tabs.Root defaultValue="tab-0" orientation="horizontal">
        <Tabs.List className="tabs">
          {rankings.map((rank, index) => (
            <Tabs.Trigger
              key={index}
              value={`tab-${index}`}
              className="tab"
            >
              {rank.model.split('/')[1] || rank.model}
              {rank.duration_ms != null && (
                <span className="duration-badge">{formatDuration(rank.duration_ms)}</span>
              )}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {rankings.map((rank, index) => (
          <Tabs.Content key={index} value={`tab-${index}`} className="tab-content">
            <div className="ranking-model">
              {rank.model}
              {rank.duration_ms != null && (
                <span className="duration-detail">
                  {formatDuration(rank.duration_ms)}
                </span>
              )}
            </div>
            <div className="ranking-content markdown-content">
              <Markdown>
                {deAnonymizeText(rank.ranking, labelToModel)}
              </Markdown>
            </div>

            {rank.parsed_ranking &&
             rank.parsed_ranking.length > 0 && (
              <div className="parsed-ranking">
                <strong>Extracted Ranking:</strong>
                <ol>
                  {rank.parsed_ranking.map((label, i) => (
                    <li key={i}>
                      {labelToModel && labelToModel[label]
                        ? labelToModel[label].split('/')[1] || labelToModel[label]
                        : label}
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </Tabs.Content>
        ))}
      </Tabs.Root>

      {aggregateRankings && aggregateRankings.length > 0 && (
        <div className="aggregate-rankings">
          <h4>Council Consensus</h4>
          <p className="stage-description">
            Standing across all peer evaluations — lower average position is
            stronger:
          </p>
          <div className="aggregate-list">
            {aggregateRankings.map((agg, index) => (
              <div key={index} className="aggregate-item">
                <span className="rank-position">#{index + 1}</span>
                <span className="rank-model">
                  {agg.model.split('/')[1] || agg.model}
                </span>
                <span className="rank-score">
                  Avg: {agg.average_rank.toFixed(2)}
                </span>
                <span className="rank-count">
                  ({agg.rankings_count} votes)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
