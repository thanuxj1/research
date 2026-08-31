import { useState } from 'react'
import { dishImageFile } from '../../lib/dishImage'

/**
 * The photo at the top of a food card.
 *
 * Fixed aspect box, `object-fit: cover`. The set is not uniform — 52 of the 155
 * files are 16:9, 51 are 3:2, 8 are 4:3, across 53 distinct pixel sizes — so
 * letting each image set its own height would give the grid ragged rows and a
 * visible reflow as each one arrives. The box is 16:9 because that is both the
 * commonest native ratio here (nothing is upscaled to fill it) and the shortest,
 * which matters on a card that already carries chips, a price, three lines of
 * description, warnings and tags.
 *
 * A 3:2 box was measured against this one and comes out level on how much of the
 * set it crops - it trades a 16% width crop on 52 files for a 16% height crop on
 * 51 - so density decided it. 66 files are not cropped at all; the two square
 * photos (`mango-chutney`, `chicken-patties`) lose 44% of their height and are the
 * ones to re-shoot first if any look wrong. The crop is centred, which is where
 * the food is in all of these.
 *
 * `alt` is empty on purpose. The photo says nothing the `<h3>` beside it does not
 * already say, so a screen reader announcing "Chicken Kottu" twice would be pure
 * noise; an empty alt is how you say "decorative here" rather than "unlabelled".
 *
 * No `width`/`height` attributes: they exist to reserve space before the image
 * loads, and the container's `aspect-ratio` already does that for every card at
 * once. Adding per-file intrinsic sizes would mean shipping a 155-entry
 * dimensions table to prevent a layout shift that cannot happen.
 *
 * The fallback tile is not decoration either. `npm run verify` fails the build if
 * any dish lacks a file, so a miss here means a deploy that dropped the
 * directory — and in that case an empty box of the right height keeps the grid
 * intact, where a broken-image icon would break every row's alignment.
 */
export function DishImage({ name, eager = false }) {
  const [failed, setFailed] = useState(false)

  // Vite rewrites BASE_URL at build time; it is undefined outside a Vite build
  // (the server-render harness), and a site served from the root gets '/'.
  const base = import.meta.env.BASE_URL || '/'

  if (failed) {
    return (
      <div className="card__media card__media--empty" aria-hidden="true">
        <span className="card__monogram">{monogram(name)}</span>
      </div>
    )
  }

  return (
    <div className="card__media">
      <img
        className="card__img"
        src={`${base}${dishImageFile(name)}`}
        alt=""
        // The first row is above the fold, and lazy images are invisible to the
        // preload scanner, so deferring them delays the largest paint on the
        // page. Four is an estimate of one row, not a measurement: the grid is
        // `auto-fill`, so the real count depends on the viewport.
        loading={eager ? 'eager' : 'lazy'}
        decoding="async"
        onError={() => setFailed(true)}
      />
    </div>
  )
}

/** Up to two initials, for the tile shown when a file is missing. */
function monogram(name) {
  return String(name)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0].toUpperCase())
    .join('')
}
