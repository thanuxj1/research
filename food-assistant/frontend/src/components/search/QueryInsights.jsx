import { Chip, Icon } from '../ui'

const SPICE_NAMES = ['None', 'Low', 'Medium', 'High', 'Very High']

const spiceName = (rank) => SPICE_NAMES[rank] ?? String(rank)
const priceName = (rank) => ['Low', 'Medium', 'High'][rank] ?? String(rank)
const humanTag = (tag) => tag.replace(/_/g, ' ')

/**
 * Renders the `understanding`, `filters` and `pipeline` blocks from /search.
 *
 * This exists to make the retrieval pipeline legible instead of magical. The
 * user can see that "I don't want seafood" was parsed as an *exclusion*, that a
 * typo was corrected, which constraints became hard filters, and which stages
 * ran — including when the cross-encoder was skipped, so a silent quality
 * downgrade is visible rather than hidden.
 */
export function QueryInsights({ understanding, filters, pipeline, tookMs, cached, total }) {
  if (!understanding) return null

  const {
    constraints = {},
    corrections = [],
    negated_terms: negated = [],
    budget = [],
  } = understanding

  const positive = []
  if (constraints.diet) {
    positive.push(constraints.diet === 'veg' ? 'vegetarian' : 'non-vegetarian')
  }
  if (constraints.spice_ceiling != null && constraints.spice_floor != null) {
    positive.push(
      constraints.spice_ceiling === constraints.spice_floor
        ? `spice ${spiceName(constraints.spice_floor)}`
        : `spice ${spiceName(constraints.spice_floor)}–${spiceName(constraints.spice_ceiling)}`,
    )
  } else if (constraints.spice_ceiling != null) {
    positive.push(`spice ≤ ${spiceName(constraints.spice_ceiling)}`)
  } else if (constraints.spice_floor != null) {
    positive.push(`spice ≥ ${spiceName(constraints.spice_floor)}`)
  }
  if (constraints.price_ceiling != null) positive.push(`price ≤ ${priceName(constraints.price_ceiling)}`)
  if (constraints.price_floor != null) positive.push(`price ≥ ${priceName(constraints.price_floor)}`)
  // Rupee amounts come back pre-worded from the server ("up to Rs 1,500") rather
  // than being reassembled here, so the phrasing the parser committed to is the
  // phrasing on screen. Showing this is not decoration: a budget is a soft
  // signal that reweights every result, so a misread amount reshapes the whole
  // page with nothing else on it to say so.
  ;(budget || []).forEach((mention) => positive.push(mention))
  ;(constraints.meal_times || []).forEach((meal) => positive.push(meal.toLowerCase()))
  ;(constraints.categories_include || []).forEach((category) => positive.push(category))
  ;(constraints.tags_include || []).forEach((tag) => positive.push(humanTag(tag)))

  const excluded = [
    ...(constraints.categories_exclude || []),
    ...(constraints.tags_exclude || []).map(humanTag),
  ]

  const hasAnything =
    positive.length || excluded.length || corrections.length || (filters?.applied?.length ?? 0)

  if (!hasAnything && !pipeline) return null

  return (
    <div className="insights anim-fade">
      {corrections.length ? (
        <div className="insights__row">
          <span className="insights__key">Corrected</span>
          <span className="correction">
            {corrections.map((correction, index) => (
              <span key={`${correction.from}-${index}`}>
                {index > 0 ? ', ' : ''}
                <s>{correction.from}</s> → <strong>{correction.to}</strong>
              </span>
            ))}
          </span>
        </div>
      ) : null}

      {positive.length ? (
        <div className="insights__row">
          <span className="insights__key">Understood</span>
          <span className="insights__values">
            {positive.map((item) => (
              <Chip key={item}>{item}</Chip>
            ))}
          </span>
        </div>
      ) : null}

      {excluded.length ? (
        <div className="insights__row">
          <span className="insights__key">Excluded</span>
          <span className="insights__values">
            {excluded.map((item) => (
              <Chip key={item} variant="negated">
                {item}
              </Chip>
            ))}
          </span>
        </div>
      ) : null}

      {negated.length && !excluded.length ? (
        <div className="insights__row">
          <span className="insights__key">Negated</span>
          <span className="insights__values">
            {negated.map((term) => (
              <Chip key={term} variant="negated">
                {term}
              </Chip>
            ))}
          </span>
        </div>
      ) : null}

      {filters?.applied?.length ? (
        <div className="insights__row">
          <span className="insights__key">Filters</span>
          <span className="insights__values">
            {filters.applied.map((filter) => (
              <Chip key={filter}>
                <Icon name="filter" size={10} />
                {filter}
              </Chip>
            ))}
            {filters.removed ? (
              <span style={{ fontSize: 11.5, color: 'var(--text-4)', alignSelf: 'center' }}>
                {filters.removed} dishes removed
              </span>
            ) : null}
          </span>
        </div>
      ) : null}

      {filters?.relaxed?.length ? (
        <div className="insights__row">
          <span className="insights__key">Relaxed</span>
          <span className="insights__values">
            {filters.relaxed.map((item) => (
              <Chip key={item} style={{ color: 'var(--warn)', borderColor: 'var(--warn-dim)' }}>
                {item}
              </Chip>
            ))}
          </span>
        </div>
      ) : null}

      {pipeline?.stages?.length ? (
        <div className="insights__row">
          <span className="insights__key">Pipeline</span>
          <span className="insights__pipeline">
            {pipeline.stages.map((stage, index) => (
              <span key={stage} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                {index > 0 ? <span className="insights__arrow">→</span> : null}
                <span
                  className={[
                    'insights__stage',
                    stage.endsWith('_skipped') ? 'insights__stage--skipped' : '',
                    stage === 'cross_encoder_rerank' ? 'insights__stage--active' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                >
                  {stage.replace(/_/g, ' ')}
                </span>
              </span>
            ))}
          </span>
        </div>
      ) : null}

      <div
        className="row wrap mono"
        style={{ gap: 10, fontSize: 11, color: 'var(--text-4)' }}
      >
        {typeof total === 'number' ? <span>{total} results</span> : null}
        {typeof tookMs === 'number' ? <span>· {tookMs} ms</span> : null}
        {cached ? <span>· cached</span> : null}
        {pipeline?.dense_backend ? <span>· dense: {pipeline.dense_backend}</span> : null}
        {pipeline && !pipeline.reranked ? (
          <span style={{ color: 'var(--warn)' }}>
            · reranker unavailable{pipeline.rerank_unavailable_reason ? ' (see /health)' : ''}
          </span>
        ) : null}
      </div>
    </div>
  )
}
