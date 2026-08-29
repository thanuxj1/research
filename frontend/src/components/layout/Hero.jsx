import { useRef } from 'react'
import { Icon } from '../ui'

/**
 * Full-viewport hero over a photograph.
 *
 * The hero highlights the four core user-facing capabilities:
 * - Smart Dish Discovery
 * - Health & Diet Safety
 * - Budget & Pricing
 * - Find Nearby Restaurants
 *
 * The scroll cue exists because the search box starts below the fold.
 */
export function Hero() {
  const heroRef = useRef(null)

  const features = [
    { icon: 'search', label: 'Smart Dish Discovery' },
    { icon: 'shield', label: 'Health & Diet Safety' },
    { icon: 'wallet', label: 'Budget & Pricing' },
    { icon: 'map-pin', label: 'Find Nearby Restaurants' },
  ]

  function scrollPastHero() {
    const hero = heroRef.current
    if (!hero) return

    const navH =
      Number.parseInt(
        getComputedStyle(document.documentElement).getPropertyValue('--nav-h'),
        10,
      ) || 56

    const reduceMotion =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches

    window.scrollTo({
      top: hero.offsetTop + hero.offsetHeight - navH,
      behavior: reduceMotion ? 'auto' : 'smooth',
    })
  }

  return (
    <header className="hero" ref={heroRef}>
      <div className="shell hero__inner">
        <span className="hero__eyebrow">
          <Icon name="layers" size={11} />
          Semantic search · explainable ranking
        </span>

        <h1 className="hero__title">
          Sri Lankan food, <em>AI Assistant</em>
        </h1>

        <p className="hero__sub">
          Ask for what you want in plain English — including what you want to
          avoid. Negations, allergies, spice tolerance and budget are parsed
          into real constraints, then results are retrieved, reranked and
          explained.
        </p>

        <div className="hero__features">
          {features.map((feature) => (
            <div className="hero__feature" key={feature.label}>
              <Icon name={feature.icon} size={16} />
              <span>{feature.label}</span>
            </div>
          ))}
        </div>
      </div>

      <button
        type="button"
        className="hero__cue"
        onClick={scrollPastHero}
      >
        Start searching
        <span className="hero__cue-arrow">
          <Icon name="chevron-down" size={16} />
        </span>
      </button>
    </header>
  )
}