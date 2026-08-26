import { useEffect, useRef } from 'react'
import { Icon } from '../ui'
import { PriceTag } from './PriceTag'
import { VenueList } from './VenueList'

/**
 * "Where to eat", as a centred dialog opened by clicking a food card.
 *
 * This replaces a per-card "Where to eat" button that expanded a panel inside the
 * card. The panel was cheap to build but wrong for the content: a venue list is
 * eight rows of name, distance, confidence and three links, which inside a 300px
 * grid column wraps into a column twice the height of the card it hangs off, and
 * pushes every card below it down the page while you read it. A dialog gets the
 * width the list actually needs and leaves the grid where it was.
 *
 * It is mounted by FoodGrid, not by FoodCard, and that placement is load-bearing:
 * `.card:hover` sets `transform: translateY(-2px)` and `.anim-rise` animates
 * `transform`, and a transformed element becomes the containing block for its
 * `position: fixed` descendants. Rendered inside a card, this dialog would be
 * positioned against that card rather than against the viewport — and only while
 * hovered, which is the kind of bug that reproduces on a mouse and not on a
 * screenshot. Owning the state one level up also means one dialog at a time.
 *
 * `VenueList` is mounted here and nowhere else, so it keeps the property it was
 * written for: nothing is fetched until a dish is opened, and browsing all 155
 * cards costs zero venue requests.
 *
 * Keyboard handling is Escape-to-close plus focus moved to the close button, and
 * that is the honest description — it is not a focus trap. Tab from the last link
 * inside will walk out into the page behind. The full treatment needs a sentinel
 * pair or `inert` on the rest of the tree; what is here covers the common exit
 * and does not pretend to more.
 */
export function DishModal({ food, onClose }) {
  const closeRef = useRef(null)

  useEffect(() => {
    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)

    // The dialog scrolls its own body; letting the page scroll behind it means a
    // wheel gesture past the end of the list moves the grid instead.
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    closeRef.current?.focus()

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      document.body.style.overflow = previous
    }
  }, [onClose])

  return (
    // Backdrop click closes, but only a click that landed on the backdrop itself:
    // without the currentTarget test, releasing a drag that started inside the
    // panel would close the dialog you were reading.
    <div
      className="modal-backdrop"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dish-modal-title"
      >
        {/* A fixed id is safe because FoodGrid mounts at most one of these. */}
        <header className="modal__head">
          <div className="stack" style={{ gap: 4, flex: 1, minWidth: 0 }}>
            <span className="panel__hint">Where to eat</span>
            <h3 className="panel__title" id="dish-modal-title" style={{ fontSize: 17 }}>
              {food.name}
            </h3>
          </div>
          <button
            ref={closeRef}
            type="button"
            className="modal__close"
            onClick={onClose}
            aria-label="Close"
          >
            <Icon name="close" size={13} />
          </button>
        </header>

        <div className="modal__body">
          {/* Repeated from the card on purpose: what a dish costs is half of
              deciding where to eat it, and the card is behind a backdrop. */}
          <PriceTag price={food.price ?? null} />
          <VenueList dish={food.name} />
        </div>
      </div>
    </div>
  )
}
