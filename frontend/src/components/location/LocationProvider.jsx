import { createContext, useContext } from 'react'
import { useGeolocation } from '../../hooks/useGeolocation'

/**
 * One location per session, shared through context.
 *
 * Context rather than props for two reasons. The consumer is a leaf — the
 * "Where to eat" list inside a food card — four levels below where the state
 * has to live, and threading it would add a `location` prop to `SearchPanel`,
 * `RecommendPanel` and `FoodGrid`, none of which use it. More importantly,
 * `useGeolocation` owns a permission prompt: two components each calling it
 * would ask the browser twice and then disagree about the answer.
 */
const LocationContext = createContext(null)

export function LocationProvider({ children }) {
  const location = useGeolocation()
  return <LocationContext.Provider value={location}>{children}</LocationContext.Provider>
}

export function useLocation() {
  const value = useContext(LocationContext)
  if (value === null) {
    throw new Error('useLocation() requires a <LocationProvider> ancestor')
  }
  return value
}
