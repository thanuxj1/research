import { useState } from 'react'
import { Button, Chip, Icon } from '../ui'
import { DishImage } from './DishImage'
import { PriceTag } from './PriceTag'
import { ScoreBreakdown } from './ScoreBreakdown'
import { SpiceMeter } from './SpiceMeter'
import { WarningList } from './WarningList'

/** Tags already conveyed by a dedicated control elsewhere on the card. */
const REDUNDANT_TAGS = new Set(['drink', 'dessert', 'soup', 'condiment', 'vegan'])

/**
 * Things inside the card that a click should not be read as "open the dialog".
 *
 * The controls are obvious. `.breakdown` is the "Why?" panel: it has no controls
 * of its own, so without it here a click on the text you deliberately expanded to
 * read would pop a dialog over it.
 */
const NOT_A_CARD_CLICK = 'a, button, input, select, textarea, [role="button"], .breakdown'

/**
 * One dish in the grid.
 *
 * `onOpen` asks the parent to open the "where to eat" dialog for this dish, and
 * the whole card is its trigger — there used to be a "Where to eat" button in the
 * footer, and the card is a better target than a 90px button for the thing you
 * mostly want from a dish you have just spotted. The card itself cannot *be* the
 * button, though: an <article> with a click handler is invisible to a keyboard and
 * to a screen reader, and nesting a button around a photo, four chips, a price and
 * two other buttons is invalid HTML. So the title is a real <button> — that is the
 * documented, focusable trigger — and the card surface adds a mouse shortcut to
 * it, skipping any click that landed on a control with its own job.
 */
export function FoodCard({ food, index = 0, hasProfile, showScore, onOpen }) {
  const [open, setOpen] = useState(false)

  const isVeg = food.is_veg === 'True'
  const severity = food.health_severity
  const tags = (food.tags || []).filter((tag) => !REDUNDANT_TAGS.has(tag))
  const labels = food.tag_labels || []
  const price = food.price ?? null

  // The CSV's Low/Medium/High column and the numeric estimate are independent -
  // the server reports where they disagree instead of reconciling them - so the
  // band chip says which one it is speaking for when they differ.
  const bandNote =
    price && price.band_agrees === false
      ? `Dataset band: ${price.dataset_band ?? food.price_range}. The numeric estimate falls in the ${price.band} band.`
      : undefined

  // tag_labels is index-aligned with the sorted tags array from the API.
  const labelFor = (tag) => {
    const position = (food.tags || []).indexOf(tag)
    return position >= 0 && labels[position] ? labels[position] : tag.replace(/_/g, ' ')
  }

  // Anywhere on the card opens the dialog, except where something else already
  // owns the click - the title button (which would otherwise fire twice), "Why?",
  // and the score panel that button expands.
  const handleCardClick = (event) => {
    if (!onOpen) return
    if (event.target.closest(NOT_A_CARD_CLICK)) return
    onOpen(food)
  }

  return (
    <article
      className={[
        'card',
        'anim-rise',
        onOpen ? 'card--clickable' : '',
        severity === 'danger' ? 'card--danger' : '',
        severity === 'caution' ? 'card--caution' : '',
      ]
        .filter(Boolean)
        .join(' ')}
      style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}
      onClick={handleCardClick}
    >
      <DishImage name={food.name} eager={index < 4} />

      <header className="card__head">
        <h3 className="card__title">
          {onOpen ? (
            <button
              type="button"
              className="card__open"
              onClick={() => onOpen(food)}
              aria-haspopup="dialog"
              title={`Where to eat ${food.name}`}
            >
              {food.name}
            </button>
          ) : (
            food.name
          )}
        </h3>
        {showScore && typeof food.score === 'number' ? (
          <span className="card__score" title="Final ranking score">
            {food.score.toFixed(3)}
          </span>
        ) : null}
      </header>

      <div className="card__meta">
        <Chip variant={isVeg ? 'veg' : 'nonveg'}>
          {isVeg ? <Icon name="leaf" size={11} /> : null}
          {isVeg ? 'Veg' : 'Non-veg'}
        </Chip>
        <Chip>{food.category}</Chip>
        {food.meal_time && food.meal_time !== 'Any' ? <Chip>{food.meal_time}</Chip> : null}
        <Chip title={bandNote}>
          {food.price_range} price{bandNote ? ' *' : ''}
        </Chip>
      </div>

      <PriceTag price={price} />

      <p className="card__desc">{food.description}</p>

      <WarningList warnings={food.warnings} hasProfile={hasProfile} />

      {tags.length ? (
        <div className="card__meta">
          {tags.slice(0, 4).map((tag) => (
            <Chip key={tag} style={{ fontSize: 11, color: 'var(--text-3)' }}>
              {labelFor(tag)}
            </Chip>
          ))}
          {tags.length > 4 ? (
            <span style={{ fontSize: 11, color: 'var(--text-4)', alignSelf: 'center' }}>
              +{tags.length - 4}
            </span>
          ) : null}
        </div>
      ) : null}

      <footer className="card__foot">
        <SpiceMeter level={food.spicy_level} />
        {/* "Why?" is the only action left here now that the venue list has moved
            into the dialog, and most dishes arrive without an explanation, so the
            wrapper is conditional rather than an empty flex row. */}
        {food.explanation ? (
          <div className="card__actions">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
            >
              {open ? 'Hide' : 'Why?'}
            </Button>
          </div>
        ) : null}
      </footer>

      {open && food.explanation ? <ScoreBreakdown explanation={food.explanation} /> : null}
    </article>
  )
}
