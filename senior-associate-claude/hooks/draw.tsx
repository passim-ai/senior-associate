// Drawing: read the session's values once, then hand the screen they call for everything it needs.
import type { EngineInterface } from 'claude-code'
import { makeKit } from './kit'
import type { Ctx, Els } from './kit'
import { profileIsEmpty } from './matter'
import { perform } from './perform'
import { documentsScreen } from './screens/documents'
import { helpScreen } from './screens/help'
import { homeScreen } from './screens/home'
import { intakeScreen } from './screens/intake'
import { itemsScreen } from './screens/items'
import { matterScreen } from './screens/matter'
import { memoScreen } from './screens/memo'
import { newMatterScreen } from './screens/new-matter'
import { packetScreen } from './screens/packet'
import { profileScreen } from './screens/profile'
import { redoScreen } from './screens/redo'
import { requestScreen } from './screens/request'
import { setupScreen } from './screens/setup'
import { timelineScreen } from './screens/timeline'
import { welcomeScreen } from './screens/welcome'
import { ensurePoll } from './runs'
import { load, refresh } from './server'
import { PANE, readAnswers, readBusy, readCaseMissing, readConfirm, readDocked, readDraft, readExpanded, readFilter, readGate, readNote, readPayload, readPrefs, readRedoAt, readRuns, readLaunching, readSetup, readSort, readView, session } from './state'
import { clockNow } from './words'
import { INK, LINE, NAVY, PAPER } from './theme'

export async function draw($: EngineInterface, els: Els, site: 'pane' | 'inline'): Promise<JSX.Element> {
  const { Box, Text, Button } = els
  await clockNow($)
  // docked is read so the inline rows redraw when the side panel opens.
  ensurePoll($)
  const [v, p, n, busy, allRuns, pr, q, d, savedAnswers, st, g, open, missingCase, , redoing, asked, sort, launching] = await Promise.all([
    readView($),
    readPayload($),
    readNote($),
    readBusy($),
    readRuns($),
    readPrefs($),
    readFilter($),
    readDraft($),
    readAnswers($),
    readSetup($),
    readGate($),
    readExpanded($),
    readCaseMissing($),
    readDocked($),
    readRedoAt($),
    readConfirm($),
    readSort($),
    readLaunching($),
  ])
  // The main actions wait while a Mac picker is open or a start is on its way.
  const b = busy || (Boolean(p?.matter) && launching.includes(p!.matter!.path))

  const kit = makeKit($, els, site, v, p, n, b, allRuns, st)
  const { page, title, actions } = kit
  // ----- opening -----

  if (!p) {
    if (!b && n.text === '' && !session.kickoff) {
      session.kickoff = true
      $.clock.after(1, async () => {
        session.kickoff = false
        const first = await load($, { op: 'state' })
        if (first?.archived_count) await refresh($)
      })
    }
    return page(
      [title('Senior Associate', n.text ? 'It couldn’t open this time.' : 'One moment…')],
      n.text !== '' ? actions([{ id: 'retry', label: 'Try again', kind: 'primary' }]) : null,
    )
  }

  const folder = p.matters_root || session.config.matters_root
  const noProfile = profileIsEmpty(p)

  // Inline in the conversation while the side panel is open: one line pointing there, not a second copy of the app.
  if (site === 'inline') {
    let paneUp = false
    try {
      paneUp = (await $.ui.panes()).some(pane => pane.id === PANE && pane.isPlaced)
    } catch {
      paneUp = false
    }
    if (paneUp) {
      return (
        <Box flexDirection="row" flexWrap="wrap" columnGap="lg" alignItems="center" backgroundColor={PAPER} borderStyle="round" borderColor={LINE} paddingX="lg" paddingY="sm">
          <Text color={INK}>Senior Associate is open beside the chat.</Text>
          <Button key="show-pane" plain onPress={() => perform($, 'dock')}><Text weight="medium" color={NAVY}>Show it</Text></Button>
        </Box>
      )
    }
  }
  const tip = site === 'inline' && pr.inlineUses <= 2
    ? <Text key="tip" dimColor size="footnote">Tip: Open as side panel keeps this beside your chat while Claude works.</Text>
    : null

  const x: Ctx = { ...els, ...kit, site, v, p, n, b, allRuns, pr, q, d, savedAnswers, st, g, open, missingCase, redoing, asked, folder, noProfile, tip, sort }
  if (v === 'setup') return setupScreen($, x)
  if (v === 'welcome') return welcomeScreen($, x)
  if (v === 'help') return helpScreen($, x)
  if (v === 'profile') return profileScreen($, x)
  if (v === 'new') return newMatterScreen($, x)
  const c = p.matter
  if (v === 'documents' && c) return documentsScreen($, x, c)
  if (v === 'packet' && c) return packetScreen($, x, c)
  if (v === 'items' && c) return itemsScreen($, x, c)
  if (v === 'memo' && c) return memoScreen($, x, c)
  if (v === 'request' && c) return requestScreen($, x, c)
  if (v === 'redo' && c) return redoScreen($, x, c)
  if (v === 'intake' && c) return intakeScreen($, x, c)
  if (v === 'timeline' && c) return timelineScreen($, x, c)
  if (v === 'matter' && c) return matterScreen($, x, c)
  return homeScreen($, x)
}
