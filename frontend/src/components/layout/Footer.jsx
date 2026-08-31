/**
 * Page footer: the medical disclaimer, and nothing else.
 *
 * This used to also carry a "How the pipeline works" grid — four cards naming
 * the seven retrieval stages. It was removed on request. The reasoning it
 * described has not gone anywhere: it lives in the README for anyone reading the
 * code, and in the "Why?" panel on each card for anyone reading a result, which
 * is the version that is actually about the dish in front of you rather than
 * about the machinery.
 *
 * What is left is the one thing on this page that has to be on every page: the
 * warning that the health flags are derived from tags and are not medical
 * advice. It stays in the footer rather than beside the results because it
 * qualifies the whole app, and it is deliberately the last thing in the DOM so a
 * screen reader reaches it without it interrupting the results.
 */
export function Footer() {
  return (
    <footer className="footer">
      <div className="shell">
        <p className="footer__text">
          Ceylon Foods — Sri Lankan food discovery. Health warnings are derived from ingredient and
          nutrition tags and are general guidance only; they are not medical advice. Always confirm
          how a dish was prepared and consult a qualified professional.
        </p>
      </div>
    </footer>
  )
}
