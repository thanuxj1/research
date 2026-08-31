import { Icon } from '../ui/Icon'

/**
 * Renders warnings exactly as the API returned them.
 *
 * No client-side rule evaluation happens anywhere in this app. The previous
 * version reimplemented the whole rule set in the browser, so the UI and the API
 * could — and did — disagree about whether a dish was safe.
 */
export function WarningList({ warnings = [], hasProfile, max = 3 }) {
  if (!hasProfile) return null

  if (warnings.length === 0) {
    return (
      <div className="warning warning--safe">
        <Icon name="check" size={13} className="warning__icon" />
        <span>No conflicts with your health profile</span>
      </div>
    )
  }

  const shown = warnings.slice(0, max)
  const hidden = warnings.length - shown.length

  return (
    <div className="stack" style={{ gap: 5 }}>
      {shown.map((warning, index) => (
        <div
          key={`${warning.condition}-${index}`}
          className={`warning warning--${warning.severity === 'danger' ? 'danger' : 'caution'}`}
        >
          <Icon name="alert" size={13} className="warning__icon" />
          <span>
            {warning.message}
            {warning.condition_label ? (
              <span className="warning__condition"> · {warning.condition_label}</span>
            ) : null}
          </span>
        </div>
      ))}
      {hidden > 0 ? (
        <span style={{ fontSize: 11, color: 'var(--text-4)', paddingLeft: 2 }}>
          +{hidden} more warning{hidden > 1 ? 's' : ''}
        </span>
      ) : null}
    </div>
  )
}
