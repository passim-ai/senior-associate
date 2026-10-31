// The colours the panel draws in.
//
// The desktop draws every Button, text field and Markdown block natively, in the app's own colours, which follow its
// light or dark theme; a plugin can neither colour them nor tell which theme is on. So the panel draws in the app's
// theme too: text and surfaces are the host's theme keys, which turn with the theme, and nothing paints a fixed light
// or dark colour that a native control could end up sitting on. Passim shows in the wordmark and in its orange, kept to
// bars, rules and the track, which read on either background. Measured (WCAG contrast on the app's background, and on
// a card, in the app's light / dark colours):
//
//   text            theme key     page light / dark    card light / dark
//   INK, HEAD       text            18.7 / 17.1          19.2 / 15.9
//   MUTED           inactive         7.5 / 11.0           7.7 / 10.2
//   ACCENT_TEXT     warning          7.7 / 7.7            7.9 / 7.1
//   OK              success          7.2 / 5.9            7.3 / 5.4
//   ERROR           error            8.1 / 7.4            8.3 / 6.8
//   (info chip)     suggestion       7.7 / 7.9            7.9 / 7.3
//
// ACCENT itself (#C2691E) is 3.7 / 5.0 on the page: enough for a bar or a rule, never for text.

/** Body text: the app's own text colour. */
export const INK = 'text'
/** Headings: the same colour, set apart by weight and size. */
export const HEAD = 'text'
/** Secondary text: details, hints, counts. */
export const MUTED = 'inactive'
/** Passim's orange, for bars, rules and the track; never for text. */
export const ACCENT = '#C2691E'
/** Text that wants the accent: a small label above a heading, the step numbers. */
export const ACCENT_TEXT = 'warning'
export const OK = 'success'
export const WARN = 'warning'
export const ERROR = 'error'
/** A card's fill: the app's raised surface. */
export const CARD = 'userMessageBackground'
/** A line between things: the app's stronger border. A Box with no border colour draws the app's faint one. */
export const LINE = 'promptBorder'

/** A chip's tone: the colour of its words and its outline. */
export type Tone = 'accent' | 'info' | 'ok' | 'warn' | 'error' | 'quiet'
export const TONE: Record<Tone, string> = { accent: 'warning', info: 'suggestion', ok: 'success', warn: 'warning', error: 'error', quiet: 'inactive' }

// A step's state as text, and its segment on the track. The track is an image: `currentColor` there is the app's text
// colour, so the done steps read in either theme.
export const STAGE_TEXT: Record<string, string> = { passed: OK, skipped: WARN, in_progress: ACCENT_TEXT, blocked: ERROR, failed: ERROR, pending: MUTED }
export const STAGE_FILL: Record<string, string> = { passed: 'currentColor', skipped: '#C9A13B', in_progress: ACCENT, blocked: '#C8483A', failed: '#C8483A' }
