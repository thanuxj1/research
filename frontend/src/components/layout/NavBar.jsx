import { Chip, Icon } from '../ui'

const TABS = [
  { id: 'search', label: 'Search', icon: 'search' },
  { id: 'recommend', label: 'Recommend', icon: 'spark' },
  { id: 'health', label: 'Health profile', icon: 'shield' },
]

export function NavBar({ tab, onTab, status, conditionCount }) {
  const online = status?.data?.status === 'ok'
  const mode = status?.data?.search?.mode

  return (
    <nav className="nav">
      <div className="shell nav__inner">
        <span className="nav__brand">
          <span className="nav__mark">CF</span>
          Ceylon Foods
        </span>

        <span className="spacer" />

        <span className="nav__status" title={status?.error ? status.error.message : mode || ''}>
          <span
            className={[
              'nav__dot',
              online ? 'nav__dot--ok' : '',
              status?.error ? 'nav__dot--down' : '',
            ]
              .filter(Boolean)
              .join(' ')}
          />
          {status?.loading ? 'connecting' : status?.error ? 'api offline' : mode || 'ready'}
        </span>

        {conditionCount > 0 ? (
          <Chip>
            <Icon name="shield" size={11} />
            {conditionCount}
          </Chip>
        ) : null}

        <div className="tabs" role="tablist">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              className={`tab ${tab === item.id ? 'tab--active' : ''}`}
              onClick={() => onTab(item.id)}
            >
              <Icon name={item.icon} size={13} />
              <span className="tab__label">{item.label}</span>
            </button>
          ))}
        </div>
      </div>
    </nav>
  )
}
