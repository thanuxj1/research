import { Icon } from './Icon'

/* -------------------------------------------------------------------------- */
/* Button                                                                     */
/* -------------------------------------------------------------------------- */
export function Button({
  variant = 'secondary',
  size,
  block,
  icon,
  loading,
  children,
  className = '',
  ...rest
}) {
  const classes = [
    'btn',
    `btn--${variant}`,
    size === 'sm' ? 'btn--sm' : '',
    block ? 'btn--block' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button className={classes} {...rest}>
      {loading ? <span className="spinner" /> : icon ? <Icon name={icon} size={14} /> : null}
      {children}
    </button>
  )
}

/* -------------------------------------------------------------------------- */
/* Chip                                                                       */
/* -------------------------------------------------------------------------- */
export function Chip({ variant, as = 'span', children, className = '', ...rest }) {
  const Tag = as
  const classes = [
    'chip',
    as === 'button' ? 'chip--button' : '',
    variant ? `chip--${variant}` : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <Tag className={classes} {...(as === 'button' ? { type: 'button' } : {})} {...rest}>
      {children}
    </Tag>
  )
}

/* -------------------------------------------------------------------------- */
/* Field wrappers                                                             */
/* -------------------------------------------------------------------------- */
export function Field({ label, htmlFor, children }) {
  return (
    <div className="field">
      {label ? (
        <label className="field__label" htmlFor={htmlFor}>
          {label}
        </label>
      ) : null}
      {children}
    </div>
  )
}

export function Select({ label, id, options, value, onChange, anyLabel = 'Any' }) {
  return (
    <Field label={label} htmlFor={id}>
      <select
        id={id}
        className="select"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{anyLabel}</option>
        {options.map((option) => {
          const optionValue = typeof option === 'string' ? option : option.value
          const count = typeof option === 'string' ? undefined : option.count
          const text = typeof option === 'string' ? option : option.label ?? option.value
          return (
            <option key={optionValue} value={optionValue}>
              {count === undefined ? text : `${text} (${count})`}
            </option>
          )
        })}
      </select>
    </Field>
  )
}

/* -------------------------------------------------------------------------- */
/* Toggle                                                                     */
/* -------------------------------------------------------------------------- */
export function Toggle({ checked, onChange, label, id }) {
  return (
    <button
      type="button"
      id={id}
      role="switch"
      aria-checked={checked}
      className={`toggle ${checked ? 'toggle--on' : ''}`}
      onClick={() => onChange(!checked)}
      style={{ background: 'none', border: 'none', padding: 0 }}
    >
      <span className="toggle__track">
        <span className="toggle__thumb" />
      </span>
      <span className="toggle__label">{label}</span>
    </button>
  )
}

/* -------------------------------------------------------------------------- */
/* States                                                                     */
/* -------------------------------------------------------------------------- */
export function EmptyState({ title, body, action }) {
  return (
    <div className="state anim-fade">
      <Icon name="search" size={20} />
      <p className="state__title">{title}</p>
      {body ? <p className="state__body">{body}</p> : null}
      {action}
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  const isNetwork = error?.isNetwork
  return (
    <div className="state state--error anim-fade">
      <Icon name="alert" size={20} />
      <p className="state__title">{isNetwork ? 'Backend unreachable' : 'Request failed'}</p>
      <p className="state__body">{error?.message || 'Something went wrong.'}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" icon="refresh" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  )
}

export function Notice({ variant, icon = 'info', children }) {
  return (
    <div className={`notice ${variant ? `notice--${variant}` : ''}`}>
      <Icon name={icon} size={14} style={{ flex: '0 0 auto', marginTop: 2 }} />
      <span>{children}</span>
    </div>
  )
}

export { Icon }
