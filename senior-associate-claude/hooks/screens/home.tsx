// Matters: where everything stands, or start another. The list opens with its groups folded, a count for each, so
// no client's name is on screen until the attorney asks for one: Show opens a group, and typing in Find a matter shows
// only what matches.
import type { EngineInterface } from 'claude-code'
import type { MatterRow } from '../../types'
import type { Ctx } from '../kit'
import { FEW, MANY, requiredMissing, shownName } from '../matter'
import { perform } from '../perform'
import { PANE, updateFilter } from '../state'
import { GROUP_TITLE, matterStatus } from '../status'
import type { Group, MatterStatus } from '../status'
import { nowMs, plural, when } from '../words'
import { ACCENT, WARN, MUTED, HEAD } from '../theme'

// The list's orders, by the words its chooser shows. Rows stay in their status groups; the order is within each.
export const SORTS: { id: string; label: string }[] = [
  { id: 'updated', label: 'Updated' }, { id: 'name', label: 'Name' }, { id: 'case', label: 'Case type' }, { id: 'status', label: 'Status' },
]
// Within a group, by status: what needs the most attention first.
const STATUS_ORDER = ['stopped', 'starting', 'needs_you', 'building', 'draft', 'waiting_client', 'paused', 'reviewed', 'ready', 'new', 'complete', 'filed']
const GROUP_ORDER: Group[] = ['needs_you', 'working', 'preparing', 'ready', 'filed']

// The press that shows or hides a group. Filed keeps the key it always had; the others are `grp:<group>`.
export const groupKey = (g: Group) => (g === 'filed' ? 'filed-group' : `grp:${g}`)

export function sortRows(rows: { m: MatterRow; s: MatterStatus }[], sort: string): { m: MatterRow; s: MatterStatus }[] {
  const byName = (a: MatterRow, b: MatterRow) => shownName(a).localeCompare(shownName(b), undefined, { sensitivity: 'base' })
  const byUpdated = (a: MatterRow, b: MatterRow) => b.updated_at.localeCompare(a.updated_at) || byName(a, b)
  return [...rows].sort((x, y) => {
    if (sort === 'name') return byName(x.m, y.m)
    if (sort === 'case') return x.m.case_line.localeCompare(y.m.case_line, undefined, { sensitivity: 'base' }) || byName(x.m, y.m)
    if (sort === 'status') return (STATUS_ORDER.indexOf(x.s.phase) - STATUS_ORDER.indexOf(y.s.phase)) || byUpdated(x.m, y.m)
    return byUpdated(x.m, y.m)
  })
}

export async function homeScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  const { Box, Text, Input, site, p, allRuns, pr, q, st, open, actions, button, lone, title, card, barCard, row, page, body, field, folder, noProfile, tip, chips, sort } = x
  const now = nowMs()
  const everything = p.matters.map(m => ({ m, s: matterStatus(m, allRuns[m.path], now) }))
  const live = everything.filter(r => !r.m.archived)
  const archived = everything.filter(r => r.m.archived)
  const needle = q.trim().toLowerCase()
  const matches = (m: MatterRow) => shownName(m).toLowerCase().includes(needle) || m.case_line.toLowerCase().includes(needle)
  const shown = sortRows(needle ? live.filter(r => matches(r.m)) : live, sort)
  const shownArchived = sortRows(needle ? archived.filter(r => matches(r.m)) : archived, sort)

  // What to do with a matter, in a few words: the server's line for its own status, the app's for what only it knows.
  const nextStep = (m: MatterRow, s: MatterStatus): string => {
    if (s.phase === 'building') return s.run?.step ? s.run.step.replace(/:.*$/, '') : m.running_line
    if (s.phase === 'starting') return 'Press Enter in the chat box to start'
    if (s.phase === 'stopped') return 'Open it to try again'
    if (s.phase === 'filed') return m.filed_at ? `Filed ${when(m.filed_at)}` : 'Filed'
    return m.next_line
  }
  // The first nine rows on screen answer the keys 1 to 9, in the order they are drawn.
  let numberKey = 0
  const rowFor = ({ m, s }: { m: MatterRow; s: MatterStatus }) => {
    numberKey += 1
    // A matter the server can't read: what happened, and Claude to repair it, instead of a page that can't open.
    if (m.problem) {
      return row(`m-${m.path}`, m.ask ? `ask-row:${m.path}` : `open:${m.path}`, shownName(m), [m.next_line, m.ask ? `Press to have Claude repair it.` : ''].filter(Boolean).join(' '), { label: s.label, tone: s.tone }, undefined, m.ask ? 'Repair' : 'Open')
    }
    return row(
      `m-${m.path}`,
      `open:${m.path}`,
      shownName(m),
      [m.case_line, nextStep(m, s), m.updated_at ? `updated ${when(m.updated_at)}` : ''].filter(Boolean).join(' · '),
      { label: s.label, tone: s.tone },
      site === 'pane' && numberKey <= 9 ? String(numberKey) : undefined,
    )
  }

  // Your details (in the header), with a gentle nudge here until they're filled in.
  const detailsLink = noProfile
    ? <Box key="details" flexDirection="row" columnGap="sm" rowGap="xs" flexWrap="wrap" alignItems="center">
        {button('details-nudge', 'Add your details', () => { void perform($, 'profile') }, 'link')}
        <Text color={MUTED} size="footnote">so the G-28 and the letter carry your name and bar number</Text>
      </Box>
    : null
  const setupWarning = requiredMissing(st).length
    ? <Box key="setup-warn" flexDirection="row" columnGap="sm" rowGap="xs" flexWrap="wrap" alignItems="center">
        <Text color={WARN}>{`⚠ Immigration Packet Builder still needs ${requiredMissing(st).map(m => m.label).join(', ')} on this Mac.`}</Text>
        {button('setup-link', 'Check my setup', () => { void perform($, 'setup') }, 'link')}
      </Box>
    : null

  const newMatter = { id: 'new', label: 'New matter', kind: 'primary' as const, detail: 'Start with the client’s name', hotkey: 'n' }
  if (everything.length === 0) {
    return page(
      [title('Matters', 'No matters yet.', actions([newMatter]))],
      tip,
      body(
        setupWarning,
        detailsLink,
        folder ? <Text key="where" dimColor size="footnote">Matters are kept in {folder}.</Text> : null,
      ),
    )
  }

  // The line under the title says what needs the attorney: questions only they can answer, a stop, a start waiting on their Enter.
  const count = (phase: string) => live.filter(r => r.s.phase === phase).length
  const summary = [
    count('needs_you') ? `${count('needs_you')} need${count('needs_you') === 1 ? 's' : ''} your answer` : '',
    count('stopped') ? `${count('stopped')} stopped` : '',
    count('starting') ? `${count('starting')} waiting for you` : '',
    count('building') ? `${count('building')} in progress` : '',
    count('complete') ? `${count('complete')} ready to file` : '',
  ].filter(Boolean).join(' · ') || plural(live.length, 'matter', 'matters')

  // Work Claude finished while the attorney was elsewhere. The notification named no one, and neither does this:
  // the press opens the matter it was about, the latest first.
  const unseen = live
    .map(r => ({ path: r.m.path, run: allRuns[r.m.path] }))
    .filter(u => u.run && (u.run.status === 'done' || u.run.status === 'failed') && u.run.seen === false)
    .sort((a, b) => (b.run!.endedAt ?? '').localeCompare(a.run!.endedAt ?? ''))
  const unseenCard = unseen.length
    ? barCard('card-unseen', ACCENT, [
        <Text key="unseen-text" weight="semibold" color={HEAD}>{unseen.length > 1
          ? `Claude finished or stopped work on ${unseen.length} matters since you last looked.`
          : unseen[0]!.run!.status === 'failed'
            ? 'Claude stopped partway through a matter since you last looked.'
            : 'Claude finished its work on a matter since you last looked.'}</Text>,
        lone('unseen-open', button('main:open-unseen', unseen.length > 1 ? 'Open the most recent' : 'Open it', () => { void perform($, `open:${unseen[0]!.path}`) }, 'primary')),
      ], 'sm')
    : null

  // The matter last opened, said by its case and where it stands, never by the client's name.
  const lastRow = !unseen.length && live.length > FEW && pr.lastMatter ? live.find(r => r.m.path === pr.lastMatter) ?? null : null
  const archivedOpen = open.includes('archived-group')

  // A group is folded until its Show is pressed; a search shows what matches wherever it sits.
  const isOpen = (g: Group) => open.includes(groupKey(g))
  const listed = GROUP_ORDER.filter(g => g !== 'filed' && shown.some(r => r.s.group === g))
  const someOpen = listed.some(isOpen)
  const allOpen = listed.length > 0 && listed.every(isOpen)
  const namesOnScreen = Boolean(needle) || someOpen

  const group = (g: Group) => {
    const rows = shown.filter(r => r.s.group === g)
    if (!rows.length) return null
    if (g === 'filed') {
      return (
        <Box key={`grp-${g}`} flexDirection="column" gap="sm">
          {lone('filed-group', button('filed-group', `${GROUP_TITLE[g]} (${rows.length}) ${isOpen(g) ? '⌄' : '›'}`, () => { void perform($, 'filed-group') }, 'link'))}
          {isOpen(g) || needle ? rows.map(rowFor) : null}
        </Box>
      )
    }
    // Folded: what the group is and how many are in it.
    if (!isOpen(g) && !needle) return row(`grp-${g}`, groupKey(g), GROUP_TITLE[g], plural(rows.length, 'matter', 'matters'), undefined, undefined, 'Show')
    return (
      <Box key={`grp-${g}`} flexDirection="column" gap="sm">
        <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="md" rowGap="xs">
          <Text size="heading" weight="semibold" color={HEAD}>{GROUP_TITLE[g]}</Text>
          {needle ? null : button(groupKey(g), 'Hide', () => { void perform($, groupKey(g)) }, 'quiet')}
        </Box>
        {rows.map(rowFor)}
      </Box>
    )
  }

  return page(
    [title('Matters', summary, actions([newMatter]))],
    tip,
    body(
      unseenCard,
      lastRow
        ? card('Pick up where you left off', [
            <Text key="last" color={MUTED} size="footnote">{[lastRow.m.case_line, lastRow.s.label, nextStep(lastRow.m, lastRow.s), lastRow.m.updated_at ? `updated ${when(lastRow.m.updated_at)}` : ''].filter(Boolean).join(' · ')}</Text>,
            lone('last-open', button(`main:open:${lastRow.m.path}`, 'Open it', () => { void perform($, `open:${lastRow.m.path}`) }, 'primary')),
          ], undefined, 'card-last')
        : null,
      setupWarning,
      detailsLink,
      live.length > MANY
        ? <Box key="find" flexDirection="column" gap="xs">
            {field('Find a matter', l => <Input key="search" label={l} placeholder="A client’s name or a case type" value={q || undefined} onInput={value => { void updateFilter($, () => value) }} onSubmit={value => { void updateFilter($, () => value) }} />)}
            {site === 'pane' ? lone('find-key', button('find-key', 'Press f to find a matter', () => { void $.ui.focus({ requestId: PANE, key: 'search' }).catch(() => undefined) }, 'quiet', { hotkey: 'f' })) : null}
          </Box>
        : null,
      // Whether names are on screen, and the press that shows or hides them all.
      listed.length && !needle
        ? <Box key="names" flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">
            <Text color={MUTED} size="footnote">{someOpen ? 'Client names are showing.' : 'Client names stay hidden until you show a group.'}</Text>
            {allOpen ? null : button('show-all', 'Show all', () => { void perform($, 'show-all') }, 'link')}
            {someOpen ? button('hide-all', 'Hide names', () => { void perform($, 'hide-all') }, 'link') : null}
          </Box>
        : null,
      namesOnScreen && live.length > 1
        ? <Box key="sort" flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">
            <Text color={MUTED} size="footnote">Sort:</Text>
            {chips('sort-chips', SORTS.map(s => ({ id: `sort:${s.id}`, label: s.label, chosen: sort === s.id })))}
          </Box>
        : null,
      <Box key="list" flexDirection="column" gap="lg">
        {needle && shown.length === 0 && shownArchived.length === 0 ? <Text dimColor>No matter matches “{q}”.</Text> : null}
        {GROUP_ORDER.map(group)}
        {shownArchived.length
          ? <Box key="grp-archived" flexDirection="column" gap="sm">
              {lone('archived-group', button('archived-group', `Archived (${shownArchived.length}) ${archivedOpen ? '⌄' : '›'}`, () => { void perform($, 'archived-group') }, 'link'))}
              {archivedOpen || needle ? shownArchived.map(rowFor) : null}
            </Box>
          : null}
      </Box>,
    ),
  )
}
