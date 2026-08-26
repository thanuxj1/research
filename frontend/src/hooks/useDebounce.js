import { useEffect, useState } from 'react'

/** Value that only updates after `delay` ms of quiet. Used to throttle typeahead. */
export function useDebounce(value, delay = 200) {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
