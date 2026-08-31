import { useState } from 'react'
import { api } from './api/client'
import { Footer } from './components/layout/Footer'
import { Hero } from './components/layout/Hero'
import { NavBar } from './components/layout/NavBar'
import { LocationBar } from './components/location/LocationBar'
import { LocationProvider } from './components/location/LocationProvider'
import { FeedbackPanel } from './components/feedback/FeedbackPanel'
import { RecommendPanel } from './components/recommend/RecommendPanel'
import { SearchPanel } from './components/search/SearchPanel'
import { HealthPanel } from './components/health/HealthPanel'
import { Notice } from './components/ui'
import { useHealthProfile } from './hooks/useHealthProfile'
import { useResource } from './hooks/useResource'

export default function App() {
  const [tab, setTab] = useState('search')
  const { profile, toggleCondition, setStrict, setName, clear } = useHealthProfile()

  // Polled once at boot: drives the nav status indicator and lets the UI warn
  // when a pipeline stage is degraded instead of silently serving worse results.
  const status = useResource((signal) => api.status(signal))

  const denseDown = status.data?.search?.dense?.error
  const rerankDown =
    status.data?.search?.reranker && !status.data.search.reranker.available

  const pricing = status.data?.pricing
  const places = status.data?.places
  // Stated once here rather than on 155 cards. The per-card tag still carries the
  // "est." marker and the exact date in its tooltip; this is the version someone
  // reads before they trust any of the numbers.
  const pricesStale = pricing?.enabled && pricing?.stale
  const placesOff = places && places.enabled === false

  return (
    <LocationProvider>
      <NavBar
        tab={tab}
        onTab={setTab}
        status={status}
        conditionCount={profile.conditions.length}
      />

      <Hero status={status} />

      <main className="shell" style={{ padding: '28px 20px 0' }}>
        <div className="stack" style={{ gap: 16 }}>
          {status.error ? (
            <Notice variant="warn" icon="alert">
              {status.error.message}
            </Notice>
          ) : null}

          {denseDown ? (
            <Notice variant="warn" icon="alert">
              Embedding model unavailable — running in lexical-only mode (BM25 + fuzzy names).
              Semantic matching is degraded. Details: {denseDown}
            </Notice>
          ) : null}

          {!denseDown && rerankDown ? (
            <Notice variant="warn" icon="alert">
              Cross-encoder reranker unavailable — results use first-stage fused ranking only.
            </Notice>
          ) : null}

          {pricesStale ? (
            <Notice icon="info">
              Prices are estimates from a table dated {pricing.as_of} ({pricing.age_days} days
              ago) and are shown as ranges in {pricing.currency}. Use them to compare dishes,
              not to settle a bill.
            </Notice>
          ) : null}

          {placesOff ? (
            <Notice icon="info">
              Nearby-venue lookup is switched off on this server, so cards show prices only.
            </Notice>
          ) : null}

          {tab !== 'health' && !placesOff ? <LocationBar /> : null}

          {tab === 'search' ? <SearchPanel profile={profile} /> : null}

          {tab === 'recommend' ? <RecommendPanel profile={profile} /> : null}

          {tab === 'health' ? (
            <HealthPanel
              profile={profile}
              toggleCondition={toggleCondition}
              setStrict={setStrict}
              setName={setName}
              clear={clear}
            />
          ) : null}

          {/* Last in the column on every tab, closed. Outside the tab switch on
              purpose: it holds a half-written comment across a trip to Health
              and back, which a per-tab mount would throw away. */}
          <FeedbackPanel />
        </div>
      </main>

      <Footer />
    </LocationProvider>
  )
}
