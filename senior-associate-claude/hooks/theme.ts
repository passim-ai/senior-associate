// Passim's colours, and the mark drawn on the navy band.

// Passim palette. Navy carries the header band; orange the main action and live accents.
// The orange and green are the darker shades, so white text on them reads at 4.5:1.
export const NAVY = '#13264F'
export const ORANGE = '#B35F1E'
export const WHITE = '#FFFFFF'
export const WHITE_DIM = '#C7CFE0'
export const GREEN = '#1E7A45'
export const AMBER = '#D9A441'
export const RED = '#B83232'
export const SLATE = '#5B6B82'
export const TRACK = '#CBD2DD'

// Text never takes a brand colour (navy text is near-invisible in the dark theme, green and orange too faint): it is
// the host's own, in its weight, or one of the theme's own keys below, which follow the light or dark theme. Brand
// colours are fills only, with text on them in a colour that reads at 4.5:1 or more (onFill).
export const OK_TEXT = 'success'
export const WARN_TEXT = 'warning'
export const ERROR_TEXT = 'error'
export const QUIET_TEXT = 'inactive'

// A step's chip on the Packet screen and its segment on the track.
export const STAGE_FILL: Record<string, string> = { passed: GREEN, skipped: AMBER, in_progress: ORANGE, blocked: RED, failed: RED, pending: TRACK }
// The same as text, where the terminal draws the track in glyphs.
export const STAGE_TEXT: Record<string, string> = { passed: OK_TEXT, skipped: WARN_TEXT, in_progress: 'claude', blocked: ERROR_TEXT, failed: ERROR_TEXT, pending: QUIET_TEXT }

// Text on a fill: navy on the light fills (amber, the track), white on the rest. Each pair reads at 4.5:1 or more.
export function onFill(fill: string): string {
  return fill === AMBER || fill === TRACK ? NAVY : WHITE
}

// The Passim mark, drawn white on the navy band: the dotted "P" with the orange dot.
export const MARK_ON_NAVY = `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100" role="img" aria-label="Passim">
<g transform="translate(29.407 17.000) scale(0.65717) translate(-25.500 0.431)"><line x1="30.0" y1="4.5" x2="30.0" y2="95.5" stroke="#FFFFFF" stroke-width="9.0" stroke-linecap="round"/><circle cx="40.26" cy="13.35" r="3.60" fill="#FFFFFF"/><circle cx="59.44" cy="3.67" r="4.10" fill="#FFFFFF"/><circle cx="79.80" cy="10.56" r="4.60" fill="#FFFFFF"/><circle cx="89.16" cy="29.90" r="5.10" fill="#FFFFFF"/><circle cx="81.94" cy="50.13" r="5.60" fill="#FFFFFF"/><circle cx="62.45" cy="59.18" r="6.10" fill="#FFFFFF"/><circle cx="42.33" cy="51.63" r="7.80" fill="#D9812F"/></g>
</svg>`
