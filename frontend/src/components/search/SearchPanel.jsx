import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { EXAMPLE_QUERIES } from '../../constants/examples'
import { Chip, Notice, Toggle } from '../ui'
import { FoodGrid } from '../food/FoodGrid'
import { QueryInsights } from './QueryInsights'
import { SearchBar } from './SearchBar'

/**
 * The search tab.
 *
 * Before the first query this renders the controls and nothing else. It used to
 * render a dashed placeholder box below them — a title, a paragraph explaining
 * that natural language works, and a "Try an example" button — which was removed
 * on request. Two things make the removal safe rather than merely smaller: the
 * example chips directly above are the same invitation in a form you can act on
 * with one click, and that button ran `EXAMPLE_QUERIES[0]`, which is literally
 * the first of those chips. The placeholder was restating its neighbours.
 */
export function SearchPanel({ profile }) {
  const [text, setText] = useState('')
  const [submitted, setSubmitted] = useState('')
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [explain, setExplain] = useState(false)
  const [rerank, setRerank] = useState(true)
  const [diversify, setDiversify] = useState(true)

  // Tracks the in-flight request so a slower earlier response cannot overwrite a
  // newer one.
  const requestRef = useRef(null)

  const run = useCallback(
    async (query) => {
      const trimmed = query.trim()
      if (!trimmed) return

      requestRef.current?.abort()
      const controller = new AbortController()
      requestRef.current = controller

      setSubmitted(trimmed)
      setLoading(true)
      setError(null)

      try {
        const result = await api.search(
          {
            query: trimmed,
            top_k: 12,
            health_conditions: profile.conditions,
            strict_allergens: profile.strict,
            explain,
            rerank,
            diversify,
          },
          controller.signal,
        )
        setPayload(result)
      } catch (requestError) {
        if (requestError?.name === 'AbortError') return
        setError(requestError)
        setPayload(null)
      } finally {
        if (requestRef.current === controller) setLoading(false)
      }
    },
    [profile.conditions, profile.strict, explain, rerank, diversify],
  )

  // Re-run the last query when an option or the health profile changes, so the
  // results on screen always match the controls.
  useEffect(() => {
    if (submitted) run(submitted)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [explain, rerank, diversify, profile.conditions, profile.strict])

  useEffect(() => () => requestRef.current?.abort(), [])

  const hasProfile = profile.conditions.length > 0

  return (
    <section className="section">
      <div className="stack" style={{ gap: 14 }}>
        <SearchBar
          value={text}
          onChange={setText}
          onSubmit={run}
          loading={loading}
          placeholder="Ask in plain English — e.g. mild vegetarian breakfast without coconut"
        />

        <div className="row wrap" style={{ gap: 6 }}>
          {EXAMPLE_QUERIES.map((example) => (
            <Chip
              key={example}
              as="button"
              onClick={() => {
                setText(example)
                run(example)
              }}
            >
              {example}
            </Chip>
          ))}
        </div>

        <div className="row wrap" style={{ gap: 18 }}>
          <Toggle checked={explain} onChange={setExplain} label="Explain scores" />
          <Toggle checked={rerank} onChange={setRerank} label="Cross-encoder rerank" />
          <Toggle checked={diversify} onChange={setDiversify} label="Diversify (MMR)" />
        </div>
      </div>

      {hasProfile ? (
        <Notice variant="info" icon="shield">
          {`Health profile active — ${profile.conditions.length} condition${
            profile.conditions.length > 1 ? 's' : ''
          } monitored. ${
            profile.strict
              ? 'Unsafe dishes are removed entirely.'
              : 'Conflicting dishes are flagged and ranked lower.'
          }`}
        </Notice>
      ) : null}

      {payload ? (
        <QueryInsights
          understanding={payload.understanding}
          filters={payload.filters}
          pipeline={payload.pipeline}
          tookMs={payload.took_ms}
          cached={payload.cached}
          total={payload.total}
        />
      ) : null}

      {payload?.message ? <Notice variant="warn" icon="alert">{payload.message}</Notice> : null}

      {submitted || loading || error ? (
        <FoodGrid
          foods={payload?.results}
          loading={loading}
          error={error}
          onRetry={() => run(submitted)}
          hasProfile={hasProfile}
          skeletonCount={8}
          emptyTitle="No dishes matched"
          emptyBody="Try removing a constraint, or check the detected filters above — one of them may be narrower than you intended."
        />
      ) : null}
    </section>
  )
}
