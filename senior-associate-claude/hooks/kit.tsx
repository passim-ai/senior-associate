// The frame every screen is drawn in, and the pieces they share: the band, the navigation, cards, rows, links,
// the message of the moment, and the main actions.
//
// Everything is the host's own element, so it keeps the host's font, focus ring, keyboard and screen-reader
// behaviour, and its light and dark themes. Text is never drawn in a brand colour: it is the host's, in a weight, or
// one of the theme's own keys (theme.ts). Brand colours fill the band, the pills and the step chips, with text on
// them that reads at 4.5:1 in both themes.
import type { Elements, EngineInterface, ResolveInput } from 'claude-code'
import type { Card, Draft, Note, Payload, Prefs, Run, Setup, View } from '../types'
import { COMMON_TYPES } from './matter'
import { askClaude, perform } from './perform'
import { session, setNote, typed } from './state'
import { matterStatus } from './status'
import { AMBER, MARK_ON_NAVY, NAVY, OK_TEXT, ORANGE, QUIET_TEXT, WARN_TEXT, WHITE, WHITE_DIM, onFill } from './theme'
import { ASK_LABEL, nowMs } from './words'

export type Els = Pick<Elements['desktop'], 'Box' | 'Text' | 'Button' | 'Input' | 'Markdown'> & {
  isDesktop: boolean
  svg: (source: string, alt: string, width?: number, height?: number) => JSX.Element | null
}

// One main action of a screen, or its companion: the host's own primary and secondary buttons, each with a line
// under it on what it does ("About 1–1½ hours · runs in the background").
export type ActionButton = { id: string; label: string; kind: 'primary' | 'secondary'; detail?: string; hotkey?: string }

// The element table for the surface the app is drawn on; null where it cannot be drawn.
export function tableFor($: EngineInterface, e: ResolveInput): Els | null {
  if (e.surface === 'desktop') {
    const t = $.ui.resolve({ ...e, surface: 'desktop' as const })
    const { Svg } = t
    return {
      Box: t.Box, Text: t.Text, Button: t.Button, Input: t.Input, Markdown: t.Markdown,
      isDesktop: true,
      svg: (source, alt, width, height) => <Svg source={source} alt={alt} width={width} height={height} />,
    }
  }
  if (e.surface === 'terminal') {
    const t = $.ui.resolve({ ...e, surface: 'terminal' as const })
    return { Box: t.Box, Text: t.Text, Button: t.Button, Input: t.Input, Markdown: t.Markdown, isDesktop: false, svg: () => null }
  }
  return null
}

export type Kids = (JSX.Element | null | false | undefined)[]

export function makeKit($: EngineInterface, els: Els, site: 'pane' | 'inline', v: View, p: Payload | null, n: Note, b: boolean, allRuns: Record<string, Run>, st: Setup | null) {
  const { Box, Text, Button, Input } = els

  // The main action(s) of a screen: the host's primary button for the one to press, its secondary for the companion.
  // `main` marks the matter page's card, whose first action the b key presses.
  const actions = (buttons: ActionButton[], main = false) => (
    <Box key="actions" flexDirection="row" flexWrap="wrap" gap="lg" alignItems="flex-start">
      {buttons.map((a, i) => (
        <Box key={`action-${a.id}`} flexDirection="column" gap="xs" flexShrink={1}>
          <Button
            key={`main:${a.id}`}
            variant={a.kind}
            label={a.label}
            hotkey={a.hotkey ?? (main && i === 0 ? 'b' : undefined)}
            dimColor={b ? true : undefined}
            autoFocus={main && i === 0 ? true : undefined}
            onPress={() => { void perform($, a.id) }}
          />
          {a.detail ? <Text dimColor size="footnote">{a.detail}</Text> : null}
        </Box>
      ))}
    </Box>
  )

  const pill = (label: string, fill: string, key = 'pill') => (
    <Box key={key} flexDirection="row">
      <Box backgroundColor={fill} paddingX="md" paddingY="xs" borderStyle="round" borderColor={fill}>
        <Text color={onFill(fill)} weight="semibold" size="caption">{label}</Text>
      </Box>
    </Box>
  )

  // The navy band at the top: Passim, the title, the status.
  const band = (title: string, subtitle?: string, status?: { label: string; fill: string }) => (
    <Box key="band" flexDirection="column" backgroundColor={NAVY} paddingX="xl" paddingY="xl" gap="md">
      <Box flexDirection="row" alignItems="center" gap="sm">
        {els.svg(MARK_ON_NAVY, 'Passim', 22, 22)}
        <Text color={WHITE} weight="semibold">Passim</Text>
        <Text color={WHITE_DIM}>Senior Associate</Text>
      </Box>
      <Box flexDirection="column" gap="sm">
        <Text size="title" weight="bold" color={WHITE}>{title}</Text>
        {subtitle ? <Text color={WHITE_DIM}>{subtitle}</Text> : null}
        {status ? pill(status.label, status.fill) : null}
      </Box>
    </Box>
  )

  const dock = site === 'inline' ? <Button key="dock" plain dimColor onPress={() => perform($, 'dock')}>Open as side panel</Button> : null

  // Where you are and the way back, as the host's own text buttons: "← Matters   New matter".
  const topNav = (back: { id: string; label: string } | null, current: string) => (
    <Box key="nav" flexDirection="row" justifyContent="space-between" alignItems="center" paddingX="xl">
      <Box flexDirection="row" alignItems="center" gap="lg">
        {back ? <Button key={`nav-${back.id}`} plain label={`Back to ${back.label}`} onPress={() => perform($, back.id)}><Text weight="medium">{`← ${back.label}`}</Text></Button> : null}
        {current ? <Text dimColor>{current}</Text> : null}
      </Box>
      {dock}
    </Box>
  )

  // The way back again at the foot of a long screen.
  const footNav = (id: string, label: string) => (
    <Box key="foot" flexDirection="row" paddingX="xl">
      <Button key={`foot-${id}`} plain label={label} onPress={() => perform($, id)}><Text weight="medium">{`← ${label}`}</Text></Button>
    </Box>
  )

  // The pill on a matter's screens: the same word the matter page and the list use.
  const pillOf = (c: Card) => {
    const s = matterStatus(c, allRuns[c.path], nowMs())
    return { label: s.label, fill: s.fill }
  }

  const card = (title: string | null, children: Kids, borderColor?: string, key?: string) => (
    <Box key={key ?? `card-${title ?? 'plain'}`} flexDirection="column" borderStyle="round" borderDimColor={!borderColor} borderColor={borderColor} paddingX="xl" paddingY="lg" gap="md">
      {title ? <Text size="heading" weight="semibold">{title}</Text> : null}
      {children}
    </Box>
  )

  // A row into another screen: the title is the press, the whole row lights on hover, and the detail wraps
  // underneath so a narrow panel never cuts it short. Its accessible name carries the status the pill shows.
  const row = (key: string, id: string, main: string, detail: string, below?: JSX.Element | null, badge?: { label: string; fill: string }, hotkey?: string) => (
    <Box key={key} flexDirection="column" borderStyle="round" borderDimColor paddingX="lg" paddingY="sm" gap="xs" hover={{ borderColor: ORANGE }}>
      <Box flexDirection="row" justifyContent="space-between" alignItems="center" gap="md">
        <Button key={id} plain hotkey={hotkey} label={badge ? `${main}, ${badge.label}` : main} onPress={() => perform($, id)}>
          <Text weight="semibold">{main}</Text>
          <Text dimColor>{'  ›'}</Text>
        </Button>
        {badge ? pill(badge.label, badge.fill, `${key}-pill`) : null}
      </Box>
      {detail ? <Text dimColor>{detail}</Text> : null}
      {below ?? null}
    </Box>
  )

  const numbered = (num: string, title: string, text: string) => (
    <Box key={`step-${num}`} flexDirection="row" gap="md" alignItems="flex-start">
      <Box backgroundColor={ORANGE} paddingX="md" borderStyle="round" borderColor={ORANGE}>
        <Text color={WHITE} weight="bold">{num}</Text>
      </Box>
      <Box flexDirection="column" flexGrow={1}>
        <Text weight="semibold">{title}</Text>
        <Text dimColor>{text}</Text>
      </Box>
    </Box>
  )

  // A text press. `name` is its accessible name where the label alone would be ambiguous among several on a screen
  // ("Mark done" beside each item reads "Mark done: Sign the G-28").
  const link = (key: string, label: string, onPress: (press: { surface?: string }) => void, strong = false, name?: string) => (
    <Button key={key} plain dimColor={!strong} label={name} onPress={press => onPress(press as { surface?: string })}>
      {strong ? <Text weight="medium">{label}</Text> : label}
    </Button>
  )
  const links = (key: string, items: (JSX.Element | null | false)[]) => {
    const shown = items.filter(Boolean)
    return shown.length ? <Box key={key} flexDirection="row" flexWrap="wrap" gap="lg">{shown}</Box> : null
  }

  // Under the box whose save was just pressed, so the press visibly lands; gone once its text changes or the screen does.
  const savedMark = (key: string, unchanged: boolean) =>
    session.savedField === key && unchanged ? <Box key={`saved:${key}`} flexDirection="row"><Text color={OK_TEXT} weight="medium">✓ Saved</Text></Box> : null

  // The message of the moment, right under the navigation where the eye is, until it's dismissed or the screen changes.
  const status = n.text ? (
    <Box key="note" flexDirection="column" paddingX="xl">
      <Box flexDirection="row" borderStyle="round" borderColor={n.tone === 'wait' ? QUIET_TEXT : n.tone === 'ok' ? OK_TEXT : WARN_TEXT} paddingX="lg" paddingY="xs" gap="md" alignItems="flex-start" justifyContent="space-between">
        <Box flexDirection="column" flexShrink={1} flexGrow={1} gap="xs">
          {n.tone === 'ok'
            ? <Text color={OK_TEXT} weight="semibold">{`✓ ${n.text}`}</Text>
            : <Text>{`${n.tone === 'wait' ? '⏳' : '⚠'} ${n.text}`}</Text>}
          {n.ask
            ? <Box flexDirection="row" gap="md" flexWrap="wrap">
                <Button key="note-ask" plain onPress={() => { void askClaude($, n.ask!) }}><Text weight="medium">{ASK_LABEL}</Text></Button>
              </Box>
            : null}
          {n.press
            ? <Box flexDirection="row" gap="md" flexWrap="wrap">
                <Button key={`note-press:${n.press.id}`} plain onPress={() => { void perform($, n.press!.id) }}><Text weight="medium">{n.press.label}</Text></Button>
              </Box>
            : null}
        </Box>
        <Button key="dismiss-note" plain dimColor role="dismiss" onPress={() => { void setNote($, '') }}>Dismiss</Button>
      </Box>
    </Box>
  ) : null

  const version = p?.version || st?.version || ''
  const helpFoot = (
    <Box key="help-foot" flexDirection="row" paddingX="xl">
      <Button key="help" plain dimColor onPress={() => perform($, 'help')}>{version ? `Help · Senior Associate ${version}` : 'Help · Senior Associate'}</Button>
    </Box>
  )

  // A screen: its head (band and navigation), the message of the moment, its body, then Help.
  const page = (head: Kids, ...children: Kids) => (
    <Box flexDirection="column" gap="xl" paddingBottom="lg">
      {head}
      {status}
      {children}
      {v === 'help' ? null : helpFoot}
    </Box>
  )

  const body = (...children: Kids) => (
    <Box key="body" flexDirection="column" paddingX="xl" gap="lg">
      {children}
    </Box>
  )

  // A screen reached from another: the band, where you are and the way back, the body, and the way back again at the
  // foot (`foot` names it, "Back to <back>" unless given; null leaves it out).
  const subpage = (o: { title: string; subtitle?: string; status?: { label: string; fill: string }; back: { id: string; label: string }; here: string; foot?: string | null }, ...children: Kids) =>
    page([band(o.title, o.subtitle, o.status), topNav(o.back, o.here)], body(...children), o.foot === null ? null : footNav(o.back.id, o.foot ?? `Back to ${o.back.label}`))

  // A press that waits on "Yes" first, asked on the page: what happens, the press that does it, and the way out.
  const confirmBox = (key: string, text: string, yes: { id: string; label: string; name?: string }, keep: string) => (
    <Box key={`${key}-ask`} flexDirection="column" gap="xs" borderStyle="round" borderColor={AMBER} paddingX="lg" paddingY="sm">
      <Text>{text}</Text>
      <Box flexDirection="row" gap="lg">
        <Button key={yes.id} plain label={yes.name} onPress={() => perform($, yes.id)}><Text weight="medium">{yes.label}</Text></Button>
        <Button key={`${key}-keep`} plain dimColor onPress={() => perform($, 'confirm-no')}>{keep}</Button>
      </Box>
    </Box>
  )

  // A choice in a list: one line, the whole of it the press. The chosen one is marked ● and in weight, and its
  // accessible name says it is selected.
  const choice = (key: string, id: string, label: string, hint: string, chosen: boolean) => (
    <Box key={key} flexDirection="row">
      <Button key={id} plain label={chosen ? `${label}, selected` : label} onPress={() => perform($, id)}>
        <Text color={chosen ? 'claude' : undefined}>{chosen ? '● ' : '○ '}</Text>
        <Text weight={chosen ? 'semibold' : 'regular'}>{label}</Text>
        {hint ? <Text dimColor>{`  ${hint}`}</Text> : null}
      </Button>
    </Box>
  )

  // Several short choices on one line (New filing or a response?), each marked and named the same way.
  const chips = (key: string, options: { id: string; label: string; chosen: boolean }[]) => (
    <Box key={key} flexDirection="row" flexWrap="wrap" gap="md">
      {options.map(o => (
        <Button key={o.id} plain label={o.chosen ? `${o.label}, selected` : o.label} onPress={() => perform($, o.id)}>
          <Text weight={o.chosen ? 'semibold' : 'regular'}>{o.chosen ? `● ${o.label}` : `○ ${o.label}`}</Text>
        </Button>
      ))}
    </Box>
  )

  // What is being filed: the common case types (all of them once asked, or once a less common one is chosen), and
  // Something else, with a box for the attorney's own words. `missing` says what to do when Create or Save was pressed
  // with nothing chosen; `other` is what the box's Enter does once the words are kept.
  const caseChooser = (d: Draft, open: string[], missing: string, other: { submitLabel: string; onSubmit: (value: string) => void }) => {
    const types = p?.catalog.matter_types ?? []
    const showAll = open.includes('more-types') || types.slice(COMMON_TYPES).some(t => t.id === d.typeId)
    const shown = showAll ? types : types.slice(0, COMMON_TYPES)
    return [
      missing ? <Text key="case-missing">{missing}</Text> : null,
      ...shown.map(t => choice(`type-${t.id}`, `type:${t.id}`, t.label, t.hint ?? '', d.typeId === t.id)),
      types.length > shown.length
        ? <Box key="more-types" flexDirection="row"><Button key="more-types" plain onPress={() => perform($, 'more-types')}><Text weight="medium">{`More case types (${types.length - shown.length}) ›`}</Text></Button></Box>
        : null,
      choice('type-other', 'type:other', 'Something else', 'Describe it in a few words', d.typeId === 'other'),
      d.typeId === 'other'
        ? <Input key="other" label="What is being filed, in your words" placeholder="e.g. I-485 based on asylee status" submitLabel={other.submitLabel} value={typed.other || undefined} onInput={value => { typed.other = value }} onSubmit={value => { typed.other = value; other.onSubmit(value) }} />
        : null,
    ]
  }

  // New filing or a response?
  const postureChips = (d: Draft) =>
    chips('postures', (p?.catalog.filing_postures ?? []).map(fp => ({ id: `posture:${fp.value}`, label: fp.label, chosen: (d.posture || 'new filing packet') === fp.value })))

  // How the matter is filed, and whether the client is protected under 8 U.S.C. 1367. A VAWA, T or U case is
  // protected by its type, so that choice is shown made and can't be undone here.
  const filingChoices = (d: Draft, byCase: boolean) => [
    <Box key="method" flexDirection="column" gap="xs">
      <Text weight="semibold">How will it be filed?</Text>
      {chips('methods', [
        { id: 'method:paper', label: 'On paper, by mail', chosen: (d.method ?? 'paper') === 'paper' },
        { id: 'method:online', label: 'Online, in a USCIS account', chosen: d.method === 'online' },
      ])}
    </Box>,
    byCase
      ? <Text key="protect-case">{'● This client is protected under 8 U.S.C. 1367 (VAWA, T or U). Their name and documents stay out of anything Claude looks up, and the forms use the safe mailing address.'}</Text>
      : choice('protect', 'protect:toggle', 'This client is protected under 8 U.S.C. 1367 (VAWA, T or U)', 'Keeps their name and documents out of anything Claude looks up', Boolean(d.protect)),
  ]

  const howItWorks = [
    numbered('1', 'Add your details', '2 minutes, once. Your name, firm and bar number go on the G-28, each form’s preparer section and the letter’s signature.'),
    numbered('2', 'Name the client and the case', 'Choose what is being filed: an I-130/I-485, an I-751, an N-400, or anything else.'),
    numbered('3', 'Add their documents', 'Pick files one at a time, or a whole folder. Claude works from copies; your originals stay where they are.'),
    numbered('4', 'Build the packet', 'A document review takes about 5–10 minutes; a full build about 1–1½ hours, in the background. Nothing is filed or sent: you get a draft to read.'),
  ]

  return { actions, pill, band, dock, topNav, footNav, pillOf, card, row, numbered, link, links, savedMark, status, version, helpFoot, page, body, subpage, confirmBox, choice, chips, caseChooser, postureChips, filingChoices, howItWorks }
}

export type Kit = ReturnType<typeof makeKit>

// Everything a screen draws from: the surface's elements, the kit, and the session's values as this draw read them.
// ($ is not in it: the engine follows $ across files only as a function's own argument, so screens take it apart.)
export type Ctx = Els & Kit & {
  site: 'pane' | 'inline'
  v: View
  p: Payload
  n: Note
  b: boolean
  allRuns: Record<string, Run>
  pr: Prefs
  q: string
  d: Draft
  savedAnswers: Record<string, string>
  st: Setup | null
  g: { matter: string; kind: string; reply: string } | null
  open: string[]
  missingCase: boolean
  redoing: { matter: string; stage: string; from: View } | null
  asked: string
  folder: string
  noProfile: boolean
  tip: JSX.Element | null
  /** The matters list's order: updated (the default), name, case or status. */
  sort: string
}
