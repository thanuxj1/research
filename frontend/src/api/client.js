/**
 * Thin API client.
 *
 * Everything the UI knows about food, health conditions and warnings comes from
 * here. The previous frontend shipped its own copy of the health-warning rules
 * and the condition catalogue, which had already drifted from the server's
 * version — so a dish could be flagged in the UI and not by the API, or the
 * reverse. The server is now the single source of truth.
 */

const RAW_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
export const API_BASE = RAW_BASE.replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    /** True when the server could not be reached at all. */
    this.isNetwork = status === 0
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    })
  } catch (error) {
    // Let cancellations propagate untouched so callers can ignore them.
    if (error?.name === 'AbortError') throw error
    throw new ApiError(
      `Cannot reach the API at ${API_BASE}. Start the backend with: uvicorn main:app --reload`,
      0,
    )
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = await response.json()
      if (payload?.detail) {
        detail =
          typeof payload.detail === 'string'
            ? payload.detail
            : JSON.stringify(payload.detail)
      }
    } catch {
      /* response had no JSON body; keep the status line */
    }
    throw new ApiError(detail, response.status)
  }

  return response.json()
}

const query = (params) =>
  Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join('&')

export const api = {
  search: (payload, signal) =>
    request('/search', { method: 'POST', body: payload, signal }),

  autocomplete: (text, signal) =>
    request(`/autocomplete?${query({ q: text, limit: 8 })}`, { signal }),

  recommend: (payload, signal) =>
    request('/recommend', { method: 'POST', body: payload, signal }),

  /**
   * Nearest neighbours in embedding space.
   *
   * Called only by `SimilarDrawer`, which is itself no longer mounted — the card
   * button that opened it was removed. Left in place with the drawer so the pair
   * can be re-attached or dropped together; see the note at the top of
   * `components/food/SimilarDrawer.jsx`.
   */
  similar: (payload, signal) =>
    request('/similar', { method: 'POST', body: payload, signal }),

  conditions: (signal) => request('/conditions', { signal }),

  facets: (signal) => request('/facets', { signal }),

  status: (signal) => request('/health', { signal }),

  /**
   * Price table plus its provenance (`meta.as_of`, `meta.stale`).
   *
   * Unused by the UI, deliberately: every dish payload already embeds its own
   * `price`, so a card never waits on a second request and two surfaces cannot
   * disagree about the same dish. Kept because these two endpoints are the
   * table-wide view — `unpriced`, `band_mismatches`, the per-tier ladder — and
   * are the natural source for a prices screen. Noted as unused so nobody
   * concludes from their presence that the cards depend on them; that assumption
   * is what left the README describing a fetch the client never made.
   */
  prices: (signal) => request('/prices?limit=500', { signal }),

  /** One dish's price with the per-venue-tier ladder. Also unused by the UI. */
  priceDetail: (name, signal) =>
    request(`/prices/${encodeURIComponent(name)}`, { signal }),

  /** City centroids for the picker shown when geolocation is unavailable. */
  cities: (signal) => request('/cities', { signal }),

  /**
   * Venues likely to serve `name`, near the caller.
   *
   * POST, even though it reads: `location` carries the user's position, and a
   * position in a query string ends up in access logs, `Referer` headers and
   * browser history. The server documents the same reasoning.
   */
  dishVenues: (name, location, signal) =>
    request(`/dishes/${encodeURIComponent(name)}/venues`, {
      method: 'POST',
      body: location,
      signal,
    }),

  /**
   * Food venues near the caller, with no dish in mind. Also unused by the UI —
   * every venue list in the app hangs off a specific dish. Its payload carries
   * the same `disclaimer` and `confidence_legend` keys as `dishVenues`, so
   * `VenueList` can render either without a branch.
   */
  venuesNearby: (location, signal) =>
    request('/venues/nearby', { method: 'POST', body: location, signal }),

  /**
   * The feedback form's own definition: its rating scale, its comment limit, the
   * privacy note, and the totals so far.
   *
   * Fetched rather than hard-coded for the same reason as `conditions` and
   * `cities`. The scale and the limit are things the server *enforces* — a client
   * copy of an enforced value is a client copy that can be wrong, and the way
   * that fails here is a 422 on a rating the user was invited to give. The
   * privacy note is a promise about what happens to the comment, which only the
   * code that does the storing is in a position to make.
   *
   * Answers 200 with `enabled: false` when collection is switched off, so the
   * panel can say so calmly instead of rendering an error.
   */
  feedbackForm: (signal) => request('/feedback', { signal }),

  /**
   * Submit a rating, and optionally a comment.
   *
   * The response carries the sentence to show the user in `message`. Render it
   * verbatim: a submission can be saved, deduplicated, or refused because the
   * log is full, and only the server knows which. A local "Thanks, saved!" would
   * be right two times out of three and reassuring in the one case that matters.
   */
  sendFeedback: (payload, signal) =>
    request('/feedback', { method: 'POST', body: payload, signal }),
}
