import { useEffect } from 'react'
import { api } from '../../api/client'
import { useResource } from '../../hooks/useResource'
import { Chip, ErrorState, Icon } from '../ui'
import { PriceTag } from './PriceTag'
import { SpiceMeter } from './SpiceMeter'
import { WarningList } from './WarningList'

/**
 * "More like this" drawer, backed by nearest neighbours in the embedding space
 * (`POST /similar`). This is the one place the dense index is queried directly,
 * with no lexical or constraint layer involved.
 *
 * NOT MOUNTED. The only thing that opened it was the "Similar" button on the food
 * card, which was removed, so nothing in the app renders this today. Kept rather
 * than deleted because the drawer and the endpoint behind it both still work —
 * re-attaching it needs one piece of state in `App.jsx` and one call site — and
 * because the same reasoning applies here as to the unused helpers in
 * `api/client.js`: an orphan that says it is an orphan is honest, while one that
 * stays silent gets read as live code. If it is still unmounted next time someone
 * touches this directory, delete it along with `api.similar`; the backend
 * `/similar` route is documented API and stays either way.
 */
export function SimilarDrawer({ dish, profile, onClose }) {
  const { data, loading, error } = useResource(
    (signal) =>
      api.similar(
        { name: dish.name, top_k: 8, health_conditions: profile.conditions },
        signal,
      ),
    [dish.name, profile.conditions.join(',')],
  )

  // Escape closes; body scroll is locked while open.
  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previous
    }
  }, [onClose])

  const hasProfile = profile.conditions.length > 0

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Dishes similar to ${dish.name}`}>
        <header className="drawer__head">
          <div className="stack" style={{ gap: 4, flex: 1 }}>
            <span className="panel__hint">Similar to</span>
            <h3 className="panel__title" style={{ fontSize: 17 }}>
              {dish.name}
            </h3>
          </div>
          <button type="button" className="drawer__close" onClick={onClose} aria-label="Close">
            <Icon name="close" size={13} />
          </button>
        </header>

        <div className="drawer__body">
          {error ? (
            <ErrorState error={error} />
          ) : loading ? (
            Array.from({ length: 5 }, (_, index) => (
              <div key={index} className="skeleton" style={{ height: 78, borderRadius: 10 }} />
            ))
          ) : (
            (data?.results ?? []).map((item) => (
              <div key={item.name} className="card" style={{ gap: 8 }}>
                <div className="card__head">
                  <h4 className="card__title" style={{ fontSize: 14 }}>
                    {item.name}
                  </h4>
                  <span className="card__score" title="Cosine similarity">
                    {typeof item.score === 'number' ? item.score.toFixed(3) : ''}
                  </span>
                </div>
                <div className="card__meta">
                  <Chip variant={item.is_veg === 'True' ? 'veg' : 'nonveg'}>
                    {item.is_veg === 'True' ? 'Veg' : 'Non-veg'}
                  </Chip>
                  <Chip>{item.category}</Chip>
                </div>
                <PriceTag price={item.price ?? null} />
                <p className="card__desc" style={{ WebkitLineClamp: 2, lineClamp: 2 }}>
                  {item.description}
                </p>
                <WarningList warnings={item.warnings} hasProfile={hasProfile} max={2} />
                <SpiceMeter level={item.spicy_level} />
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  )
}
