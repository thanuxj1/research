import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import { useResource } from '../../hooks/useResource'
import { Button, Icon, Notice } from '../ui'

/**
 * Feedback panel — a rating and an optional comment on the recommendations.
 *
 * Every sentence on screen here comes from `GET /feedback`. That is not
 * ceremony: the scale bounds and the comment limit are things the server
 * *enforces*, so a client copy of either is a copy that can be wrong, and the
 * way it fails is a 422 on a rating the user was invited to give. The privacy
 * note is a promise about what happens to the comment, which only the code doing
 * the storing can keep. The same applies after submitting — a submission can be
 * saved, deduplicated, truncated, or refused because the log is full, and
 * `message` is the server saying which. It is rendered verbatim.
 *
 * Collapsed by default. An open form at the foot of every page would compete
 * with the results for attention on the first visit, which is the one visit
 * where the person has not yet seen enough to have an opinion. The closed state
 * is a single row that reads as an invitation.
 *
 * The disclosure is a native `<details>` rather than a `useState` toggle. It is
 * keyboard-operable and announced as expandable without any ARIA of ours, it
 * survives a re-render without a state variable to lose, and it means the form
 * exists in the markup at first paint — so the static render harness can check
 * the whole body, which a JS-gated panel would hide from it.
 *
 * The totals in `form.summary` are deliberately not shown. They would be
 * anchoring — a visible "average 4.3" tells you what the right answer is before
 * you have picked one — and at the sample size this will realistically have, a
 * displayed average is noise wearing a decimal point. The aggregates exist for
 * the maintainers, at `GET /feedback/summary`.
 *
 * State is local and never reset: switching tabs keeps a half-written comment,
 * and once submitted the panel stays thanked rather than re-arming, so a second
 * click cannot turn into a second identical record. (The server would dedupe it
 * anyway; this means the user never sees that happen.)
 */

/* -------------------------------------------------------------------------- */
/* Rating scale                                                               */
/* -------------------------------------------------------------------------- */

/**
 * The five points of the scale, as buttons, each showing its own label.
 *
 * Not stars. Stars carry no units — the difference between three and four is
 * whatever the person supplies — and this scale has named points that the server
 * already sends, so showing "Mixed" and "Useful" is strictly more information
 * than showing three glyphs and four glyphs. It also survives touch: a
 * hover-to-reveal label is invisible on a phone, which is where most of this
 * app's traffic will be.
 *
 * `radiogroup`/`radio` rather than five plain buttons, because that is what this
 * is: one choice out of five, and a screen reader should say "3 of 5" instead of
 * announcing five unrelated controls.
 */
function ScaleRow({ scale, value, onChange, disabled }) {
  return (
    <div className="feedback__scale" role="radiogroup" aria-label="Rating">
      {scale.map((point) => (
        <button
          key={point.value}
          type="button"
          role="radio"
          aria-checked={value === point.value}
          disabled={disabled}
          className={
            value === point.value ? 'feedback__point feedback__point--on' : 'feedback__point'
          }
          onClick={() => onChange(point.value)}
        >
          <span className="feedback__point-value">{point.value}</span>
          <span className="feedback__point-label">{point.label}</span>
        </button>
      ))}
    </div>
  )
}

/**
 * Characters left, shown only near the end of the budget.
 *
 * Silent for the first 80% so it does not count at someone typing two sentences,
 * and amber for the last 10% so the ceiling arrives as a warning rather than as a
 * keystroke that does nothing. The textarea's `maxLength` is what actually stops
 * the overflow; this only explains why.
 */
function CharsLeft({ used, max }) {
  const left = max - used
  if (left > Math.round(max * 0.2)) return null
  return (
    <span
      className={
        left <= Math.round(max * 0.1) ? 'feedback__count feedback__count--warn' : 'feedback__count'
      }
      aria-live="polite"
    >
      {left} left
    </span>
  )
}

/* -------------------------------------------------------------------------- */
/* The form itself                                                            */
/* -------------------------------------------------------------------------- */

/**
 * Renders a form from the server's description of it.
 *
 * Separate from the panel below so that every state this can be in — collecting,
 * paused because the log is full, switched off entirely — is reachable by handing
 * it a payload, with no network and no effects. `FeedbackPanel` is then only the
 * fetch.
 */
export function FeedbackForm({ form }) {
  const [rating, setRating] = useState(null)
  const [comment, setComment] = useState('')
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState(null)
  const [sendError, setSendError] = useState(null)

  const pending = useRef(null)
  useEffect(() => () => pending.current?.abort(), [])

  const send = useCallback(async () => {
    if (!rating) return
    pending.current?.abort()
    const controller = new AbortController()
    pending.current = controller

    setSending(true)
    setSendError(null)
    try {
      const response = await api.sendFeedback(
        { rating, comment: comment.trim() || undefined },
        controller.signal,
      )
      setResult(response)
    } catch (error) {
      if (error?.name === 'AbortError') return
      setSendError(error)
    } finally {
      if (pending.current === controller) setSending(false)
    }
  }, [rating, comment])

  // Switched off server-side. Said out loud rather than hidden: it is one quiet
  // line, it matches how the app reports its other off-switches (stale prices,
  // places lookup), and it is the only signal an operator gets that the flag
  // they set actually took effect.
  if (!form.enabled) {
    return (
      <section className="feedback feedback--off">
        <p className="feedback__off-note">{form.note}</p>
      </section>
    )
  }

  const answered = result?.stored === true || result?.duplicate === true

  return (
    <details className="feedback">
      <summary className="feedback__toggle">
        <Icon name="spark" size={14} />
        <span className="feedback__title">{form.title}</span>
        <Icon name="chevron" size={13} className="feedback__chevron" />
      </summary>

      <div className="feedback__body">
        {answered ? (
          <p className="feedback__thanks">
            <Icon name="check" size={15} />
            {/* The server's sentence, whichever of the three it is. */}
            <span>{result.message}</span>
          </p>
        ) : (
          <>
            <p className="feedback__prompt">{form.prompt}</p>

            <ScaleRow
              scale={form.scale}
              value={rating}
              onChange={setRating}
              disabled={sending || !form.accepting}
            />

            {form.accepting ? (
              <div className="field">
                <label className="field__label" htmlFor="feedback-comment">
                  {form.comment_prompt}
                </label>
                <div className="feedback__comment">
                  <textarea
                    id="feedback-comment"
                    className="input feedback__textarea"
                    rows={3}
                    value={comment}
                    maxLength={form.comment_max_chars}
                    placeholder={form.comment_placeholder}
                    disabled={sending}
                    onChange={(event) => setComment(event.target.value)}
                  />
                  <CharsLeft used={comment.length} max={form.comment_max_chars} />
                </div>
              </div>
            ) : (
              <Notice variant="warn" icon="alert">
                {form.paused_note}
              </Notice>
            )}

            {sendError ? (
              <Notice variant="warn" icon="alert">
                {sendError.message}
              </Notice>
            ) : null}

            <div className="feedback__foot">
              <Button
                variant="primary"
                size="sm"
                loading={sending}
                disabled={!rating || sending || !form.accepting}
                onClick={send}
              >
                {form.submit}
              </Button>
              <p className="feedback__privacy">{form.privacy_note}</p>
            </div>
          </>
        )}
      </div>
    </details>
  )
}

/* -------------------------------------------------------------------------- */
/* Panel                                                                      */
/* -------------------------------------------------------------------------- */

export function FeedbackPanel() {
  const { data: form, loading, error } = useResource((signal) => api.feedbackForm(signal))

  // A panel that cannot be filled in is worse than no panel, so nothing renders
  // until the server has described the form. The failure case is silent for the
  // same reason: the page already shows a banner when the API is unreachable, and
  // a second error block about the feedback widget would be noise about the least
  // important thing on screen.
  if (loading || error || !form) return null

  return <FeedbackForm form={form} />
}
