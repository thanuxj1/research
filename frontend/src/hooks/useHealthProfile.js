import { useCallback, useEffect, useMemo, useState } from 'react'

const STORAGE_KEY = 'ceylon.health.profile.v2'

const EMPTY = { name: '', conditions: [], strict: false }

function read() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return EMPTY
    const parsed = JSON.parse(raw)
    return {
      name: typeof parsed?.name === 'string' ? parsed.name : '',
      conditions: Array.isArray(parsed?.conditions)
        ? parsed.conditions.filter((c) => typeof c === 'string')
        : [],
      strict: Boolean(parsed?.strict),
    }
  } catch {
    // Corrupt or unavailable storage (private mode, quota) must not break boot.
    return EMPTY
  }
}

/**
 * Health profile, persisted to localStorage.
 *
 * Only condition *ids* are stored. Their labels, descriptions and the warning
 * rules all live on the server, so the stored profile cannot go stale when the
 * rules change.
 */
export function useHealthProfile() {
  const [profile, setProfile] = useState(read)

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(profile))
    } catch {
      /* storage unavailable; the profile still works for this session */
    }
  }, [profile])

  const toggleCondition = useCallback((id) => {
    setProfile((current) => {
      const has = current.conditions.includes(id)
      return {
        ...current,
        conditions: has
          ? current.conditions.filter((c) => c !== id)
          : [...current.conditions, id],
      }
    })
  }, [])

  const setStrict = useCallback((strict) => {
    setProfile((current) => ({ ...current, strict: Boolean(strict) }))
  }, [])

  const setName = useCallback((name) => {
    setProfile((current) => ({ ...current, name }))
  }, [])

  const clear = useCallback(() => setProfile(EMPTY), [])

  return useMemo(
    () => ({ profile, toggleCondition, setStrict, setName, clear }),
    [profile, toggleCondition, setStrict, setName, clear],
  )
}
