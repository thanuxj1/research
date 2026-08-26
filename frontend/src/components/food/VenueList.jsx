import { api } from '../../api/client'
import { useResource } from '../../hooks/useResource'
import { LocationPrompt } from '../location/LocationBar'
import { useLocation } from '../location/LocationProvider'
import { Chip, ErrorState, Icon, Notice } from '../ui'

/**
 * "Where to eat" — venues near the user that plausibly serve this dish.
 *
 * The honesty of this list matters more than its length. No venue API publishes
 * menus, so a match means "the right kind of place", not "we have seen this dish
 * here" — which is why every row carries its confidence and its reason, both
 * written by the server, and why the disclaimer is rendered from the payload
 * rather than hard-coded here. If the server softens or sharpens that claim, the
 * UI follows automatically instead of reassuring the user on stale terms.
 *
 * Nothing is fetched until the section is expanded: the component only mounts on
 * expand, so browsing 155 cards costs zero venue requests.
 */

function formatDistance(km, approximate) {
  if (typeof km !== 'number') return ''
  const text = km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`
  // A tilde on seed venues, whose coordinates are a neighbourhood rather than a
  // surveyed point — showing "2.98 km" for those would overstate the precision.
  return approximate ? `~${text}` : text
}

/**
 * The halal mark on a venue row.
 *
 * Rendered only when the server says `halal === true`. The two other states are
 * deliberately silent: `null` means nobody has surveyed this venue, and `false`
 * means an OpenStreetMap contributor tagged it `diet:halal=no` — thin evidence
 * on which to print a public negative claim about a named business, and the
 * absence of a badge already carries "not established" for anyone looking for
 * one. Only the positive is shown, and only as a quotation of the tag.
 *
 * The label and the tooltip are the server's words, not this file's, for the
 * same reason as the venue disclaimer and the confidence legend: the caveat that
 * this is a mapper's tag rather than a certification has to travel with the
 * claim. A local fallback string here would be a second copy free to drift, and
 * one that would keep reassuring the user after the server had stopped.
 */
function HalalBadge({ venue }) {
  if (venue.halal !== true || !venue.halal_label) return null

  return (
    <span className="halal" title={venue.halal_note || undefined}>
      <Icon name="crescent" size={10} />
      {venue.halal_label}
    </span>
  )
}

function Venue({ venue, legend }) {
  const reason = venue.reason || legend?.[venue.confidence] || ''

  return (
    <li className="venue">
      <div className="venue__head">
        <a
          className="venue__name"
          href={venue.map_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          {venue.name}
          <Icon name="chevron" size={11} />
        </a>
        <span className="venue__dist mono" title={reason}>
          {formatDistance(venue.distance_km, venue.approximate)}
        </span>
      </div>

      <div className="venue__meta">
        <span className={`conf conf--${venue.confidence}`} title={reason}>
          {venue.confidence}
        </span>
        <HalalBadge venue={venue} />
        {venue.kind ? <Chip>{venue.kind.replace(/_/g, ' ')}</Chip> : null}
        {venue.price_estimate ? (
          <Chip title={`Typical for a ${venue.price_estimate.tier} venue — an estimate, not this venue's menu.`}>
            {venue.price_estimate.display}
          </Chip>
        ) : null}
        {venue.open_now === true ? <Chip variant="veg">open now</Chip> : null}
        {venue.open_now === false ? <Chip>closed now</Chip> : null}
        {typeof venue.rating === 'number' ? (
          <Chip>
            {venue.rating.toFixed(1)}
            {venue.rating_count ? ` (${venue.rating_count})` : ''}
          </Chip>
        ) : null}
      </div>

      {venue.note ? <p className="venue__note">{venue.note}</p> : null}
      {venue.address ? <p className="venue__note">{venue.address}</p> : null}

      <div className="venue__links">
        <a
          className="venue__link"
          href={venue.directions_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Directions
        </a>
        {venue.website ? (
          <a className="venue__link" href={venue.website} target="_blank" rel="noopener noreferrer">
            Website
          </a>
        ) : null}
        {venue.phone ? (
          <a className="venue__link" href={`tel:${venue.phone}`}>
            {venue.phone}
          </a>
        ) : null}
        {venue.approximate ? (
          <span
            className="venue__approx"
            title="Location is approximate, so the map link searches for the place by name instead of dropping a pin on a guessed point."
          >
            approximate location
          </span>
        ) : null}
      </div>
    </li>
  )
}

function VenueResults({ dish, location }) {
  const { data, loading, error } = useResource(
    (signal) => api.dishVenues(dish, { ...location.payload, limit: 8 }, signal),
    [dish, location.key],
  )

  if (loading) {
    return (
      <div className="stack" style={{ gap: 8 }}>
        {Array.from({ length: 3 }, (_, index) => (
          <div key={index} className="skeleton" style={{ height: 58, borderRadius: 10 }} />
        ))}
      </div>
    )
  }

  if (error) return <ErrorState error={error} />
  if (!data) return null

  const results = data.results ?? []
  const centre = data.resolved_from_city
    ? `${data.resolved_from_city} city centre`
    : 'your position'

  return (
    <div className="venues">
      <div className="venues__head">
        <span className="venues__count">
          {results.length === 0
            ? 'Nothing found'
            : `${results.length} place${results.length === 1 ? '' : 's'}`}{' '}
          within {data.radius_km} km of {centre}
        </span>
        {data.matched_before_limit > results.length ? (
          <span className="venues__more">
            +{data.matched_before_limit - results.length} more nearby
          </span>
        ) : null}
      </div>

      {data.degraded ? (
        <Notice variant="warn" icon="alert">
          <span title={data.provider_error || ''}>
            Live venue lookup is unavailable, so these are well-known places from the bundled
            list rather than a fresh search. Distances are still real; opening hours are not
            known.
          </span>
        </Notice>
      ) : null}

      {data.note ? <Notice icon="info">{data.note}</Notice> : null}

      {results.length === 0 ? (
        <p className="venues__note">
          No food venues matched within {data.radius_km} km. Try a wider radius, or a city.
        </p>
      ) : (
        <ul className="venues__list">
          {results.map((venue) => (
            <Venue key={venue.id} venue={venue} legend={data.confidence_legend} />
          ))}
        </ul>
      )}

      <p className="venues__note venues__note--foot">{data.disclaimer}</p>
    </div>
  )
}

export function VenueList({ dish }) {
  const location = useLocation()
  // The fetch lives in a child so that the hook is called unconditionally there:
  // rendering the prompt instead must not skip a hook in this component.
  if (!location.hasLocation) return <LocationPrompt />
  return <VenueResults dish={dish} location={location} />
}
