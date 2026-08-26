/**
 * The price line on a food card.
 *
 * The formatted string comes from the server (`price.display`), not from
 * `Intl.NumberFormat` here. The server already decides the currency symbol, the
 * thousands separator and the rounding step a menu would actually use — and a
 * second formatter on this side would eventually round Rs 1,250 to Rs 1,300 in
 * the card while every other surface reading the same payload said Rs 1,250.
 *
 * `estimated` is always true today, and is still read from the payload rather
 * than assumed: the day a real observed price arrives, this stops claiming it is
 * an estimate without anyone having to remember to come back here.
 */
export function PriceTag({ price, size = 'md' }) {
  if (!price) return null

  const staleNote = price.stale
    ? `Estimated from a price table last updated ${price.as_of} (${price.age_days} days ago) — treat it as a rough guide, not today's menu.`
    : `Estimated from a price table dated ${price.as_of}.`

  const confidenceNote =
    price.confidence === 'low'
      ? ' This dish’s estimate is low-confidence: prices vary widely by venue.'
      : ''

  return (
    <div className={`price ${size === 'lg' ? 'price--lg' : ''}`}>
      <span className="price__amount mono">{price.display}</span>
      {price.unit ? <span className="price__unit">/ {price.unit}</span> : null}
      {price.estimated ? (
        <span
          className={`price__est ${price.stale ? 'price__est--stale' : ''}`}
          title={staleNote + confidenceNote}
        >
          {price.stale ? `est. ${price.as_of.slice(0, 4)}` : 'est.'}
        </span>
      ) : null}
    </div>
  )
}
