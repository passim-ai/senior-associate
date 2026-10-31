// The frame every screen is drawn in, and the pieces they share: the header, the title, the matter's tabs, cards and
// rules, buttons and links, the message of the moment, and the main actions.
//
// Passim paper (theme.ts): the page paints its own warm paper and every text on it is drawn in a paper colour, never
// the host's, so it reads the same in a light or a dark theme. Text is the kit's own (paperText), which draws INK
// unless told otherwise and turns dimColor and the host's theme keys into paper colours. Buttons are the host's plain
// Buttons, drawn inside a Box that paints them (primary: navy with white text; secondary: a line border with navy
// text), so they keep the host's focus ring, keyboard and screen-reader behaviour. Text fields and pickers keep the
// host's own styling; each sits in a well painted in the host's own background colour, so its label and text read in
// either theme.
import type { Elements, EngineInterface, ResolveInput } from 'claude-code'
import type { Card, Draft, Note, Payload, Prefs, Run, Setup, View } from '../types'
import { WORDMARK, WORDMARK_RATIO } from './brand'
import { COMMON_TYPES } from './matter'
import { askClaude, perform } from './perform'
import { session, setNote, typed } from './state'
import { matterStatus } from './status'
import { ACCENT, ACCENT_LIGHT, ACCENT_TEXT, AMBER, GREEN, HOVER, INK, LINE, MUTED, NAVY, NAVY_HOVER, PAPER, SURFACE, THEME_TEXT, WHITE, onFill } from './theme'
import { ASK_LABEL, nowMs } from './words'

type Table = Elements['desktop']
type TextProps = Parameters<Table['Text']>[0]

export type Els = Pick<Table, 'Box' | 'Text' | 'Button' | 'Input'> & {
  isDesktop: boolean
  /** The panel is narrow (the side panel at its usual width): headers stack and columns fold into one. */
  narrow: boolean
  svg: (source: string, alt: string, width?: number, height?: number) => JSX.Element | null
}

// One main action of a screen, or its companion: a primary (navy) and a secondary (outlined) button, each with a line
// under it on what it does ("About 1–1½ hours · runs in the background").
export type ActionButton = { id: string; label: string; kind: 'primary' | 'secondary'; detail?: string; hotkey?: string }

// Below this many columns the panel is drawn narrow. The desktop reports the side panel's width in cells of its code
// font (about 8 pixels each), so this is about 560 pixels.
export const NARROW_COLUMNS = 72

// Text drawn on the paper: INK unless a colour is given; dimColor is MUTED; a host theme key is its paper colour.
function paperText(Base: Table['Text']): Table['Text'] {
  return (props: TextProps) => {
    const { color, dimColor, ...rest } = props as TextProps & { color?: string }
    const named = typeof color === 'string' && !color.startsWith('#') ? THEME_TEXT[color] ?? INK : color
    return Base({ ...rest, color: named ?? (dimColor ? MUTED : INK) } as TextProps)
  }
}

// The element table for the surface the app is drawn on; null where it cannot be drawn. `columns` is how wide the
// site is, in cells, where the surface said.
export function tableFor($: EngineInterface, e: ResolveInput, columns?: number): Els | null {
  const narrow = typeof columns === 'number' && columns > 0 && columns < NARROW_COLUMNS
  if (e.surface === 'desktop') {
    const t = $.ui.resolve({ ...e, surface: 'desktop' as const })
    const { Svg } = t
    return {
      Box: t.Box, Text: paperText(t.Text), Button: t.Button, Input: t.Input,
      isDesktop: true,
      narrow,
      svg: (source, alt, width, height) => <Svg source={source} alt={alt} width={width} height={height} />,
    }
  }
  if (e.surface === 'terminal') {
    const t = $.ui.resolve({ ...e, surface: 'terminal' as const })
    return { Box: t.Box, Text: paperText(t.Text as Table['Text']), Button: t.Button, Input: t.Input, isDesktop: false, narrow, svg: () => null }
  }
  return null
}

export type Kids = (JSX.Element | null | false | undefined)[]

// The matter's tabs, each the view it shows and the key that opens it.
export type Tab = 'matter' | 'documents' | 'items' | 'packet' | 'memo' | 'timeline'
const TABS: { tab: Tab; key: string; id: string; label: string }[] = [
  { tab: 'matter', key: 'nav-matter', id: 'matter', label: 'Overview' },
  { tab: 'documents', key: 'docs', id: 'docs', label: 'Documents' },
  { tab: 'items', key: 'items', id: 'items', label: 'Questions' },
  { tab: 'packet', key: 'packet', id: 'packet', label: 'Packet' },
  { tab: 'memo', key: 'memo', id: 'memo', label: 'Memo & request' },
  { tab: 'timeline', key: 'timeline', id: 'timeline', label: 'Timeline' },
]

// What the Questions tab holds open: the open items and the questions Claude asked, counted once each.
export function questionCount(c: Card): number {
  const keys = new Set<string>((c.open_items?.open ?? []).map(it => it.id))
  for (const n of c.needs_you) if (n.who !== 'system') keys.add(n.key)
  return keys.size
}

export function makeKit($: EngineInterface, els: Els, site: 'pane' | 'inline', v: View, p: Payload | null, n: Note, b: boolean, allRuns: Record<string, Run>, st: Setup | null) {
  const { Box, Text, Button, Input, narrow } = els

  // ----- rules, labels and chips -----

  // A thin rule across the page, in LINE: a Box with a border and no height.
  const rule = (key: string, color = LINE) => <Box key={key} height={0} borderStyle="single" borderColor={color} />

  // A small label above a heading: "NEXT STEP", "YOUR FIRST MATTER".
  const eyebrow = (text: string, key = 'eyebrow') => <Text key={key} size="caption" weight="semibold" color={ACCENT_TEXT}>{text.toUpperCase()}</Text>

  // A heading inside a page: navy, semibold.
  const heading = (text: string, key?: string, size: 'heading' | 'body' = 'heading') => <Text key={key ?? `h-${text}`} size={size} weight="semibold" color={NAVY}>{text}</Text>

  // A chip: a status, a count. Its text is the one colour that reads on its fill.
  const pill = (label: string, fill: string, key = 'pill') => (
    <Box key={key} flexDirection="row" flexShrink={0}>
      <Box backgroundColor={fill} paddingX="sm" borderStyle="round" borderColor={fill === SURFACE ? LINE : fill}>
        <Text color={onFill(fill)} weight="semibold" size="caption">{label}</Text>
      </Box>
    </Box>
  )

  // ----- buttons -----

  type Look = 'primary' | 'secondary' | 'link' | 'quiet'
  // A press, in one of four looks. Primary and secondary are a plain Button inside a Box that paints it; a link is navy
  // text; a quiet one is muted text. `name` is the accessible name where the words alone would be ambiguous.
  const button = (key: string, label: string, onPress: (press: { surface?: string }) => void, look: Look = 'link', o: { name?: string; hotkey?: string; autoFocus?: boolean; small?: boolean } = {}) => {
    const press = (e: unknown) => onPress(e as { surface?: string })
    const size = o.small ? 'footnote' as const : undefined
    if (look === 'link' || look === 'quiet') {
      return (
        <Button key={key} plain label={o.name} hotkey={o.hotkey} autoFocus={o.autoFocus ? true : undefined} onPress={press}>
          <Text color={look === 'link' ? NAVY : MUTED} weight={look === 'link' ? 'medium' : 'regular'} size={size}>{label}</Text>
        </Button>
      )
    }
    const waiting = b && look === 'primary'
    const fill = look === 'primary' ? (waiting ? LINE : NAVY) : SURFACE
    return (
      <Box key={`bx:${key}`} flexDirection="row" backgroundColor={fill} borderStyle="round" borderColor={look === 'primary' ? fill : LINE}
        paddingX={o.small ? 'md' : 'lg'} paddingY={o.small ? 'xs' : 'sm'}
        hover={look === 'primary' ? (waiting ? undefined : { backgroundColor: NAVY_HOVER, borderColor: NAVY_HOVER }) : { backgroundColor: HOVER, borderColor: MUTED }}>
        <Button key={key} plain variant={look} label={o.name ?? label} hotkey={o.hotkey} dimColor={waiting ? true : undefined} autoFocus={o.autoFocus ? true : undefined} onPress={press}>
          <Text color={look === 'primary' ? (waiting ? MUTED : WHITE) : NAVY} weight="semibold" size={size ?? 'footnote'}>{label}</Text>
        </Button>
      </Box>
    )
  }
  // A button on a line of its own, not stretched across the page.
  const lone = (key: string, el: JSX.Element) => <Box key={`lone:${key}`} flexDirection="row">{el}</Box>

  // The main action(s) of a screen: primary first. `main` marks the matter page's card, whose first action the b key
  // presses and where the focus starts.
  const actions = (buttons: ActionButton[], main = false) => (
    <Box key="actions" flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="md" alignItems="flex-start">
      {buttons.map((a, i) => (
        <Box key={`action-${a.id}`} flexDirection="column" gap="xs" flexShrink={1}>
          <Box flexDirection="row">
            {button(`main:${a.id}`, a.label, () => { void perform($, a.id) }, a.kind, { hotkey: a.hotkey ?? (main && i === 0 ? 'b' : undefined), autoFocus: main && i === 0 })}
          </Box>
          {a.detail ? <Text color={MUTED} size="caption">{a.detail}</Text> : null}
        </Box>
      ))}
    </Box>
  )

  // A text press. `name` is its accessible name where the label alone would be ambiguous among several on a screen
  // ("Mark done" beside each item reads "Mark done: Sign the G-28").
  const link = (key: string, label: string, onPress: (press: { surface?: string }) => void, strong = false, name?: string) =>
    button(key, label, onPress, strong ? 'link' : 'quiet', { name })
  const links = (key: string, items: (JSX.Element | null | false)[]) => {
    const shown = items.filter(Boolean)
    return shown.length ? <Box key={key} flexDirection="row" flexWrap="wrap" columnGap="lg" rowGap="xs" alignItems="center">{shown}</Box> : null
  }

  // ----- the header: Passim's lockup, and the places every screen can go -----

  const matterViews: View[] = ['matter', 'documents', 'packet', 'items', 'memo', 'request', 'redo', 'intake', 'timeline']
  const navItem = (key: string, label: string, id: string, selected: boolean) => (
    <Box key={`navbx:${key}`} flexDirection="row" backgroundColor={selected ? HOVER : SURFACE} borderStyle="round" borderColor={selected ? HOVER : SURFACE} paddingX="sm" hover={{ backgroundColor: HOVER, borderColor: HOVER }}>
      <Button key={key} plain label={selected ? `${label}, current` : label} onPress={() => { void perform($, id) }}>
        <Text size="footnote" weight={selected ? 'semibold' : 'medium'} color={selected ? NAVY : MUTED}>{label}</Text>
      </Button>
    </Box>
  )
  const nav = (
    <Box key="nav" flexDirection="row" flexWrap="wrap" columnGap={narrow ? 'xs' : 'sm'} rowGap="xs" alignItems="center" justifyContent={narrow ? 'space-between' : 'flex-end'} flexGrow={narrow ? 1 : 0}>
      {navItem('nav-all', 'Matters', 'all', v === 'home' || v === 'new' || v === 'welcome' || matterViews.includes(v))}
      {navItem('profile', 'Your details', 'profile', v === 'profile')}
      {navItem('nav-setup', 'Setup', 'setup', v === 'setup')}
      {navItem('help', 'Help', 'help', v === 'help')}
      {site === 'inline' ? navItem('dock', 'Open as side panel', 'dock', false) : null}
    </Box>
  )
  const markWidth = narrow ? 100 : 118
  const lockup = (
    <Box key="lockup" flexDirection="row" alignItems="center" gap="md" flexShrink={0}>
      {els.svg(WORDMARK, 'Passim', markWidth, Math.round(markWidth * WORDMARK_RATIO))}
      <Box width={0} height={1} borderStyle="single" borderColor={LINE} />
      <Text size="footnote" weight="semibold" color={NAVY}>Senior Associate</Text>
    </Box>
  )
  const header = (
    <Box key="header" flexDirection="column">
      <Box flexDirection={narrow ? 'column' : 'row'} flexWrap="wrap" justifyContent="space-between" alignItems={narrow ? 'flex-start' : 'center'} rowGap="sm" columnGap="lg" backgroundColor={SURFACE} paddingX={narrow ? 'lg' : 'xl'} paddingY="md">
        {lockup}
        {nav}
      </Box>
      {rule('header-rule')}
    </Box>
  )

  // ----- the title of a screen, and where it sits -----

  // The page's title: the name in navy, a line under it, and what sits at its right (a status, New matter).
  const title = (text: string, sub?: string | null, right?: JSX.Element | null) => (
    <Box key="title" flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="lg" rowGap="sm">
      <Box flexDirection="column" gap="xs" flexShrink={1}>
        <Text size="title" weight="semibold" color={NAVY}>{text}</Text>
        {sub ? <Text color={MUTED}>{sub}</Text> : null}
      </Box>
      {right ?? null}
    </Box>
  )

  // Where you are: "Matters › Garcia I-130 I-485", each place before the last a press.
  const crumbs = (items: ({ key: string; label: string; id: string; name?: string } | string)[]) => (
    <Box key="crumbs" flexDirection="row" flexWrap="wrap" alignItems="center" columnGap="xs">
      {items.flatMap((it, i) => [
        i > 0 ? <Text key={`sep-${i}`} size="footnote" color={MUTED}>›</Text> : null,
        typeof it === 'string'
          ? <Text key={`here-${i}`} size="footnote" color={MUTED}>{it}</Text>
          : <Button key={it.key} plain label={it.name} onPress={() => { void perform($, it.id) }}><Text size="footnote" weight="medium" color={NAVY}>{it.label}</Text></Button>,
      ])}
    </Box>
  )

  // The pill on a matter's screens: the same word the matter page and the list use.
  const pillOf = (c: Card) => {
    const s = matterStatus(c, allRuns[c.path], nowMs())
    return { label: s.label, fill: s.fill }
  }

  // The matter's tabs: the one open in navy over an accent underline, Questions with how many are open.
  const tabs = (c: Card, active: Tab) => {
    const count = questionCount(c)
    return (
      <Box key="tabs" flexDirection="column">
        <Box flexDirection="row" flexWrap="wrap" columnGap={narrow ? 'lg' : 'xl'} rowGap="sm">
          {TABS.map(t => {
            const on = t.tab === active
            return (
              <Box key={`tab:${t.key}`} flexDirection="column" gap="xs">
                <Button key={t.key} plain label={`${t.label}${t.tab === 'items' && count ? `, ${count} open` : ''}${on ? ', current' : ''}`} onPress={() => { void perform($, t.id) }}>
                  <Text size="footnote" weight="semibold" color={on ? NAVY : MUTED}>{t.label}</Text>
                  {t.tab === 'items' && count ? <Text size="caption" color={MUTED}>{' '}</Text> : null}
                  {t.tab === 'items' && count ? <Text size="caption" weight="semibold" color={ACCENT_TEXT} backgroundColor={ACCENT_LIGHT}>{` ${count} `}</Text> : null}
                </Button>
                {rule(`tab-line:${t.key}`, on ? ACCENT : PAPER)}
              </Box>
            )
          })}
        </Box>
        {rule('tabs-rule')}
      </Box>
    )
  }

  // ----- containers -----

  // A card on the paper: SURFACE with a LINE border; a border colour marks one that needs attention.
  const card = (heading: string | null, children: Kids, borderColor?: string, key?: string) => (
    <Box key={key ?? `card-${heading ?? 'plain'}`} flexDirection="column" backgroundColor={SURFACE} borderStyle="round" borderColor={borderColor ?? LINE} paddingX={narrow ? 'lg' : 'xl'} paddingY="lg" gap="md">
      {heading ? <Text size="heading" weight="semibold" color={NAVY}>{heading}</Text> : null}
      {children}
    </Box>
  )

  // A section on the paper itself, with no card: its heading, then its content.
  const section = (heading: string | null, children: Kids, key?: string, right?: JSX.Element | null) => (
    <Box key={key ?? `sec-${heading ?? 'plain'}`} flexDirection="column" gap="md">
      {heading
        ? <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="md" rowGap="xs">
            <Text size="heading" weight="semibold" color={NAVY}>{heading}</Text>
            {right ?? null}
          </Box>
        : null}
      {children}
    </Box>
  )

  // A card with the accent bar down its left edge: the matter's next step, a suggested approach.
  const barCard = (key: string, bar: string, children: Kids, fill = SURFACE) => (
    <Box key={key} flexDirection="row" backgroundColor={fill}>
      <Box backgroundColor={bar} paddingLeft="xs" />
      <Box flexDirection="column" flexGrow={1} flexShrink={1} paddingX={narrow ? 'lg' : 'xl'} paddingY="lg" gap="md">
        {children}
      </Box>
    </Box>
  )

  // Columns side by side when the panel is wide, one above the other when it is narrow.
  const columns = (key: string, cols: Kids) => (
    <Box key={key} flexDirection={narrow ? 'column' : 'row'} flexWrap="wrap" columnGap="xl" rowGap="lg" alignItems="flex-start">
      {cols.filter(Boolean).map((col, i) => (
        <Box key={`${key}-col-${i}`} flexDirection="column" flexGrow={1} flexShrink={1} width={narrow ? '100%' : `${Math.floor(94 / Math.max(1, cols.filter(Boolean).length))}%`}>
          {col}
        </Box>
      ))}
    </Box>
  )

  // A section folded under its title: ▸ closed, ▾ open. `id` is what the press toggles (the expanded list's key).
  const disclosure = (id: string, label: string, hint: string, isOpen: boolean, children: Kids) => (
    <Box key={`disc-${id}`} flexDirection="column" gap="md">
      <Box flexDirection="row" flexWrap="wrap" columnGap="md" alignItems="center">
        <Button key={id} plain label={`${label}, ${isOpen ? 'open' : 'folded'}`} onPress={() => { void perform($, id) }}>
          <Text weight="semibold" color={NAVY}>{`${isOpen ? '▾' : '▸'} ${label}`}</Text>
        </Button>
        {hint ? <Text size="footnote" color={MUTED}>{hint}</Text> : null}
      </Box>
      {isOpen ? <Box flexDirection="column" gap="md" paddingLeft="lg">{children}</Box> : null}
    </Box>
  )

  // A row into a matter on the list: the name is the press, the status chip at its right, the detail under it.
  // Its accessible name carries the status the chip shows.
  const row = (key: string, id: string, main: string, detail: string, below?: JSX.Element | null, badge?: { label: string; fill: string }, hotkey?: string) => (
    <Box key={key} flexDirection="column" backgroundColor={SURFACE} borderStyle="round" borderColor={LINE} paddingX="lg" paddingY="md" gap="xs" hover={{ borderColor: ACCENT }}>
      <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="md" rowGap="xs">
        <Box flexDirection="row" flexShrink={1}>
          <Button key={id} plain hotkey={hotkey} label={badge ? `${main}, ${badge.label}` : main} onPress={() => perform($, id)}>
            <Text size="heading" weight="semibold" color={NAVY}>{main}</Text>
            <Text color={MUTED}>{'  ›'}</Text>
          </Button>
        </Box>
        {badge ? pill(badge.label, badge.fill, `${key}-pill`) : null}
      </Box>
      {detail ? <Text color={MUTED} size="footnote">{detail}</Text> : null}
      {below ?? null}
    </Box>
  )

  // A numbered step: 01, 02, 03 in the accent, a short title, a line on what it means.
  const numbered = (num: string, heading: string, text: string) => (
    <Box key={`step-${num}`} flexDirection="row" gap="md" alignItems="flex-start">
      <Box flexDirection="row" flexShrink={0}><Text size="heading" weight="semibold" color={ACCENT_TEXT} tabular>{num.padStart(2, '0')}</Text></Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1} gap="xs">
        <Text weight="semibold" color={NAVY}>{heading}</Text>
        <Text color={INK} size="footnote">{text}</Text>
      </Box>
    </Box>
  )

  // A text field or picker of the host's, in a well painted in the host's own background colour, so the label and the
  // text the host draws in its own colours read in either theme.
  const field = (input: JSX.Element, key?: string) => (
    <Box key={key} flexDirection="column" backgroundColor="inverseText" borderStyle="round" borderColor={LINE} paddingX="sm" paddingY="xs">
      {input}
    </Box>
  )

  // Under the box whose save was just pressed, so the press visibly lands; gone once its text changes or the screen does.
  const savedMark = (key: string, unchanged: boolean) =>
    session.savedField === key && unchanged ? <Box key={`saved:${key}`} flexDirection="row"><Text color={GREEN} weight="medium">✓ Saved</Text></Box> : null

  // The message of the moment, at the top of the page where the eye is, until it's dismissed or the screen changes.
  const toneColor = n.tone === 'wait' ? NAVY : n.tone === 'ok' ? GREEN : AMBER
  const status = n.text ? (
    <Box key="note" flexDirection="row" backgroundColor={SURFACE} borderStyle="round" borderColor={LINE}>
      <Box backgroundColor={toneColor} paddingLeft="xs" />
      <Box flexDirection="row" flexGrow={1} flexShrink={1} paddingX="lg" paddingY="sm" gap="md" alignItems="flex-start" justifyContent="space-between">
        <Box flexDirection="column" flexShrink={1} flexGrow={1} gap="xs">
          {n.tone === 'ok'
            ? <Text color={GREEN} weight="semibold">{`✓ ${n.text}`}</Text>
            : <Text color={n.tone === 'wait' ? NAVY : INK}>{`${n.tone === 'wait' ? '⏳' : '⚠'} ${n.text}`}</Text>}
          {n.ask ? links('note-asks', [button('note-ask', ASK_LABEL, () => { void askClaude($, n.ask!) }, 'link')]) : null}
          {n.press ? links('note-presses', [button(`note-press:${n.press.id}`, n.press.label, () => { void perform($, n.press!.id) }, 'link')]) : null}
        </Box>
        {button('dismiss-note', 'Dismiss', () => { void setNote($, '') }, 'quiet', { small: true })}
      </Box>
    </Box>
  ) : null

  const version = p?.version || st?.version || ''

  // A screen: the header, then its head (where you are, the title, the tabs), the message of the moment, and its body,
  // on the paper from edge to edge.
  const page = (head: Kids, ...children: Kids) => (
    <Box flexDirection="column" backgroundColor={PAPER} minHeight="100%" flexGrow={1}>
      {header}
      <Box key="content" flexDirection="column" paddingX={narrow ? 'lg' : 'xl'} paddingTop="lg" paddingBottom="xl" gap="lg">
        {head}
        {status}
        {children}
      </Box>
    </Box>
  )

  const body = (...children: Kids) => (
    <Box key="body" flexDirection="column" gap="lg">
      {children}
    </Box>
  )

  // A screen reached from another: where you are and the way back, the title, the body.
  const subpage = (o: { title: string; subtitle?: string; status?: { label: string; fill: string }; back: { id: string; label: string }; here: string; foot?: string | null }, ...children: Kids) =>
    page(
      [
        // The header's Matters is nav-all; the crumb back to Matters is a press of its own.
        crumbs([{ key: o.back.id === 'all' ? 'crumb-all' : `nav-${o.back.id}`, label: o.back.label, id: o.back.id, name: `Back to ${o.back.label}` }, o.here]),
        title(o.title, o.subtitle, o.status ? pill(o.status.label, o.status.fill, 'title-pill') : null),
      ],
      body(...children),
    )

  // One of the matter's tabs: Matters › the matter, its name and case, its status, the tabs, then the tab's body.
  const matterPage = (c: Card, tab: Tab, ...children: Kids) => {
    const s = pillOf(c)
    return page(
      [
        crumbs([{ key: 'crumb-all', label: 'Matters', id: 'all', name: 'Back to Matters' }, c.name]),
        title(c.name, [c.case_line, c.intake.filing_posture_label].filter(Boolean).join(' · '), pill(s.label, s.fill, 'title-pill')),
        tabs(c, tab),
      ],
      body(...children),
    )
  }

  // A press that waits on "Yes" first, asked on the page: what happens, the press that does it, and the way out.
  const confirmBox = (key: string, text: string, yes: { id: string; label: string; name?: string }, keep: string) => (
    <Box key={`${key}-ask`} flexDirection="row" backgroundColor={SURFACE} borderStyle="round" borderColor={LINE}>
      <Box backgroundColor={AMBER} paddingLeft="xs" />
      <Box flexDirection="column" flexGrow={1} flexShrink={1} gap="sm" paddingX="lg" paddingY="sm">
        <Text>{text}</Text>
        <Box flexDirection="row" flexWrap="wrap" columnGap="lg" rowGap="xs" alignItems="center">
          {button(yes.id, yes.label, () => { void perform($, yes.id) }, 'secondary', { name: yes.name, small: true })}
          {button(`${key}-keep`, keep, () => { void perform($, 'confirm-no') }, 'quiet')}
        </Box>
      </Box>
    </Box>
  )

  // A choice in a list: one line, the whole of it the press. The chosen one is marked ● in navy and in weight, and its
  // accessible name says it is selected.
  const choice = (key: string, id: string, label: string, hint: string, chosen: boolean) => (
    <Box key={key} flexDirection="row">
      <Button key={id} plain label={chosen ? `${label}, selected` : label} onPress={() => perform($, id)}>
        <Text color={chosen ? ACCENT_TEXT : MUTED}>{chosen ? '● ' : '○ '}</Text>
        <Text weight={chosen ? 'semibold' : 'regular'} color={chosen ? NAVY : INK}>{label}</Text>
        {hint ? <Text color={MUTED}>{`  ${hint}`}</Text> : null}
      </Button>
    </Box>
  )

  // Several short choices on one line (New filing or a response?), each marked and named the same way.
  const chips = (key: string, options: { id: string; label: string; chosen: boolean }[]) => (
    <Box key={key} flexDirection="row" flexWrap="wrap" columnGap="sm" rowGap="xs">
      {options.map(o => (
        <Box key={`chipbx:${o.id}`} flexDirection="row" backgroundColor={o.chosen ? NAVY : SURFACE} borderStyle="round" borderColor={o.chosen ? NAVY : LINE} paddingX="md" hover={o.chosen ? undefined : { borderColor: MUTED }}>
          <Button key={o.id} plain label={o.chosen ? `${o.label}, selected` : o.label} onPress={() => perform($, o.id)}>
            <Text size="footnote" weight={o.chosen ? 'semibold' : 'medium'} color={o.chosen ? WHITE : NAVY}>{o.chosen ? `● ${o.label}` : `○ ${o.label}`}</Text>
          </Button>
        </Box>
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
      missing ? <Text key="case-missing" color={AMBER} weight="medium">{missing}</Text> : null,
      ...shown.map(t => choice(`type-${t.id}`, `type:${t.id}`, t.label, t.hint ?? '', d.typeId === t.id)),
      types.length > shown.length ? lone('more-types', button('more-types', `More case types (${types.length - shown.length}) ›`, () => { void perform($, 'more-types') }, 'link')) : null,
      choice('type-other', 'type:other', 'Something else', 'Describe it in a few words', d.typeId === 'other'),
      d.typeId === 'other'
        ? field(<Input key="other" label="What is being filed, in your words" placeholder="e.g. I-485 based on asylee status" submitLabel={other.submitLabel} value={typed.other || undefined} onInput={value => { typed.other = value }} onSubmit={value => { typed.other = value; other.onSubmit(value) }} />, 'field-other')
        : null,
    ]
  }
  // New filing or a response?
  const postureChips = (d: Draft) =>
    chips('postures', (p?.catalog.filing_postures ?? []).map(fp => ({ id: `posture:${fp.value}`, label: fp.label, chosen: (d.posture || 'new filing packet') === fp.value })))

  // How the matter is filed, and whether the client is protected under 8 U.S.C. 1367. A VAWA, T or U case is
  // protected by its type, so that choice is shown made and can't be undone here.
  const filingChoices = (d: Draft, byCase: boolean) => [
    <Box key="method" flexDirection="column" gap="sm">
      <Text weight="semibold" color={NAVY} size="footnote">How will it be filed?</Text>
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

  return { rule, eyebrow, heading, pill, button, lone, actions, link, links, header, title, crumbs, pillOf, tabs, card, section, barCard, columns, disclosure, row, numbered, field, savedMark, status, version, page, body, subpage, matterPage, confirmBox, choice, chips, caseChooser, postureChips, filingChoices, howItWorks }
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
