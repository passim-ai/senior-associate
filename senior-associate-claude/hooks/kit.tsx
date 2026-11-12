// The frame every screen is drawn in, and the pieces they share: the header, the title, the matter's tabs, cards and
// rules, buttons and links, the message of the moment, and the main actions.
//
// The desktop draws each Button natively, in the app's colours, and shows only its label: a Button's children and any
// paint around it don't reach the screen. So every press here is a host Button and nothing else, its label the words
// it shows: primary (the app's main button), secondary (outlined), a link (plain) or quiet (plain and dim). Text and
// surfaces are the app's theme keys (theme.ts), so the panel reads in a light or a dark theme. Two more rules of the
// desktop's layout shape the pieces below: a Box with a border gets padding unless it sets its own, so a rule is a
// bordered Box with no height and no padding; and a text in a row can be squeezed into a sliver, so whatever sits
// beside something else may shrink (minWidth 0) and the row wraps.
import type { Elements, EngineInterface, ResolveInput } from 'claude-code'
import type { Card, Check, Draft, Note, Payload, Prefs, Run, Setup, View } from '../types'
import { WORDMARK, WORDMARK_RATIO } from './brand'
import { COMMON_TYPES, shownName } from './matter'
import { askClaude, perform } from './perform'
import { session, setNote, typed } from './state'
import { matterStatus } from './status'
import { ACCENT, ACCENT_TEXT, CARD, HEAD, MUTED, OK, TONE, WARN } from './theme'
import type { Tone } from './theme'
import { ASK_LABEL, nowMs } from './words'

type Table = Elements['desktop']

export type Els = Pick<Table, 'Box' | 'Text' | 'Button' | 'Input'> & {
  isDesktop: boolean
  /** The panel is narrow (the side panel at its usual width): headers stack and columns fold into one. */
  narrow: boolean
  svg: (source: string, alt: string, width?: number, height?: number) => JSX.Element | null
}

// One main action of a screen, or its companion: a primary and a secondary button, each with a line under it on what
// it does ("About 1–1½ hours · runs in the background").
export type ActionButton = { id: string; label: string; kind: 'primary' | 'secondary'; detail?: string; hotkey?: string }

// Below this many columns the panel is drawn narrow. The desktop reports the side panel's width in cells of its code
// font (about 8 pixels each), so this is about 560 pixels.
export const NARROW_COLUMNS = 72

// The element table for the surface the app is drawn on; null where it cannot be drawn. `columns` is how wide the
// site is, in cells, where the surface said.
export function tableFor($: EngineInterface, e: ResolveInput, columns?: number): Els | null {
  const narrow = typeof columns === 'number' && columns > 0 && columns < NARROW_COLUMNS
  if (e.surface === 'desktop') {
    const t = $.ui.resolve({ ...e, surface: 'desktop' as const })
    const { Svg } = t
    return {
      Box: t.Box, Text: t.Text, Button: t.Button, Input: t.Input,
      isDesktop: true,
      narrow,
      svg: (source, alt, width, height) => <Svg source={source} alt={alt} width={width} height={height} />,
    }
  }
  if (e.surface === 'terminal') {
    const t = $.ui.resolve({ ...e, surface: 'terminal' as const })
    return { Box: t.Box, Text: t.Text as Table['Text'], Button: t.Button, Input: t.Input, isDesktop: false, narrow, svg: () => null }
  }
  return null
}

export type Kids = (JSX.Element | null | false | undefined)[]

// The matter's tabs, each the view it shows and the key that opens it. The Timeline is a screen of the matter's too,
// reached from Matter details on the Overview: looked at rarely, it has no tab of its own.
export type Tab = 'matter' | 'documents' | 'items' | 'packet' | 'memo' | 'timeline'
const TABS: { tab: Tab; key: string; id: string; label: string }[] = [
  { tab: 'matter', key: 'nav-matter', id: 'matter', label: 'Overview' },
  { tab: 'documents', key: 'docs', id: 'docs', label: 'Documents' },
  { tab: 'items', key: 'items', id: 'items', label: 'Questions' },
  { tab: 'packet', key: 'packet', id: 'packet', label: 'Packet' },
  { tab: 'memo', key: 'memo', id: 'memo', label: 'Memo & request' },
]

// What the Questions tab holds open: the open items and the questions Claude asked, counted once each.
export function questionCount(c: Card): number {
  const keys = new Set<string>((c.open_items?.open ?? []).map(it => it.id))
  for (const n of c.needs_you) if (n.who !== 'system') keys.add(n.key)
  return keys.size
}

export function makeKit($: EngineInterface, els: Els, site: 'pane' | 'inline', v: View, p: Payload | null, n: Note, b: boolean, allRuns: Record<string, Run>, st: Setup | null, demo = false) {
  const { Box, Text, Button, Input, isDesktop, narrow } = els

  // ----- rules, labels and chips -----

  // A thin line: a bordered Box with no height and no padding (across a column), or no width (down a row). With no
  // colour it is the app's faint border.
  const rule = (key: string, color?: string) => <Box key={key} height={0} padding={0} borderStyle="single" borderColor={color} />
  const upright = (key: string) => <Box key={key} width={0} height={1} padding={0} borderStyle="single" />

  // A small label above a heading: "NEXT STEP", "YOUR FIRST MATTER".
  const eyebrow = (text: string, key = 'eyebrow') => <Text key={key} size="caption" weight="semibold" color={ACCENT_TEXT}>{text.toUpperCase()}</Text>

  // A heading inside a page.
  const heading = (text: string, key?: string, size: 'heading' | 'body' = 'heading') => <Text key={key ?? `h-${text}`} size={size} weight="semibold" color={HEAD}>{text}</Text>

  // A chip: a status, a count, outlined and lettered in its tone's colour.
  const pill = (label: string, tone: Tone, key = 'pill') => (
    <Box key={key} flexDirection="row" flexShrink={0}>
      <Box borderStyle="round" borderColor={TONE[tone]} paddingX="sm" paddingY={0}>
        <Text color={TONE[tone]} weight="semibold" size="caption">{label}</Text>
      </Box>
    </Box>
  )

  // ----- buttons -----

  type Look = 'primary' | 'secondary' | 'link' | 'quiet'
  // A press, in one of four looks: the app's main button, its outlined one, plain text (a link), or plain dim text.
  const button = (key: string, label: string, onPress: (press: { surface?: string }) => void, look: Look = 'link', o: { hotkey?: string; autoFocus?: boolean } = {}) => {
    const press = (e: unknown) => onPress(e as { surface?: string })
    const plain = look === 'link' || look === 'quiet' ? true : undefined
    // While a press is on its way, the main button dims.
    const dim = look === 'quiet' || (b && look === 'primary') ? true : undefined
    return <Button key={key} label={label} plain={plain} variant={look === 'primary' || look === 'secondary' ? look : undefined} dimColor={dim} hotkey={o.hotkey} autoFocus={o.autoFocus ? true : undefined} onPress={press} />
  }
  // A button on a line of its own, not stretched across the page.
  const lone = (key: string, el: JSX.Element) => <Box key={`lone:${key}`} flexDirection="row">{el}</Box>

  // The main action(s) of a screen: primary first. `main` marks the matter page's card, whose first action the b key
  // presses and where the focus starts.
  const actions = (buttons: ActionButton[], main = false) => (
    <Box key="actions" flexDirection="row" flexWrap="wrap" columnGap="lg" rowGap="md" alignItems="flex-start">
      {buttons.map((a, i) => (
        <Box key={`action-${a.id}`} flexDirection="column" gap="xs" flexShrink={1} minWidth={0}>
          {lone(`action-${a.id}`, button(`main:${a.id}`, a.label, () => { void perform($, a.id) }, a.kind, { hotkey: a.hotkey ?? (main && i === 0 ? 'b' : undefined), autoFocus: main && i === 0 }))}
          {a.detail ? <Text color={MUTED} size="caption">{a.detail}</Text> : null}
        </Box>
      ))}
    </Box>
  )

  // A text press: plain, or dim when it's one of the lesser ones.
  const link = (key: string, label: string, onPress: (press: { surface?: string }) => void, strong = false) =>
    button(key, label, onPress, strong ? 'link' : 'quiet')
  const links = (key: string, items: (JSX.Element | null | false)[]) => {
    const shown = items.filter(Boolean)
    return shown.length ? <Box key={key} flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">{shown}</Box> : null
  }

  // Something you can be on (a tab, a place in the header): the label in full where you are and dim elsewhere, with
  // the accent under the one you're on.
  const place = (key: string, label: string, id: string, here: boolean) => (
    <Box key={`place:${key}`} flexDirection="column" gap="xs">
      <Button key={key} label={label} plain dimColor={here ? undefined : true} onPress={() => { void perform($, id) }} />
      {here ? rule(`place-line:${key}`, ACCENT) : null}
    </Box>
  )

  // ----- the header: Passim's lockup, and the places every screen can go -----

  // On a matter's screens the header holds the way back and Help, and the matter's tabs do the rest; elsewhere it
  // holds Matters, Your details and Help. Setup is under Help (Check my setup), and shows by itself when it is needed.
  const matterViews: View[] = ['matter', 'documents', 'packet', 'items', 'memo', 'request', 'redo', 'intake', 'timeline']
  const onMatter = matterViews.includes(v) && Boolean(p?.matter)
  const nav = (
    <Box key="nav" flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="flex-start">
      {place('nav-all', onMatter ? '‹ Matters' : 'Matters', 'all', !onMatter && (v === 'home' || v === 'new' || v === 'welcome'))}
      {onMatter ? null : place('profile', 'Your details', 'profile', v === 'profile')}
      {place('help', 'Help', 'help', v === 'help' || v === 'setup')}
      {site === 'inline' ? place('dock', 'Open as side panel', 'dock', false) : null}
    </Box>
  )
  const markWidth = narrow ? 92 : 108
  const lockup = (
    <Box key="lockup" flexDirection="row" alignItems="center" gap="md" flexShrink={0}>
      {els.svg(WORDMARK, 'Passim', markWidth, Math.round(markWidth * WORDMARK_RATIO))}
      {isDesktop ? upright('lockup-line') : null}
      <Text size="footnote" weight="semibold" color={MUTED}>Immigration Packet Builder</Text>
    </Box>
  )
  const header = (
    <Box key="header" flexDirection="column">
      <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" rowGap="sm" columnGap="lg" paddingX={narrow ? 'lg' : 'xl'} paddingY="md">
        {lockup}
        {nav}
      </Box>
      {rule('header-rule')}
    </Box>
  )

  // ----- the title of a screen, and where it sits -----

  // The page's title, a line under it, and what sits at its right (a status, New matter).
  const title = (text: string, sub?: string | null, right?: JSX.Element | null) => (
    <Box key="title" flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="flex-start" columnGap="lg" rowGap="sm">
      <Box flexDirection="column" gap="xs" flexShrink={1} minWidth={0}>
        <Text size="title" weight="semibold" color={HEAD}>{text}</Text>
        {sub ? <Text color={MUTED}>{sub}</Text> : null}
      </Box>
      {right ?? null}
    </Box>
  )

  // Where you are: "Matters › Garcia I-130 I-485", each place before the last a press.
  const crumbs = (items: ({ key: string; label: string; id: string } | string)[]) => (
    <Box key="crumbs" flexDirection="row" flexWrap="wrap" alignItems="center" columnGap="xs">
      {items.flatMap((it, i) => [
        i > 0 ? <Text key={`sep-${i}`} size="footnote" color={MUTED}>›</Text> : null,
        typeof it === 'string'
          ? <Text key={`here-${i}`} size="footnote" color={MUTED}>{it}</Text>
          : <Button key={it.key} label={it.label} plain onPress={() => { void perform($, it.id) }} />,
      ])}
    </Box>
  )

  // The chip on a matter's screens: the same word the matter page and the list use.
  const pillOf = (c: Card) => {
    const s = matterStatus(c, allRuns[c.path], nowMs())
    return { label: s.label, tone: s.tone }
  }

  // The matter's tabs, Documents with how many there are and Questions with how many are open, and a line under them.
  const tabs = (c: Card, active: Tab) => {
    const count = questionCount(c)
    const label = (t: (typeof TABS)[number]) =>
      t.tab === 'items' && count ? `${t.label} · ${count}` : t.tab === 'documents' && c.documents.count ? `${t.label} · ${c.documents.count}` : t.label
    return (
      <Box key="tabs" flexDirection="column" gap="xs">
        <Box flexDirection="row" flexWrap="wrap" columnGap={narrow ? 'sm' : 'md'} rowGap="sm" alignItems="flex-start">
          {TABS.map(t => place(t.key, label(t), t.id, t.tab === active))}
        </Box>
        {rule('tabs-rule')}
      </Box>
    )
  }

  // ----- containers -----

  // A card: the app's raised surface inside its faint border; a border colour marks one that needs attention.
  const card = (heading: string | null, children: Kids, borderColor?: string, key?: string) => (
    <Box key={key ?? `card-${heading ?? 'plain'}`} flexDirection="column" backgroundColor={CARD} borderStyle="round" borderColor={borderColor} paddingX={narrow ? 'lg' : 'xl'} paddingY="lg" gap="md">
      {heading ? <Text size="heading" weight="semibold" color={HEAD}>{heading}</Text> : null}
      {children}
    </Box>
  )

  // A section on the page itself, with no card: its heading, then its content.
  const section = (heading: string | null, children: Kids, key?: string, right?: JSX.Element | null) => (
    <Box key={key ?? `sec-${heading ?? 'plain'}`} flexDirection="column" gap="md">
      {heading
        ? <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="md" rowGap="xs">
            <Text size="heading" weight="semibold" color={HEAD}>{heading}</Text>
            {right ?? null}
          </Box>
        : null}
      {children}
    </Box>
  )

  // A card with a coloured bar down its left edge: the matter's next step, the message of the moment.
  const barCard = (key: string, bar: string, children: Kids, pad: 'lg' | 'sm' = 'lg') => (
    <Box key={key} flexDirection="row" backgroundColor={CARD} borderStyle="round" padding={0} overflow="hidden">
      <Box backgroundColor={bar} paddingLeft="xs" />
      <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} paddingX={narrow || pad === 'sm' ? 'lg' : 'xl'} paddingY={pad} gap={pad === 'sm' ? 'sm' : 'md'}>
        {children}
      </Box>
    </Box>
  )

  // Columns side by side when the panel is wide, one above the other when it is narrow.
  const columns = (key: string, cols: Kids) => (
    <Box key={key} flexDirection={narrow ? 'column' : 'row'} flexWrap="wrap" columnGap="xl" rowGap="lg" alignItems="flex-start">
      {cols.filter(Boolean).map((col, i) => (
        <Box key={`${key}-col-${i}`} flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} width={narrow ? '100%' : `${Math.floor(94 / Math.max(1, cols.filter(Boolean).length))}%`}>
          {col}
        </Box>
      ))}
    </Box>
  )

  // A section folded under its title: ▸ closed, ▾ open. `id` is what the press toggles (the expanded list's key).
  const disclosure = (id: string, label: string, hint: string, isOpen: boolean, children: Kids) => (
    <Box key={`disc-${id}`} flexDirection="column" gap="md">
      <Box flexDirection="row" flexWrap="wrap" columnGap="sm" alignItems="center">
        <Button key={id} label={`${isOpen ? '▾' : '▸'} ${label}`} plain onPress={() => { void perform($, id) }} />
        {hint ? <Text size="footnote" color={MUTED}>{hint}</Text> : null}
      </Box>
      {isOpen ? <Box flexDirection="column" gap="md" paddingLeft="lg">{children}</Box> : null}
    </Box>
  )

  // A matter on the list: its name and status chip, what's next under them, and Open at the right (below, when
  // narrow). A row has no card of its own: `rows` puts a group's rows on one card, a thin line between them.
  const row = (key: string, id: string, main: string, detail: string, badge?: { label: string; tone: Tone }, hotkey?: string, press = 'Open') => (
    <Box key={key} flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="lg" rowGap="xs" paddingY="sm">
      <Box flexDirection="column" gap="xs" flexGrow={1} flexShrink={1} minWidth={0}>
        <Box flexDirection="row" flexWrap="wrap" columnGap="sm" rowGap="xs" alignItems="center">
          <Text weight="semibold" color={HEAD}>{main}</Text>
          {badge ? pill(badge.label, badge.tone, `${key}-pill`) : null}
        </Box>
        {detail ? <Text color={MUTED} size="footnote">{detail}</Text> : null}
      </Box>
      <Button key={id} label={press} hotkey={hotkey} onPress={() => perform($, id)} />
    </Box>
  )
  const rows = (key: string, items: (JSX.Element | null)[]) => {
    const shown = items.filter((it): it is JSX.Element => Boolean(it))
    return shown.length
      ? <Box key={key} flexDirection="column" backgroundColor={CARD} borderStyle="round" paddingX={narrow ? 'lg' : 'xl'} paddingY="xs">
          {shown.flatMap((it, i) => (i ? [rule(`${key}-rule-${i}`), it] : [it]))}
        </Box>
      : null
  }

  // A numbered step: 01, 02, 03 in the accent, a short title, a line on what it means.
  const numbered = (num: string, heading: string, text: string) => (
    <Box key={`step-${num}`} flexDirection="row" gap="md" alignItems="flex-start">
      <Box flexDirection="row" flexShrink={0}><Text size="heading" weight="semibold" color={ACCENT_TEXT} tabular>{num.padStart(2, '0')}</Text></Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
        <Text weight="semibold" color={HEAD}>{heading}</Text>
        <Text size="footnote">{text}</Text>
      </Box>
    </Box>
  )

  // A text field with its label. The desktop draws an Input's own label beside the field, squeezing it in a narrow
  // panel, so there the label goes above and the field takes the full width; the terminal draws it with the field.
  const field = (label: string, input: (label?: string) => JSX.Element, key?: string) => (
    <Box key={key ?? `field-${label}`} flexDirection="column" gap="xs">
      {isDesktop ? <Text size="footnote" weight="medium">{label}</Text> : null}
      {input(isDesktop ? undefined : label)}
    </Box>
  )

  // Under the box whose save was just pressed, so the press visibly lands; gone once its text changes or the screen does.
  const savedMark = (key: string, unchanged: boolean) =>
    session.savedField === key && unchanged ? <Box key={`saved:${key}`} flexDirection="row"><Text color={OK} weight="medium">✓ Saved</Text></Box> : null

  // The message of the moment, at the top of the page where the eye is, until it's dismissed or the screen changes.
  const toneBar = n.tone === 'wait' ? TONE.info : n.tone === 'ok' ? TONE.ok : TONE.warn
  const status = n.text
    ? barCard('note', n.tone === 'wait' ? ACCENT : n.tone === 'ok' ? '#3E8E4F' : '#C9A13B', [
        <Box key="note-line" flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="flex-start" justifyContent="space-between">
          <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
            <Text color={n.tone === 'wait' ? undefined : toneBar} weight={n.tone === 'ok' ? 'semibold' : 'regular'}>{`${n.tone === 'ok' ? '✓' : n.tone === 'wait' ? '⏳' : '⚠'} ${n.text}`}</Text>
            {links('note-acts', [
              n.ask ? button('note-ask', ASK_LABEL, () => { void askClaude($, n.ask!) }, 'link') : null,
              n.press ? button(`note-press:${n.press.id}`, n.press.label, () => { void perform($, n.press!.id) }, 'link') : null,
            ])}
          </Box>
          {button('dismiss-note', 'Dismiss', () => { void setNote($, '') }, 'quiet')}
        </Box>,
      ], 'sm')
    : null

  const version = p?.version || st?.version || ''

  // A screen: the header, then its head (where you are, the title, the tabs), the message of the moment, and its body.
  // While the demo is on, every screen says so under the header, with the way out.
  const demoBar = demo
    ? <Box key="demo-bar" flexDirection="column">
        <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="lg" rowGap="xs" backgroundColor={CARD} paddingX={narrow ? 'lg' : 'xl'} paddingY="sm">
          <Box flexDirection="column" flexShrink={1} minWidth={0}>
            <Text size="footnote" weight="medium">Demo. Only the fictional sample matter is shown; your own matters are not.</Text>
          </Box>
          {button('leave-demo', 'Leave the demo', () => { void perform($, 'leave-demo') }, 'link')}
        </Box>
        {rule('demo-rule')}
      </Box>
    : null

  const page = (head: Kids, ...children: Kids) => (
    <Box flexDirection="column" flexGrow={1}>
      {header}
      {demoBar}
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

  // A screen reached from another: the way back, the title, the body. Where the way back is Matters, the header
  // already holds it.
  const subpage = (o: { title: string; subtitle?: string; status?: { label: string; tone: Tone }; back: { id: string; label: string }; here: string; foot?: string | null }, ...children: Kids) =>
    page(
      [
        o.back.id === 'all' ? null : lone(`back-${o.back.id}`, button(`nav-${o.back.id}`, `‹ ${o.back.label}`, () => { void perform($, o.back.id) }, 'quiet')),
        title(o.title, o.subtitle, o.status ? pill(o.status.label, o.status.tone, 'title-pill') : null),
      ],
      body(...children),
    )

  // One of the matter's screens: its name and case, its status, the tabs, then the body. The way back to Matters is
  // in the header.
  const matterPage = (c: Card, tab: Tab, ...children: Kids) => {
    const s = pillOf(c)
    return page(
      [
        title(shownName(c), [c.case_line, c.intake.filing_posture_label].filter(Boolean).join(' · '), pill(s.label, s.tone, 'title-pill')),
        tabs(c, tab),
      ],
      body(...children),
    )
  }

  // A press that waits on "Yes" first, asked on the page: what happens, the press that does it, and the way out.
  const confirmBox = (key: string, text: string, yes: { id: string; label: string }, keep: string) =>
    barCard(`${key}-ask`, '#C9A13B', [
      <Text key="ask-text">{text}</Text>,
      <Box key="ask-acts" flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">
        {button(yes.id, yes.label, () => { void perform($, yes.id) }, 'secondary')}
        {button(`${key}-keep`, keep, () => { void perform($, 'confirm-no') }, 'quiet')}
      </Box>,
    ], 'sm')

  // A choice in a list: ● the chosen one, ○ the others, each the whole press, with a hint under it.
  const choice = (key: string, id: string, label: string, hint: string, chosen: boolean) => (
    <Box key={key} flexDirection="column">
      {lone(id, <Button key={id} label={`${chosen ? '●' : '○'} ${label}`} plain dimColor={chosen ? undefined : true} onPress={() => perform($, id)} />)}
      {hint ? <Box flexDirection="column" paddingLeft="lg"><Text color={MUTED} size="footnote">{hint}</Text></Box> : null}
    </Box>
  )

  // Several short choices on one line (New filing or a response?): the chosen one the app's main button.
  const chips = (key: string, options: { id: string; label: string; chosen: boolean }[]) => (
    <Box key={key} flexDirection="row" flexWrap="wrap" columnGap="sm" rowGap="xs">
      {options.map(o => <Button key={o.id} label={o.label} variant={o.chosen ? 'primary' : undefined} onPress={() => perform($, o.id)} />)}
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
      missing ? <Text key="case-missing" color={WARN} weight="medium">{missing}</Text> : null,
      ...shown.map(t => choice(`type-${t.id}`, `type:${t.id}`, t.label, t.hint ?? '', d.typeId === t.id)),
      types.length > shown.length ? lone('more-types', button('more-types', `More case types (${types.length - shown.length}) ›`, () => { void perform($, 'more-types') }, 'link')) : null,
      choice('type-other', 'type:other', 'Something else', 'Describe it in a few words', d.typeId === 'other'),
      d.typeId === 'other'
        ? field('What is being filed, in your words', l => <Input key="other" label={l} placeholder="e.g. I-485 based on asylee status" submitLabel={other.submitLabel} value={typed.other || undefined} onInput={value => { typed.other = value }} onSubmit={value => { typed.other = value; other.onSubmit(value) }} />, 'field-other')
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
      <Text weight="semibold" color={HEAD} size="footnote">How will it be filed?</Text>
      {chips('methods', [
        { id: 'method:paper', label: 'On paper, by mail', chosen: (d.method ?? 'paper') === 'paper' },
        { id: 'method:online', label: 'Online, in a USCIS account', chosen: d.method === 'online' },
      ])}
    </Box>,
    byCase
      ? <Text key="protect-case">{'● This client is protected under 8 U.S.C. 1367 (VAWA, T or U). Their name and documents stay out of anything Claude looks up, and the forms use the safe mailing address.'}</Text>
      : <Box key="protect" flexDirection="column" gap="xs">
          {choice('protect-choice', 'protect:toggle', 'Protected client (8 U.S.C. 1367: VAWA, T or U)', 'Keeps their name and documents out of anything Claude looks up, and uses the safe mailing address.', Boolean(d.protect))}
        </Box>,
  ]

  const howItWorks = [
    numbered('1', 'Add your details', '2 minutes, once. Your name, firm and bar number go on the G-28, each form’s preparer section and the letter’s signature.'),
    numbered('2', 'Name the client and the case', 'Choose what is being filed: an I-130/I-485, an I-751, an N-400, or anything else.'),
    numbered('3', 'Add their documents', 'Pick files one at a time, or a whole folder. Claude works from copies; your originals stay where they are.'),
    numbered('4', 'Build the packet', 'A document review takes about 5–10 minutes; a full build about 1–1½ hours, in the background. Nothing is filed or sent: you get a draft to read.'),
  ]

  return { rule, eyebrow, heading, pill, button, lone, actions, link, links, header, title, crumbs, pillOf, tabs, card, section, barCard, columns, disclosure, row, rows, numbered, field, savedMark, status, version, page, body, subpage, matterPage, confirmBox, choice, chips, caseChooser, postureChips, filingChoices, howItWorks }
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
  /** Where case-law research stands now (server.ts researchCheck); null before anything has looked. */
  research: Check | null
}
