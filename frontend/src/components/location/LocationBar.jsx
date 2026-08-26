import { useState } from 'react'
import { api } from '../../api/client'
import { useResource } from '../../hooks/useResource'
import { RADIUS_CHOICES } from '../../hooks/useGeolocation'
import { Button, Icon } from '../ui'
import { useLocation } from './LocationProvider'

/**
 * Location controls.
 *
 * `LocationBar` is the persistent header control; `LocationPrompt` is the
 * compact version shown inside a card's "Where to eat" section when no location
 * has been set yet. They share this file because they share the city picker and
 * must not drift: two components offering the same choice in two different
 * vocabularies is how a user ends up unsure which one the app is actually using.
 */

/**
 * The city list comes from `GET /cities` rather than a bundled constant.
 *
 * The venue lookup resolves a city name against the server's own table, so a
 * client-side copy could offer a city the server would then reject with a 422 —
 * the same reason the health conditions are fetched instead of hard-coded.
 * Mounted on demand, so a user who shares their position never pays for it.
 */
function CityPicker({ value, onChoose, autoFocus }) {
  const { data, loading, error } = useResource((signal) => api.cities(signal))
  const cities = data?.cities ?? []

  if (loading) {
    return <div className="skeleton" style={{ height: 34, width: 190, borderRadius: 8 }} />
  }

  if (error) {
    return (
      <span className="locbar__error">
        Could not load the city list — {error.message}
      </span>
    )
  }

  return (
    <select
      className="select locbar__select"
      value={value ?? ''}
      autoFocus={autoFocus}
      aria-label="Choose a city"
      onChange={(event) => onChoose(event.target.value)}
    >
      <option value="">Choose a city…</option>
      {cities.map((city) => (
        <option key={city.name} value={city.name}>
          {city.district && city.district !== city.name
            ? `${city.name} — ${city.district}`
            : city.name}
        </option>
      ))}
    </select>
  )
}

function RadiusSelect({ radiusKm, onChange }) {
  return (
    <select
      className="select locbar__select locbar__select--narrow"
      value={radiusKm}
      aria-label="Search radius"
      onChange={(event) => onChange(Number(event.target.value))}
    >
      {RADIUS_CHOICES.map((km) => (
        <option key={km} value={km}>
          within {km} km
        </option>
      ))}
    </select>
  )
}

function describe(location) {
  if (location.mode === 'city') return location.city
  if (location.mode === 'device') return 'Your current position'
  return null
}

export function LocationBar() {
  const location = useLocation()
  const { status, error, hasLocation } = location
  // The picker is opened explicitly, except when there is nothing else to fall
  // back to: after a denial or on a browser with no location API, offering the
  // alternative immediately saves the user working out what to do next.
  const [pickerOpen, setPickerOpen] = useState(false)
  const showPicker =
    pickerOpen || (!hasLocation && (status === 'denied' || status === 'unsupported' || status === 'error'))

  return (
    <section className="locbar" aria-label="Location for nearby venues">
      <div className="locbar__row">
        <Icon name="search" size={13} className="locbar__icon" />
        <div className="locbar__text">
          <span className="locbar__label">Nearby venues</span>
          <span className="locbar__value">
            {hasLocation ? describe(location) : 'No location set'}
          </span>
        </div>

        <div className="locbar__actions">
          {hasLocation ? <RadiusSelect radiusKm={location.radiusKm} onChange={location.setRadiusKm} /> : null}

          {status !== 'unsupported' ? (
            <Button
              variant={hasLocation ? 'ghost' : 'secondary'}
              size="sm"
              icon="spark"
              loading={status === 'locating'}
              onClick={location.locate}
            >
              {status === 'locating'
                ? 'Locating…'
                : location.mode === 'device'
                  ? 'Update'
                  : 'Use my location'}
            </Button>
          ) : null}

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setPickerOpen((open) => !open)}
            aria-expanded={showPicker}
          >
            {location.mode === 'city' ? 'Change city' : 'Pick a city'}
          </Button>

          {hasLocation ? (
            <Button variant="ghost" size="sm" onClick={location.clear} aria-label="Forget my location">
              <Icon name="close" size={12} />
            </Button>
          ) : null}
        </div>
      </div>

      {showPicker ? (
        <div className="locbar__row locbar__row--picker">
          <CityPicker
            value={location.mode === 'city' ? location.city : ''}
            autoFocus={pickerOpen}
            onChoose={(city) => {
              location.chooseCity(city)
              setPickerOpen(false)
            }}
          />
          <span className="locbar__hint">
            Planning from elsewhere? A city works just as well — venues are ranked from its centre.
          </span>
        </div>
      ) : null}

      {error ? <p className="locbar__error">{error}</p> : null}

      <p className="locbar__hint">
        Your position is rounded to about 110 m before it is sent, and it is never stored — only
        the choice of device-or-city is remembered.
      </p>
    </section>
  )
}

/** In-card version, shown where a venue list would be if a location were known. */
export function LocationPrompt() {
  const location = useLocation()
  const [pickerOpen, setPickerOpen] = useState(false)
  const forced =
    location.status === 'denied' ||
    location.status === 'unsupported' ||
    location.status === 'error'

  return (
    <div className="venues__prompt">
      <p className="venues__note">
        {forced
          ? location.error
          : 'Where are you? Venues are listed nearest first, so this needs a starting point.'}
      </p>
      <div className="venues__prompt-actions">
        {location.status !== 'unsupported' ? (
          <Button
            variant="secondary"
            size="sm"
            icon="spark"
            loading={location.status === 'locating'}
            onClick={location.locate}
          >
            {location.status === 'locating' ? 'Locating…' : 'Use my location'}
          </Button>
        ) : null}
        {pickerOpen || forced ? (
          <CityPicker
            value=""
            autoFocus={pickerOpen}
            onChoose={(city) => {
              location.chooseCity(city)
              setPickerOpen(false)
            }}
          />
        ) : (
          <Button variant="ghost" size="sm" onClick={() => setPickerOpen(true)}>
            Pick a city
          </Button>
        )}
      </div>
    </div>
  )
}
