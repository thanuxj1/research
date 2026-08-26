import { useEffect, useState } from 'react'

/**
 * Loads a one-shot resource on mount.
 *
 * `fetcher` receives an AbortSignal and must forward it, so an unmounted
 * component's request is cancelled rather than resolving into a dead setState.
 */
export function useResource(fetcher, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null })

  useEffect(() => {
    const controller = new AbortController()
    let active = true

    setState((current) => ({ ...current, loading: true, error: null }))

    fetcher(controller.signal)
      .then((data) => {
        if (active) setState({ data, loading: false, error: null })
      })
      .catch((error) => {
        if (!active || error?.name === 'AbortError') return
        setState({ data: null, loading: false, error })
      })

    return () => {
      active = false
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return state
}
