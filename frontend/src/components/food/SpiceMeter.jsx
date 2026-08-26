const LEVELS = ['None', 'Low', 'Medium', 'High']

const LABELS = {
  None: 'No heat',
  Low: 'Mild',
  Medium: 'Medium',
  High: 'Hot',
  'Very High': 'Very hot',
}

/**
 * Four-segment spice indicator.
 *
 * The dataset only contains None/Low/Medium/High, so the meter has exactly four
 * segments rather than inventing a fifth for a "Very High" level nothing uses.
 */
export function SpiceMeter({ level }) {
  const index = LEVELS.indexOf(level)
  const filled = index < 0 ? 0 : index + 1
  const hot = level === 'High' || level === 'Very High'

  return (
    <span className="spice" title={`Spice level: ${level}`}>
      <span className="spice__bars">
        {LEVELS.map((_, position) => (
          <span
            key={position}
            className={[
              'spice__bar',
              position < filled ? 'spice__bar--on' : '',
              position < filled && hot ? 'spice__bar--hot' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          />
        ))}
      </span>
      <span className="spice__label">{LABELS[level] ?? level}</span>
    </span>
  )
}
