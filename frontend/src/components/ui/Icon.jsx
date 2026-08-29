/**
 * Inline SVG icon set.
 *
 * Deliberately replaces the emoji the previous UI used for every affordance.
 * Emoji render differently on every platform, cannot inherit colour, and made
 * severity states rely on a glyph rather than on the design system — which
 * matters when the state being communicated is "do not eat this".
 */

const paths = {
  search: <path d="M11 11 14 14M12.5 7.75a4.75 4.75 0 1 1-9.5 0 4.75 4.75 0 0 1 9.5 0Z" />,
  spark: <path d="M8 2v3.5M8 10.5V14M2 8h3.5M10.5 8H14M4.2 4.2l2 2M9.8 9.8l2 2M11.8 4.2l-2 2M6.2 9.8l-2 2" />,
  shield: <path d="M8 2 3.5 3.8v3.9c0 2.7 1.8 5.1 4.5 6.3 2.7-1.2 4.5-3.6 4.5-6.3V3.8L8 2Z" />,
  sliders: <path d="M2.5 5h7M12 5h1.5M2.5 11h1.5M6.5 11h7M10.5 3.4v3.2M4.5 9.4v3.2" />,
  alert: <path d="M8 2.8 1.9 13.2h12.2L8 2.8ZM8 6.4v3M8 11.4v.6" />,
  check: <path d="M3 8.4 6.2 11.5 13 4.8" />,
  leaf: <path d="M13 3c0 5.5-3.4 8.6-7.6 8.6H3.6C3.6 6.6 7.3 3 13 3ZM4 13c1.2-3.4 3.2-5.4 6-6.6" />,
  close: <path d="M4 4l8 8M12 4l-8 8" />,
  chevron: <path d="M5.5 3.5 10 8l-4.5 4.5" />,
  // The same stroke turned a quarter turn, as its own entry rather than a CSS
  // rotation on the caller: the one place that needs a downward chevron is the
  // hero's scroll cue, and that element's `transform` is already carrying a
  // keyframe animation, so a `rotate()` there would be overwritten mid-cycle.
  'chevron-down': <path d="M3.5 5.5 8 10l4.5-4.5" />,
  layers: <path d="M8 2 2 5.2l6 3.2 6-3.2L8 2ZM2 8.4l6 3.2 6-3.2M2 11.4l6 3.2 6-3.2" />,
  info: <path d="M8 7.2v4M8 4.9v.5M14 8A6 6 0 1 1 2 8a6 6 0 0 1 12 0Z" />,
  refresh: <path d="M13 8a5 5 0 1 1-1.6-3.7M13 2.6V5h-2.4" />,
  filter: <path d="M2.5 4h11L9.2 8.9v3.7L6.8 13.8V8.9L2.5 4Z" />,
  // Used for the halal badge. Named for the shape, not the feature, like every
  // other entry here — and deliberately *not* a certification mark. Real halal
  // marks belong to certifying bodies; reproducing one would both infringe a
  // trademark and assert an audit that the underlying OpenStreetMap tag has not
  // had. A crescent is the conventional shorthand and claims nothing.
  crescent: <path d="M10.5 3.1a5.5 5.5 0 1 0 0 9.8 5 5 0 0 1 0-9.8Z" />,
}

export function Icon({ name, size = 15, className, strokeWidth = 1.5, ...rest }) {
  const shape = paths[name]
  if (!shape) return null

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {shape}
    </svg>
  )
}
