// The app against what the real server sends (finding 54): every golden payload from server/tools/golden_payloads.py
// (tests/golden.ts, written by tests/make-golden.sh), drawn the way the attorney meets it. Each matter shows the
// server's status in its words, nothing of a program's, every text in a paper colour of its own, and a way forward; the list puts
// each row in its group; a start uses the brief start_run sends back.
import type { On } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import { GOLDEN } from './golden'
import { GOOD_CHECKS, OPTS, PLUGIN, SEEN, answer, inActions, mount, offTheme, open } from './world'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Ui = any
const MATTERS = ['new', 'ready', 'reviewed', 'building', 'paused', 'needs_you', 'waiting_client', 'draft', 'complete', 'filed', 'damaged', 'protected', 'archived']

// The real server's answers: the state of the matter asked for (or the list), and the lease ops.
function golden(on: On, opened: string, spawned: { prompt?: string }[] = [], moved: string[] = []) {
  const requests: Record<string, unknown>[] = []
  const card = (path: unknown) => Object.values(GOLDEN).find(g => g.matter?.path === path) ?? GOLDEN['state-home']
  on('process.run', async (_$, e) => {
    const argv = e.argv as readonly string[]
    const request = JSON.parse(argv[argv.length - 1] ?? '{}') as Record<string, unknown>
    requests.push(request)
    if (moved.includes(String(request.matter_path))) return answer(GOLDEN['error-moved'], 1)
    switch (request.op) {
      case 'doctor': return answer({ checks: GOOD_CHECKS.map(c => ({ ...c, ok: true })), version: GOLDEN['state-home'].version })
      case 'list': return answer(GOLDEN[request.include_archived ? 'list-with-archived' : 'list'])
      case 'start_run': return answer(GOLDEN['start-run'])
      case 'heartbeat_run': return answer({ status: 'heartbeat', ok: true, lease: GOLDEN['start-run'].lease })
      case 'privacy_terms': return answer({ status: 'privacy_terms', terms: [], names: [], full_names: [], identifiers: [] })
      default: return answer(request.matter_path || request.matter ? card(request.matter_path ?? request.matter) : GOLDEN['state-home'])
    }
  })
  on('agent.spawn', async (_$, e) => { spawned.push(e as never); return { model: 'opus', agentId: 'agent-1' } })
  on('agent.list', async () => ({ value: [] }))
  on('fs.exists', async () => ({ value: true }))
  on('tool.list', async () => ({ value: [] }))
  on('ui.toast', async () => ({ value: undefined }))
  on('store.get', async (_$, e) => ({ value: e.key === 'prefs' ? { ...SEEN, lastMatter: opened } : undefined }))
  on('store.set', async () => ({ value: undefined }))
  return { requests, spawned }
}

// Every text on the page.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function texts(el: any, out: string[] = []): string[] {
  if (!el || typeof el !== 'object') return out
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  if (el.type === 'Text') out.push((el.children ?? []).map((c: any) => (typeof c === 'string' ? c : '')).join(''))
  for (const child of el.children ?? []) texts(child, out)
  return out
}

test('every matter the real server sends: its status in its words, nothing raw, everything in the app’s theme, a way forward', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  golden(on, '')
  const { ui, tap } = await mount($, clock)
  for (const name of MATTERS) {
    const c = GOLDEN[`matter-${name}`].matter
    await ui.press({ plugin: PLUGIN, key: 'nav-all' }).catch(() => undefined)
    await clock.settle()
    // Filed and archived matters wait, folded, at the foot of the list.
    for (const group of ['filed-group', 'archived-group']) {
      if (await ui.find({ type: 'Button', key: `open:${c.path}` })) break
      await ui.press({ plugin: PLUGIN, key: group }).catch(() => undefined)
      await clock.settle()
    }
    await tap(`open:${c.path}`)
    const page = await ui.drawn()
    const words = texts(page)
    expect([name, words.includes(c.status.label)]).toEqual([name, true])
    expect([name, offTheme(page)]).toEqual([name, []])
    expect([name, words.filter(t => /_|That didn’t work|Traceback|\{|\/Users\//.test(t))]).toEqual([name, []])
    // A way forward: a main action, Claude's work to watch or stop, or More you can do (folded until asked for).
    const forward = (await ui.findAll({ type: 'Button' })).some((b: { key?: string }) => /^(main:|do-|sec-more$|watch|stop|unmark-filed|ask-fix|not-working)/.test(b.key ?? ''))
    expect([name, forward]).toEqual([name, true])
  }
  await ui.unmount()
})

test('the real server’s matters, state by state: running steps, a stale lease, a list Claude can’t read, the client’s language', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  golden(on, '')
  const { ui, tap } = await mount($, clock)
  const visit = async (name: string) => {
    await ui.press({ plugin: PLUGIN, key: 'nav-all' }).catch(() => undefined)
    await clock.settle()
    await tap(`open:${GOLDEN[`matter-${name}`].matter.path}`)
  }
  // Claude works on it from the chat (a fresh lease held by the orchestrator): two steps side by side, nothing to start.
  await visit('building')
  expect(await ui.find({ type: 'Text', text: /^Building the packet · step 3 of 10: Forms review and Cover letter$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'continue-link' })).toBeUndefined()
  // The lease went stale (the app that held it stopped renewing it): paused, with Continue building.
  await visit('paused')
  expect(await ui.find({ type: 'Text', text: /^Paused$/ })).toBeDefined()
  expect(await inActions(ui, /^Continue building$/)).toBeDefined()
  // The open items list can't be read: said on the card, with Claude to rewrite it.
  await visit('damaged')
  expect(await ui.find({ type: 'Text', text: /^• Claude's list of open items can't be read\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'ask-fix:0' })).toBeDefined()
  // The client request in Spanish too: it can be copied in either language.
  await visit('draft')
  expect(await inActions(ui, /^2 needed before filing$/)).toBeDefined()
  // The research behind the letter, as the real server sums it up; no BIA Edge in this session, so nothing offers the check again.
  expect(await ui.find({ type: 'Text', text: /^Checked October 27, 2026 with BIA Edge$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Later treatment was checked for the case, and nothing adverse was found\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'research-recheck' })).toBeUndefined()
  await tap('memo')
  await tap('request')
  expect(await ui.find({ type: 'Button', key: 'main:copy-request-lang:Spanish' })).toBeDefined()
  await ui.unmount()
})

test('the real server’s list: each row in its group, archived ones folded at the foot', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  golden(on, '')
  const { ui } = await mount($, clock)
  await clock.advance(15000)
  await clock.settle()
  const rows = GOLDEN['list-with-archived'].matters
  for (const r of rows.filter((x: { archived?: boolean }) => !x.archived)) {
    const button = await ui.find({ type: 'Button', key: `open:${r.path}` })
    if (r.phase === 'filed') continue // folded under Filed
    expect([r.name, button?.props?.label]).toEqual([r.name, 'Open'])
    expect([r.name, Boolean(await ui.find({ type: 'Text', text: r.label }))]).toEqual([r.name, true])
  }
  expect(await ui.find({ type: 'Button', key: 'archived-group' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  await ui.unmount()
})

test('a start with the real server: the brief start_run sends back is the one the agent gets, run id and all', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const ready = GOLDEN['matter-reviewed'].matter
  const { spawned, requests } = golden(on, ready.path)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${ready.path}`)
  await tap('main:build')
  // No details in the fictional profile: Build says so first, and Build anyway goes on.
  if (await ui.find({ type: 'Button', key: 'main:gate-build' })) {
    await tap('main:gate-build')
  }
  expect(requests.find(r => r.op === 'start_run')).toMatchObject({ matter: ready.path, kind: 'build' })
  expect(spawned).toHaveLength(1)
  expect(String(spawned[0]!.prompt).startsWith(GOLDEN['start-run'].prompt)).toBe(true)
  expect(String(spawned[0]!.prompt)).toContain('Your run id is <run-id>.')
  await ui.unmount()
})

test('a matter moved in Finder, in the real server’s words: after two failed refreshes, the way back to Matters', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const ready = GOLDEN['matter-ready'].matter
  const moved: string[] = []
  golden(on, ready.path, [], moved)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${ready.path}`)
  moved.push(ready.path)
  for (let i = 0; i < 2; i++) {
    await clock.advance(15000)
    await clock.settle()
  }
  expect(await ui.find({ type: 'Text', text: `⚠ ${GOLDEN['error-moved'].error}` })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'note-press:all' })).toBeDefined()
  await ui.unmount()
})

// How much is on a matter's Overview, counted the way an attorney meets it: every word in a text or on a press, and
// every press. The ceilings sit a little above what each state carries now (1.5.0 carried a quarter more words and
// seven more presses), so words and buttons that creep back show up here.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function weight(el: any, m = { words: 0, buttons: 0 }) {
  if (!el || typeof el !== 'object') return m
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const own = (el.children ?? []).map((c: any) => (typeof c === 'string' ? c : '')).join('')
  const count = (t: string) => t.split(/\s+/).filter(w => /[A-Za-z0-9]/.test(w)).length
  if (el.type === 'Text') m.words += count(own)
  if (el.type === 'Button') { m.buttons += 1; m.words += count(String(el.props?.label ?? own)) }
  for (const child of el.children ?? []) weight(child, m)
  return m
}
const CEILING: Record<string, [words: number, buttons: number]> = {
  new: [225, 25], ready: [240, 26], reviewed: [245, 19], building: [175, 15], paused: [210, 16],
  needs_you: [210, 21], waiting_client: [170, 18], draft: [255, 21], complete: [360, 29], filed: [170, 19],
}

test('a matter’s Overview stays lean: one way back, five tabs, and no more words or presses than its ceiling', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  golden(on, '')
  const { ui, tap } = await mount($, clock)
  for (const [name, [words, buttons]] of Object.entries(CEILING)) {
    const c = GOLDEN[`matter-${name}`].matter
    await ui.press({ plugin: PLUGIN, key: 'nav-all' }).catch(() => undefined)
    await clock.settle()
    if (!(await ui.find({ type: 'Button', key: `open:${c.path}` }))) await tap('filed-group')
    await tap(`open:${c.path}`)
    const got = weight(await ui.drawn())
    expect([name, got.words <= words, got.buttons <= buttons, got]).toEqual([name, true, true, got])
    // The header holds the way back and Help; the matter's five tabs do the rest. No trail of crumbs, no Setup or
    // Your details up there, no Timeline tab.
    expect([name, (await ui.find({ type: 'Button', key: 'nav-all' }))?.props?.label]).toEqual([name, '‹ Matters'])
    for (const gone of ['profile', 'nav-setup', 'crumb-all', 'metric-docs']) expect([name, gone, await ui.find({ type: 'Button', key: gone })]).toEqual([name, gone, undefined])
    for (const tab of ['nav-matter', 'docs', 'items', 'packet', 'memo']) expect([name, tab, Boolean(await ui.find({ type: 'Button', key: tab }))]).toEqual([name, tab, true])
  }
  // Back on the list, the header is the list's: Matters, Your details, Help. Setup is under Help.
  await tap('nav-all')
  expect((await ui.find({ type: 'Button', key: 'nav-all' }))?.props?.label).toBe('Matters')
  expect(await ui.find({ type: 'Button', key: 'profile' })).toBeDefined()
  await tap('help')
  await tap('help-setup')
  expect(await ui.find({ type: 'Text', text: /^Getting set up$/ })).toBeDefined()
  await ui.unmount()
})
