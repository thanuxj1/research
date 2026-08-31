import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useResource } from '../../hooks/useResource'
import { Button, Notice, Select, Toggle } from '../ui'
import { FoodGrid } from '../food/FoodGrid'

const EMPTY_FORM = {
  category: '',
  is_veg: '',
  meal_time: '',
  spicy_level: '',
  price_range: '',
}

export function RecommendPanel({ profile }) {
  const [form, setForm] = useState(EMPTY_FORM)
  const [payload, setPayload] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [explain, setExplain] = useState(false)
  const requestRef = useRef(null)

  // Facet values (and their counts) come from the server, so the dropdowns can
  // never list a value the dataset does not contain.
  const { data: facets, error: facetsError } = useResource((signal) => api.facets(signal))

  const run = useCallback(async () => {
    requestRef.current?.abort()
    const controller = new AbortController()
    requestRef.current = controller

    setLoading(true)
    setError(null)

    const body = { top_k: 12, explain, health_conditions: profile.conditions, strict_allergens: profile.strict }
    Object.entries(form).forEach(([key, value]) => {
      if (value) body[key] = value
    })

    try {
      setPayload(await api.recommend(body, controller.signal))
    } catch (requestError) {
      if (requestError?.name === 'AbortError') return
      setError(requestError)
      setPayload(null)
    } finally {
      if (requestRef.current === controller) setLoading(false)
    }
  }, [form, explain, profile.conditions, profile.strict])

  useEffect(() => () => requestRef.current?.abort(), [])

  const hasProfile = profile.conditions.length > 0
  const engine = payload?.engine

  return (
    <section className="section">
      <div className="panel">
        <div className="stack" style={{ gap: 16 }}>
          <div className="stack" style={{ gap: 4 }}>
            <span className="panel__title">Preference filters</span>
            <span className="panel__hint">
              Scored by the XGBoost model blended with a deterministic preference match, so results
              stay sensible even if the model is unavailable.
            </span>
          </div>

          {facetsError ? (
            <Notice variant="warn" icon="alert">
              Could not load filter options — {facetsError.message}
            </Notice>
          ) : null}

          <div className="filters-grid">
            <Select
              id="rec-category"
              label="Category"
              value={form.category}
              onChange={(value) => setForm((f) => ({ ...f, category: value }))}
              options={facets?.categories ?? []}
            />
            <Select
              id="rec-diet"
              label="Diet"
              value={form.is_veg}
              onChange={(value) => setForm((f) => ({ ...f, is_veg: value }))}
              options={[
                { value: 'True', label: 'Vegetarian' },
                { value: 'False', label: 'Non-vegetarian' },
              ]}
            />
            <Select
              id="rec-meal"
              label="Meal time"
              value={form.meal_time}
              onChange={(value) => setForm((f) => ({ ...f, meal_time: value }))}
              options={facets?.meal_times ?? []}
            />
            <Select
              id="rec-spice"
              label="Spice level"
              value={form.spicy_level}
              onChange={(value) => setForm((f) => ({ ...f, spicy_level: value }))}
              options={facets?.spicy_levels ?? []}
            />
            <Select
              id="rec-price"
              label="Price range"
              value={form.price_range}
              onChange={(value) => setForm((f) => ({ ...f, price_range: value }))}
              options={facets?.price_ranges ?? []}
            />
          </div>

          <div className="row wrap" style={{ gap: 10 }}>
            <Button variant="primary" icon="spark" onClick={run} loading={loading} disabled={loading}>
              Recommend
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setForm(EMPTY_FORM)
                setPayload(null)
                setError(null)
              }}
            >
              Reset
            </Button>
            <span className="spacer" />
            <Toggle checked={explain} onChange={setExplain} label="Explain scores" />
          </div>
        </div>
      </div>

      {engine ? (
        <Notice variant={engine.model_loaded ? undefined : 'warn'} icon={engine.model_loaded ? 'info' : 'alert'}>
          {engine.model_loaded
            ? `Scoring mode: ${engine.mode} · ${engine.classes} dish classes`
            : `Model unavailable (${engine.error ?? 'unknown error'}) — falling back to rule-based scoring.`}
        </Notice>
      ) : null}

      {payload || loading || error ? (
        <FoodGrid
          foods={payload?.results}
          loading={loading}
          error={error}
          onRetry={run}
          hasProfile={hasProfile}
          emptyTitle="Nothing matched those preferences"
          emptyBody="Loosen one of the filters and try again."
        />
      ) : (
        <div className="state anim-fade">
          <p className="state__title">Pick your preferences</p>
          <p className="state__body">
            Leave a filter on “Any” to let the model decide. Every field is optional.
          </p>
        </div>
      )}
    </section>
  )
}
