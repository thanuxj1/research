import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/**
 * The user's position, for the venue lookup.
 *
 * Three decisions worth stating, because each is a trade the code cannot
 * express on its own:
 *
 * **Coordinates are coarsened here as well as on the server.** The server
 * rounds because it must never trust a client; this hook rounds because a
 * precise position should not leave the browser in the first place. Three
 * decimal places is ~110 m — far finer than any restaurant search needs, and
 * coarse enough that the request does not describe which building someone is
 * standing in.
 *
 * **Only the *choice* is persisted, never the position.** A remembered city is
 * a preference. A remembered coordinate pair is a location history, and there
 * is no reason for this app to keep one. On reload, a device position is
 * re-acquired if the browser already holds the permission (so no second
 * prompt), and otherwise waits for a deliberate click.
 *
 * **Low accuracy is requested on purpose.** `enableHighAccuracy: true` wakes
 * the GPS, costs battery and seconds, and produces precision this feature
 * immediately throws away by rounding.
 */

const STORAGE_KEY = 'ceylon.location.v1'

/**
 * ~110 m. Matches the server's default `FOODAI_PLACES_COORD_PRECISION`; the
 * server rounds again regardless, so the two drifting apart costs precision,
 * never correctness.
 */
export const COORD_DECIMALS = 3

export const DEFAULT_RADIUS_KM = 5
export const RADIUS_CHOICES = [2, 5, 10, 25]

const GEO_OPTIONS = {
  enableHighAccuracy: false,
  timeout: 10000,
  // A five-minute-old fix is fine: the answer is "which city block", and
  // reusing a cached fix avoids a fresh hardware read on every mount.
  maximumAge: 300000,
}

/** Round toward the nearest grid point at `COORD_DECIMALS`. */
export function coarsen(value, decimals = COORD_DECIMALS) {
  const factor = 10 ** decimals
  return Math.round(value * factor) / factor
}

const EMPTY = { mode: 'none', city: null, latitude: null, longitude: null }

function readPreference() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return { mode: 'none', city: null, radiusKm: DEFAULT_RADIUS_KM }
    const parsed = JSON.parse(raw)
    const mode = parsed?.mode === 'device' || parsed?.mode === 'city' ? parsed.mode : 'none'
    return {
      mode,
      city: typeof parsed?.city === 'string' ? parsed.city : null,
      radiusKm: RADIUS_CHOICES.includes(parsed?.radiusKm)
        ? parsed.radiusKm
        : DEFAULT_RADIUS_KM,
    }
  } catch {
    // Private mode, disabled storage, corrupt JSON: none of these should stop
    // the app booting, and losing a remembered city is a small cost.
    return { mode: 'none', city: null, radiusKm: DEFAULT_RADIUS_KM }
  }
}

const DENIAL_MESSAGES = {
  1: 'Location permission was declined. Pick a city instead — the results are the same, just centred on the city rather than on you.',
  2: 'Your device could not determine a position. Pick a city instead.',
  3: 'Locating timed out. Try again, or pick a city instead.',
}

export function useGeolocation() {
  const preference = useRef(readPreference())
  const [place, setPlace] = useState(() => {
    const saved = preference.current
    // A saved *city* is enough to be usable immediately; the coordinates come
    // from the server's city table, so none are needed here. A saved *device*
    // choice is not usable until a fix arrives.
    return saved.mode === 'city' && saved.city
      ? { mode: 'city', city: saved.city, latitude: null, longitude: null }
      : EMPTY
  })
  const [status, setStatus] = useState(() =>
    preference.current.mode === 'city' && preference.current.city ? 'ready' : 'idle',
  )
  const [error, setError] = useState(null)
  const [radiusKm, setRadius] = useState(preference.current.radiusKm)

  const alive = useRef(true)
  useEffect(() => () => {
    alive.current = false
  }, [])

  const persist = useCallback((mode, city, radius) => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode, city, radiusKm: radius }))
    } catch {
      /* storage unavailable; the choice still holds for this session */
    }
  }, [])

  const locate = useCallback(() => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      setStatus('unsupported')
      setError('This browser does not expose a location API. Pick a city instead.')
      return
    }
    setStatus('locating')
    setError(null)
    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!alive.current) return
        setPlace({
          mode: 'device',
          city: null,
          latitude: coarsen(position.coords.latitude),
          longitude: coarsen(position.coords.longitude),
        })
        setStatus('ready')
        persist('device', null, radiusKm)
      },
      (failure) => {
        if (!alive.current) return
        setStatus(failure?.code === 1 ? 'denied' : 'error')
        setError(DENIAL_MESSAGES[failure?.code] || failure?.message || 'Could not get a position.')
        // A refused permission should not keep re-prompting on every reload.
        if (failure?.code === 1) persist('none', null, radiusKm)
      },
      GEO_OPTIONS,
    )
  }, [persist, radiusKm])

  // Re-acquire silently when the permission is already held, so a reload does
  // not cost the user a click. Guarded because Safari's Permissions API rejects
  // the 'geolocation' name outright, and because a prompt here would be an
  // unrequested interruption at page load.
  const bootstrapped = useRef(false)
  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true
    if (preference.current.mode !== 'device') return
    if (typeof navigator === 'undefined' || !navigator.permissions?.query) return
    let cancelled = false
    Promise.resolve()
      .then(() => navigator.permissions.query({ name: 'geolocation' }))
      .then((result) => {
        if (!cancelled && result?.state === 'granted') locate()
      })
      .catch(() => {
        /* permission state unknowable here; wait for an explicit click */
      })
    return () => {
      cancelled = true
    }
  }, [locate])

  const chooseCity = useCallback(
    (city) => {
      if (!city) return
      setPlace({ mode: 'city', city, latitude: null, longitude: null })
      setStatus('ready')
      setError(null)
      persist('city', city, radiusKm)
    },
    [persist, radiusKm],
  )

  const setRadiusKm = useCallback(
    (value) => {
      const next = Number(value) || DEFAULT_RADIUS_KM
      setRadius(next)
      persist(place.mode, place.city, next)
    },
    [persist, place.city, place.mode],
  )

  const clear = useCallback(() => {
    setPlace(EMPTY)
    setStatus('idle')
    setError(null)
    persist('none', null, radiusKm)
  }, [persist, radiusKm])

  const hasLocation =
    place.mode === 'city' ? Boolean(place.city) : place.latitude !== null

  /**
   * Request body for the venue endpoints.
   *
   * Coordinates and city are mutually exclusive: the server rejects a lone
   * latitude, and sending a stale city alongside live coordinates would leave
   * it guessing which the user meant.
   */
  const payload = useMemo(() => {
    if (!hasLocation) return null
    if (place.mode === 'device') {
      return { latitude: place.latitude, longitude: place.longitude, radius_km: radiusKm }
    }
    return { city: place.city, radius_km: radiusKm }
  }, [hasLocation, place, radiusKm])

  /** Stable string for effect dependencies — objects would refire every render. */
  const key = payload
    ? `${payload.city ?? ''}:${payload.latitude ?? ''}:${payload.longitude ?? ''}:${radiusKm}`
    : 'none'

  return useMemo(
    () => ({
      mode: place.mode,
      city: place.city,
      latitude: place.latitude,
      longitude: place.longitude,
      status,
      error,
      radiusKm,
      hasLocation,
      payload,
      key,
      locate,
      chooseCity,
      setRadiusKm,
      clear,
    }),
    [place, status, error, radiusKm, hasLocation, payload, key, locate, chooseCity, setRadiusKm, clear],
  )
}
