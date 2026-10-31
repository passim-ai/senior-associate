// Passim paper: the colours the panel draws in.
//
// The panel paints its own warm paper in every theme, light or dark, and draws every text on it in one of the colours
// below, never in the host's own text colour (which turns light in a dark theme and would vanish on the paper). The
// rule from before still holds: no text colour reads under 4.5:1 on what it sits on. Measured (WCAG contrast):
//
//   text colour      on PAPER  on SURFACE  on HOVER  on its chip
//   INK  #4B4742       8.46      9.13        7.68
//   MUTED #625C54      6.07      6.55        5.51      4.58 on LINE (the pending step)
//   NAVY #13264F      13.60     14.68       12.35     12.28 on NAVY_TINT
//   ACCENT_TEXT        5.51      5.95        5.01      4.93 on ACCENT_LIGHT
//   GREEN #2E6B3F      5.86      6.32        5.32      5.39 on GREEN_TINT
//   AMBER #8A5A00      5.44      5.87        4.94      5.03 on AMBER_TINT
//   DANGER #9B382C     6.44      6.95        5.85      5.67 on RED_TINT
//   WHITE on NAVY 14.81, on NAVY_HOVER 10.36, on ACCENT_TEXT 6.00, on DANGER 7.01
//
// ACCENT itself (#B76115) reads 4.07 on PAPER: under 4.5, so it never colours text. It draws the bars, the active tab's
// underline and the track; text that wants the accent is ACCENT_TEXT, a darker shade of it.

export const PAPER = '#F7F5F1'
export const SURFACE = '#FFFEFA'
export const HOVER = '#EEEAE3'
export const LINE = '#DCD6CD'
export const INK = '#4B4742'
export const MUTED = '#625C54'
export const NAVY = '#13264F'
export const NAVY_HOVER = '#263F70'
export const ACCENT = '#B76115'
export const ACCENT_TEXT = '#9A4F0E'
export const ACCENT_LIGHT = '#F4E7D7'
export const GREEN = '#2E6B3F'
export const AMBER = '#8A5A00'
export const DANGER = '#9B382C'
export const WHITE = '#FFFFFF'

// The chips' fills, each with the one text colour that reads on it (above).
export const NAVY_TINT = '#E6EAF2'
export const GREEN_TINT = '#E3EFE5'
export const AMBER_TINT = '#F5ECD2'
export const RED_TINT = '#F6E3DF'

// Text in a state's colour: done, a warning, something wrong, something quiet.
export const OK_TEXT = GREEN
export const WARN_TEXT = AMBER
export const ERROR_TEXT = DANGER
export const QUIET_TEXT = MUTED

// The host's theme keys a Text might still name, and the paper colour each is drawn in instead.
export const THEME_TEXT: Record<string, string> = {
  text: INK, subtle: MUTED, inactive: MUTED, success: GREEN, warning: AMBER, error: DANGER, claude: ACCENT_TEXT,
  suggestion: NAVY, permission: NAVY, remember: NAVY, merged: NAVY, inverseText: WHITE,
}

// A step's marker on the Packet screen: its fill and border, and the text on it.
export const STAGE_MARK: Record<string, { fill: string; border: string; text: string }> = {
  passed: { fill: NAVY, border: NAVY, text: WHITE },
  in_progress: { fill: ACCENT_TEXT, border: ACCENT_TEXT, text: WHITE },
  skipped: { fill: AMBER_TINT, border: AMBER_TINT, text: AMBER },
  blocked: { fill: DANGER, border: DANGER, text: WHITE },
  failed: { fill: DANGER, border: DANGER, text: WHITE },
  pending: { fill: PAPER, border: LINE, text: MUTED },
}
// A step's segment on the track, drawn as graphics (3:1 is enough there; the words beside it carry the meaning).
export const STAGE_FILL: Record<string, string> = { passed: NAVY, skipped: '#C9A13B', in_progress: ACCENT, blocked: DANGER, failed: DANGER, pending: LINE }
// The same as text.
export const STAGE_TEXT: Record<string, string> = { passed: GREEN, skipped: AMBER, in_progress: ACCENT_TEXT, blocked: DANGER, failed: DANGER, pending: MUTED }

// A chip's text colour, by its fill. A fill not listed is the plain chip: MUTED on SURFACE with a LINE border.
const CHIP_TEXT: Record<string, string> = { [NAVY_TINT]: NAVY, [GREEN_TINT]: GREEN, [AMBER_TINT]: AMBER, [RED_TINT]: DANGER, [ACCENT_LIGHT]: ACCENT_TEXT, [SURFACE]: MUTED }
export function onFill(fill: string): string {
  return CHIP_TEXT[fill] ?? MUTED
}
