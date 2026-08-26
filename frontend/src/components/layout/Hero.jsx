import { Icon } from '../ui'

export function Hero({ status }) {
  const dishes = status?.data?.dishes
  const search = status?.data?.search
  const reranked = search?.reranker?.available

  const stats = [
    { value: dishes ? String(dishes) : '155', label: 'Dishes' },
    { value: '7', label: 'Pipeline stages' },
    { value: '11', label: 'Health conditions' },
    { value: reranked ? 'On' : 'Off', label: 'Cross-encoder' },
  ]

  return (
    <header className="hero">
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

      </div>
    </header>
  )
}
