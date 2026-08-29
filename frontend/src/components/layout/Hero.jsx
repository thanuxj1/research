import { useRef } from 'react'
import { Icon } from '../ui'

/**
 * Full-viewport hero over a photograph.
 *
 * Two things follow from it being full-height that would not otherwise be here.
 *
 * The stats row is rendered rather than computed and thrown away, which is what
 * this component did before: the array existed, the CSS for it existed, and
 * nothing ever put it on screen. On a hero sized to the content it read as
 * restraint; on a hero sized to the viewport it left most of a screen empty.
 *
 * The scroll cue exists because the search box now starts below the fold. A first
 * screen with no visible control has to say there is a second screen, and the cue
 * is a real button because on that screen it is effectively the primary control.
 */
export function Hero({ status }) {
  const heroRef = useRef(null)

  const dishes = status?.data?.dishes
  const search = status?.data?.search
  const reranked = search?.reranker?.available

  // `dishes` is absent until /status resolves, so these fall back rather than
  // rendering a blank or a zero. 155 is the shipped corpus size; if the two ever
  // disagree the served number wins, which is the right way round.
  const stats = [
    { value: dishes ? String(dishes) : '155', label: 'Dishes' },
    { value: '7', label: 'Pipeline stages' },
    { value: '11', label: 'Health conditions' },
    { value: reranked ? 'On' : 'Off', label: 'Cross-encoder' },
  ]

  function scrollPastHero() {
    const hero = heroRef.current
    if (!hero) return

    // The nav is sticky, so it keeps occupying the top of the viewport after the
    // page moves. Landing on the hero's exact bottom edge would slide the first
    // 56px of content underneath it — and `scrollIntoView` has the same problem
    // with no way to ask it for headroom. Hence the arithmetic instead.
    //
    // The offset is read from `--nav-h` rather than hardcoded so this cannot drift
    // from the token the hero's own height is derived from.
    const navH =
      Number.parseInt(
        getComputedStyle(document.documentElement).getPropertyValue('--nav-h'),
        10,
      ) || 56

    // Smooth scrolling is motion, and someone who asked for less of it asked for
    // less of this too. The `prefers-reduced-motion` block in theme.css cannot
    // reach `scrollTo`, so the check has to happen here.
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
          Ask for what you want in plain English — including what you want to avoid. Negations,
          allergies, spice tolerance and budget are parsed into real constraints, then results are
          retrieved, reranked and explained.
        </p>

        {/* Plain divs rather than a <dl>. A stats row is close to a description
            list, but the visual order is value-then-label and <dl> requires the
            <dt> first, so the markup would either be invalid or need a
            column-reverse to undo itself. Read aloud these come out as "155
            Dishes", which is the sentence anyway. */}
        <div className="hero__stats">
          {stats.map((stat) => (
            <div className="stack" key={stat.label}>
              <span className="hero__stat-value mono">{stat.value}</span>
              <span className="hero__stat-label">{stat.label}</span>
            </div>
          ))}
        </div>
      </div>

      <button type="button" className="hero__cue" onClick={scrollPastHero}>
        Start searching
        <span className="hero__cue-arrow">
          <Icon name="chevron-down" size={16} />
        </span>
      </button>
    </header>
  )
}
