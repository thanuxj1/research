/**
 * Visualises the additive signal breakdown returned by `explain: true`.
 *
 * This view is only possible because scoring is additive. The previous pipeline
 * multiplied its penalties together, so a final score could not be decomposed
 * into named contributions at all — there was nothing to show.
 *
 * Bars are drawn from a centre line: contributions to the right add, to the left
 * subtract, and every bar shares one scale so their magnitudes are comparable.
 */
export function ScoreBreakdown({ explanation }) {
  if (!explanation?.signals?.length) return null

  const { signals, rerank_score: rerankScore, retrievers = [] } = explanation
  const peak = Math.max(...signals.map((s) => Math.abs(s.contribution)), 0.001)

  return (
    <div className="breakdown">
      <div
        className="row wrap"
        style={{ gap: 8, fontSize: 11, color: 'var(--text-4)', marginBottom: 2 }}
      >
        <span className="mono">relevance {explanation.relevance?.toFixed(3)}</span>
        {rerankScore != null ? (
          <span className="mono">· cross-encoder {rerankScore.toFixed(3)}</span>
        ) : null}
        {retrievers.length ? <span className="mono">· via {retrievers.join('+')}</span> : null}
      </div>

      {signals.map((signal, index) => {
        const magnitude = Math.abs(signal.contribution)
        const width = (magnitude / peak) * 50
        const negative = signal.contribution < 0
        return (
          <div className="breakdown__row" key={`${signal.name}-${index}`}>
            <span className="breakdown__name" title={signal.name}>
              {signal.name}
            </span>
            <span className="breakdown__track">
              <span
                className={`breakdown__fill ${negative ? 'breakdown__fill--negative' : ''}`}
                style={
                  negative
                    ? { right: '50%', width: `${width}%` }
                    : { left: '50%', width: `${width}%` }
                }
              />
            </span>
            <span
              className="breakdown__value"
              style={negative ? { color: 'var(--danger)' } : undefined}
            >
              {signal.contribution >= 0 ? '+' : ''}
              {signal.contribution.toFixed(3)}
            </span>
            {signal.detail ? <span className="breakdown__detail">{signal.detail}</span> : null}
          </div>
        )
      })}
    </div>
  )
}
