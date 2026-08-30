import { api } from '../../api/client'
import { useResource } from '../../hooks/useResource'
import { Button, Chip, ErrorState, Icon, Notice, Toggle } from '../ui'

/**
 * Health profile editor.
 *
 * The condition catalogue is fetched from `GET /conditions`. It is not hardcoded
 * here, which is the point: the previous frontend kept its own copy of both the
 * condition list *and* the full warning rule set, so the client could disagree
 * with the server about whether a dish was safe to eat.
 */
export function HealthPanel({ profile, toggleCondition, setStrict, setName, clear }) {
  const { data, loading, error } = useResource((signal) => api.conditions(signal))
  const conditions = data?.conditions ?? []
  const selected = profile.conditions.length

  const allergies = conditions.filter((condition) => condition.is_allergy)
  const medical = conditions.filter((condition) => !condition.is_allergy)

  return (
    <section className="section">
      <div className="panel">
        <div className="stack" style={{ gap: 16 }}>
          <div className="row wrap" style={{ gap: 14 }}>
            <div className="field" style={{ flex: '1 1 220px', maxWidth: 300 }}>
              <label className="field__label" htmlFor="profile-name">
                Your name (optional)
              </label>
              <input
                id="profile-name"
                className="input"
                value={profile.name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Only stored in this browser"
              />
            </div>
            <div className="stack" style={{ gap: 6, flex: '1 1 260px' }}>
              <span className="field__label">Strict mode</span>
              <Toggle
                checked={profile.strict}
                onChange={setStrict}
                label={
                  profile.strict
                    ? 'Remove unsafe dishes from results'
                    : 'Show unsafe dishes, flagged'
                }
              />
              <span className="panel__hint">
                Strict mode hard-filters dishes that conflict with a selected allergy, rather than
                ranking them down.
              </span>
            </div>
          </div>

          {selected > 0 ? (
            <div className="row wrap" style={{ gap: 8 }}>
              <Chip>
                <Icon name="shield" size={11} />
                {selected} active
              </Chip>
              <Button variant="ghost" size="sm" onClick={clear}>
                Clear all
              </Button>
            </div>
          ) : (
            <Notice icon="info">
              Nothing selected. Pick any conditions below and every dish across search and
              recommendations will be checked against them.
            </Notice>
          )}
        </div>
      </div>

      {error ? (
        <ErrorState error={error} />
      ) : loading ? (
        <div className="conditions">
          {Array.from({ length: 8 }, (_, index) => (
            <div key={index} className="skeleton" style={{ height: 62, borderRadius: 10 }} />
          ))}
        </div>
      ) : (
        <>
          <ConditionGroup
            title="Allergies & intolerances"
            note="Can be enforced as a hard filter with strict mode"
            conditions={allergies}
            profile={profile}
            onToggle={toggleCondition}
          />
          <ConditionGroup
            title="Medical conditions"
            note="Always advisory — dishes are flagged and ranked lower"
            conditions={medical}
            profile={profile}
            onToggle={toggleCondition}
          />
        </>
      )}

      <div className="panel">
        <div className="stack" style={{ gap: 10 }}>
          <span className="panel__title">Warning levels</span>
          <div className="warning warning--danger">
            <Icon name="alert" size={13} className="warning__icon" />
            <span>
              <strong>Avoid</strong> — directly conflicts with a selected condition.
            </span>
          </div>
          <div className="warning warning--caution">
            <Icon name="alert" size={13} className="warning__icon" />
            <span>
              <strong>Caution</strong> — fine in moderation, or worth confirming how it was prepared.
            </span>
          </div>
          <div className="warning warning--safe">
            <Icon name="check" size={13} className="warning__icon" />
            <span>
              <strong>Safe</strong> — no conflicts detected with your selections.
            </span>
          </div>
          <p className="footer__text" style={{ marginTop: 4 }}>
            These warnings are generated from ingredient and nutrition tags derived from dish
            descriptions. They are general guidance, not medical advice — always confirm with the
            restaurant and your doctor or dietitian.
          </p>
        </div>
      </div>
    </section>
  )
}

function ConditionGroup({ title, note, conditions, profile, onToggle }) {
  if (!conditions.length) return null

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="section__head">
        <h3 className="panel__title">{title}</h3>
        <span className="section__note">{note}</span>
      </div>
      <div className="conditions">
        {conditions.map((condition) => {
          const active = profile.conditions.includes(condition.id)
          return (
            <button
              key={condition.id}
              type="button"
              role="checkbox"
              aria-checked={active}
              className={`condition ${active ? 'condition--on' : ''}`}
              onClick={() => onToggle(condition.id)}
            >
              <span className="condition__check">
                {active ? <Icon name="check" size={11} strokeWidth={2.2} /> : null}
              </span>
              <span>
                <span className="condition__label">{condition.label}</span>
                <span className="condition__desc">{condition.description}</span>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
