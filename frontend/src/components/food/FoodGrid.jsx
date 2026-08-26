import { useState } from 'react'
import { EmptyState, ErrorState } from '../ui'
import { DishModal } from './DishModal'
import { FoodCard } from './FoodCard'

function SkeletonCard() {
  return (
    <div className="card" aria-hidden="true">
      {/* Same aspect box the real photo lands in, so the grid does not jump by
          the height of an image when results arrive. */}
      <div className="card__media">
        <div className="skeleton" style={{ width: '100%', height: '100%' }} />
      </div>
      <div className="skeleton" style={{ height: 17, width: '62%' }} />
      <div className="row" style={{ gap: 6 }}>
        <div className="skeleton" style={{ height: 20, width: 54, borderRadius: 999 }} />
        <div className="skeleton" style={{ height: 20, width: 74, borderRadius: 999 }} />
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <div className="skeleton" style={{ height: 11 }} />
        <div className="skeleton" style={{ height: 11 }} />
        <div className="skeleton" style={{ height: 11, width: '72%' }} />
      </div>
      <div className="skeleton" style={{ height: 14, width: 110, marginTop: 'auto' }} />
    </div>
  )
}

/**
 * The results grid, and the owner of the "where to eat" dialog.
 *
 * The dialog's state lives here rather than in FoodCard for two reasons. The hard
 * one is CSS: `.card:hover` and `.anim-rise` both set a `transform`, and a
 * transformed element is the containing block for `position: fixed` descendants,
 * so a dialog rendered inside a card would be laid out against the card. The soft
 * one is that one piece of state here means exactly one dialog can be open, which
 * is what a modal claims when it says `aria-modal`.
 */
export function FoodGrid({
  foods,
  loading,
  error,
  onRetry,
  hasProfile,
  showScore = true,
  skeletonCount = 8,
  emptyTitle = 'No matches',
  emptyBody,
}) {
  // Declared above the early returns: hooks have to run in the same order on
  // every render, and `loading` flipping to false must not change the count.
  const [venueDish, setVenueDish] = useState(null)

  if (loading) {
    return (
      <div className="grid">
        {Array.from({ length: skeletonCount }, (_, index) => (
          <SkeletonCard key={index} />
        ))}
      </div>
    )
  }

  if (error) return <ErrorState error={error} onRetry={onRetry} />

  if (!foods) return null

  if (foods.length === 0) {
    return <EmptyState title={emptyTitle} body={emptyBody} />
  }

  return (
    <>
      <div className="grid">
        {foods.map((food, index) => (
          <FoodCard
            key={`${food.name}-${index}`}
            food={food}
            index={index}
            hasProfile={hasProfile}
            showScore={showScore}
            onOpen={(dish) => setVenueDish(dish)}
          />
        ))}
      </div>

      {venueDish ? (
        <DishModal food={venueDish} onClose={() => setVenueDish(null)} />
      ) : null}
    </>
  )
}
