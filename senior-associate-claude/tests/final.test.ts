// The last review's findings in the app, each as the attorney would meet it: a start waiting in the chat box that the
// list called Claude at work, a red Stopped while Claude worked from the chat, an Answer that found no box, a Ready to
// file matter that lost Mark as filed, a recommendation saved to the wrong question, research let through or refused
// by mistake, a start that never began said as a problem, a Cancel that failed silently, a damaged list read as none,
// a protected case named in the header, Help without its keys, and a run that looks alive when it isn't.
import { expect, test } from 'claude-code/testing'
import { holdsTerm, onlyCitations, readTerms, toolInput } from '../hooks/privacy'
import { matterStatus } from '../hooks/status'
import { ANA, DOCS, OPTS, SEEN, agents, boot, card, metaOf, mount, open, world } from './world'
import type { Matter, Options } from './world'


// A decision the packet can be filed without, as the server lists it once every step is done.
function withOptionalDecision(m: Matter) {
  const decision = m.open_items!.open.find(o => o.id === 'decide-i765')!
  m.needs_you = [...m.needs_you, { text: decision.question!, question: decision.question, kind: 'decision', who: 'attorney', id: decision.id, blocks_filing: false } as never]
  return m
}

const T0 = Date.parse('2026-10-29T10:00:00Z')
const run = (r: Record<string, unknown>) => ({ agentId: '', kind: 'build', matter: '/m/G', name: 'G', label: 'Building the packet', startedAt: '2026-10-29T10:00:00Z', endedAt: '', status: 'running', answer: '', reason: '', reply: '', step: '', stepLabel: '', lastSeen: '', lastChangeAt: '2026-10-29T10:00:00Z', waitingOk: false, ...r }) as never

test('a list row: the app’s own start waiting in the chat box is Waiting for you, and a run from the chat is never Stopped', () => {
  const row = { path: '/m/G', name: 'G', phase: 'building', label: 'Claude is working' }
  const waiting = run({ status: 'starting', runId: 'run-1' })
  const own = { run_id: 'run-1', holder: 'app', origin: 'app', started_at: '2026-10-29T10:00:00Z', fresh: true }
  expect(matterStatus({ ...row, lease: own }, waiting, T0 + 60000).label).toBe('Waiting for you')
  // Taken up by its orchestrator: Claude is at work.
  expect(matterStatus({ ...row, lease: { ...own, holder: 'orchestrator' } }, waiting, T0 + 60000).phase).toBe('building')
  // This session's run failed; then a run from the chat took the matter: the row says Claude is working.
  const failed = run({ status: 'failed', endedAt: '2026-10-29T10:20:00Z', reason: 'error' })
  expect(matterStatus(row, failed, T0 + 32 * 60000).phase).toBe('building')
  expect(matterStatus({ ...row, lease: { ...own, run_id: 'r2', holder: 'orchestrator', started_at: '2026-10-29T10:30:00Z' } }, failed, T0 + 32 * 60000).label).toBe('Claude is working')
  // A row the server doesn't call building still shows the stop.
  expect(matterStatus({ ...row, phase: 'paused', label: 'Paused' }, failed, T0 + 32 * 60000).phase).toBe('stopped')
})

test('a start waiting in the chat box reads Waiting for you on the matters list too', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const lopez = card('Lopez I-751', 'ready', DOCS)
  let box = ''
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: [] }))
  on('prompt.fill', async (_$, e) => { box = e.text; return { isFilled: true } })
  on('prompt.read', async () => ({ value: { text: box, cursor: box.length } }))
  const { clock, ui, tap } = await boot($, on, [garcia, lopez])
  await tap('main:build')
  await tap('nav-all')
  await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: `open:${garcia.path}` })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Waiting for you$/ })).toBeDefined()
  await ui.unmount()
})

for (const phase of ['draft', 'waiting_client'] as const) {
  test(`${phase === 'draft' ? 'a draft packet' : 'waiting on the client'} with a decision not needed before filing: its View finds its box on Questions`, OPTS(), async ($, on) => {
    const garcia = withOptionalDecision(card('Garcia I-130 I-485', phase, DOCS))
    if (phase === 'waiting_client') garcia.needs_you = [{ text: 'The I-94', question: 'The I-94', kind: 'client', who: 'client', id: 'doc-i94' }, ...garcia.needs_you]
    const { ui, tap } = await boot($, on, [garcia])
    expect(await ui.find({ type: 'Text', text: /^Your decision · Not needed before filing$/ })).toBeDefined()
    await tap('view:decide-i765')
    expect(await ui.find({ type: 'Text', text: /^Questions & missing evidence$/ })).toBeDefined()
    expect(await ui.find({ type: 'Text', text: /^Not needed before filing$/ })).toBeDefined()
    expect(await ui.find({ type: 'Input', key: 'answer-decide-i765' })).toBeDefined()
    await ui.unmount()
  })
}

test('ready to file with a file added since the build: Mark as filed and Print the filing checklist stay', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'complete', DOCS, { fresh: ['Lease 2026.pdf'] })
  ;(garcia.outputs as Record<string, unknown>).filing_checklist = { name: 'Filing Checklist.pdf', path: `${garcia.path}/output/deliverables/Filing Checklist.pdf` }
  const { ui, tap, requests } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^1 new file arrived since the packet was built\./ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'print-checklist' })).toBeDefined()
  await tap('mark-filed')
  expect(requests.some(r => r.op === 'mark_filed')).toBe(true)
  await ui.unmount()
})

test('Use the recommendation answers the question it sits under, even after the questions moved', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.needs_you = [
    { text: 'Include an I-765?', question: 'Include an I-765?', recommendation: 'Yes, include it.', kind: 'decision', who: 'attorney', id: 'd-765' },
    { text: 'Include an I-131?', question: 'Include an I-131?', recommendation: 'No, he has no travel plans.', kind: 'decision', who: 'attorney', id: 'd-131' },
  ]
  const { clock, ui, tap, matters, requests } = await boot($, on, [garcia])
  await tap('items')
  expect(await ui.find({ type: 'Button', key: 'rec:d-131' })).toBeDefined()
  // The I-765 question was settled in the chat, and a new one came first: the refresh lands before the press.
  matters[0]!.needs_you = [{ text: 'Which address?', question: 'Which address?', recommendation: 'The safe address.', kind: 'decision', who: 'attorney', id: 'd-addr' }, garcia.needs_you[1]!]
  await clock.advance(15000)
  await clock.settle()
  await tap('rec:d-131')
  expect(requests.filter(r => r.op === 'save_answer').map(r => [r.key, r.answer])).toEqual([['d-131', 'Go with your recommendation: No, he has no travel plans.']])
  await ui.unmount()
})

test('the research gate: an encoded name is the name; a date, a precedent with small words, a citation lookup are not the client', () => {
  const t = readTerms({ names: ['José', 'Núñez', 'Cruz'], full_names: ['José Núñez'], identifiers: ['1/2/2020', 'A201555019'] })
  expect(holdsTerm({ url: 'https://www.google.com/search?q=Jos%C3%A9+N%C3%BA%C3%B1ez+asylum+denial', prompt: 'Summarize the results' }, t)).toBe(true)
  expect(holdsTerm({ url: 'https://example.com/search?q=Jose%20Nunez%ZZ' }, t)).toBe(true) // a stray % never hides the rest
  expect(holdsTerm({ query: 'USCIS policy alert issued December 12, 2020 on public charge' }, t)).toBe(false)
  expect(holdsTerm({ query: 'born 1/2/2020' }, t)).toBe(true)
  expect(holdsTerm({ query: 'A 201 555 019 status' }, t)).toBe(true)
  expect(holdsTerm({ query: 'Matter of de la Cruz hardship standard' }, t)).toBe(false)
  expect(holdsTerm({ query: 'Matter of de la Cruz and our client Cruz' }, t)).toBe(true)
  // tool.call's event carries the call's envelope beside the tool's arguments; only the arguments are read.
  const event = { tool: 'mcp__biaedge__get_case_by_citation', tool_use_id: 'toolu_01ABCDEF', agentId: 'a1', citation: 'Matter of Garcia, 16 I&N Dec. 653 (BIA 1978)' }
  expect(toolInput(event)).toEqual({ citation: event.citation })
  expect(onlyCitations(toolInput(event))).toBe(true)
})

test('a start that never began is given back without saying Claude ran into a problem', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: [] }))
  on('prompt.fill', async () => ({ isFilled: false }))
  const { ui, tap, requests } = await boot($, on, [garcia])
  await tap('main:build')
  expect(requests.find(r => r.op === 'cancel_start')).toMatchObject({ run_id: 'run-1', why: 'not_started' })
  expect(requests.find(r => r.op === 'release_run')).toBeUndefined()
  await ui.unmount()
})

test('Cancel on a start waiting in the chat box says so when the server can’t take it back', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let box = ''
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: [] }))
  on('prompt.fill', async (_$, e) => { box = e.text; return { isFilled: true } })
  on('prompt.read', async () => ({ value: { text: box, cursor: box.length } }))
  const o: Options = {}
  const { ui, tap } = await boot($, on, [garcia], o)
  await tap('main:build')
  o.gone = [garcia.path]
  await tap('cancel-start')
  expect(await ui.find({ type: 'Text', text: /^⚠ The start wasn’t cancelled: / })).toBeDefined()
  await ui.unmount()
})

test('a list of open items that can’t be read says so on What’s left, with Claude to rewrite it', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  garcia.open_items = null
  ;(garcia as Matter & { open_items_state?: string }).open_items_state = 'damaged'
  const ask = 'Rewrite the open items list for Garcia I-130 I-485 from the review findings and the memo.'
  garcia.needs_you = [{ text: 'Claude’s list of open items can’t be read.', kind: 'setup', who: 'system', id: 'open-items-damaged', key: 'open-items-damaged', ask } as never]
  const { ui, tap, submitted } = await boot($, on, [garcia])
  await tap('main:items')
  expect(await ui.find({ type: 'Text', text: /^The list can’t be read$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Nothing listed yet$/ })).toBeUndefined()
  await tap('ask-rewrite')
  expect(submitted[0]).toMatch(/^Rewrite the open items list for Garcia I-130 I-485/)
  await ui.unmount()
})

test('a hot reload leaves nothing busy or starting', OPTS(), async ($, on) => {
  // What the session held before the reload: a server call in flight (busy) and a start being pressed (launching).
  // The module starts over, $.state doesn't; the test keeps those two values as the host would, versioned.
  const kept: Record<string, { value: unknown; version: number }> = {
    busy: { value: true, version: 1 },
    launching: { value: ['/matters/Garcia I-130 I-485'], version: 1 },
  }
  on('state.get', async (_$, e, next) => (kept[e.key] ? { value: kept[e.key] } as never : next(e)))
  on('state.set', async (_$, e, next) => {
    const k = kept[e.key]
    if (!k) return next(e)
    kept[e.key] = { value: (e as { value: unknown }).value, version: k.version + 1 }
    return { value: { isSet: true, version: kept[e.key]!.version } } as never
  })
  on('command.register', async () => ({ value: { command: 'matters' } }))
  on('session.start', async (_$, e) => ({ cwd: (e as { cwd: string }).cwd }))
  await open($, on)
  world(on, [], { prefs: { ...SEEN } }, { profile: ANA })
  await ($ as never as { session: { start: (e: unknown) => Promise<unknown> } }).session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  expect(kept.busy!.value).toBe(false)
  expect(kept.launching!.value).toEqual([])
})

test('a protected matter’s header names its forms only, as the list does', OPTS(), async ($, on) => {
  const ramos = card('Ramos I-360', 'ready', DOCS)
  ramos.intake = { ...ramos.intake, matter_type: 'I-360 VAWA self-petition packet', matter_type_label: 'I-360 VAWA self-petition' }
  Object.assign(metaOf(ramos), { protected: true, protected_reason: 'catalog' })
  const { ui } = await boot($, on, [ramos])
  expect(await ui.find({ type: 'Text', text: /^I-360 · New filing$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /VAWA/ })).toBeUndefined()
  await ui.unmount()
})

test('Help lists the keys; each problem has its own Done — check again', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.needs_you = [{ text: 'Install Ghostscript', kind: 'setup', who: 'system', id: 'sys-gs', fix: 'Claude can install Ghostscript for you.', ask: 'Install Ghostscript for Immigration Packet Builder.' }]
  const { ui, tap } = await boot($, on, [garcia])
  expect((await ui.find({ type: 'Button', key: 'check-again:0' }))?.props?.label).toBe('Done — check again')
  await tap('help')
  expect(await ui.find({ type: 'Text', text: /^Keyboard$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^b presses the matter’s main button\.$/ })).toBeDefined()
  await ui.unmount()
})

test('a run this session didn’t start looks alive but isn’t: the attorney lets the matter go, after saying so on the page', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'paused', DOCS, { stage: i => (i < 3 ? 'passed' : 'pending') })
  const { clock } = await open($, on)
  const w = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  const at = new Date().toISOString()
  w.leases[garcia.path] = { run_id: 'chat-1', kind: 'build', holder: 'orchestrator', origin: 'orchestrator', started_at: at, heartbeat_at: at, stage: null, fresh: true }
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  await tap('not-working')
  expect(await ui.find({ type: 'Text', text: /^Let go of this matter\?/ })).toBeDefined()
  expect(w.requests.some(r => r.op === 'abandon_run')).toBe(false)
  await tap('not-working-yes')
  expect(w.requests.find(r => r.op === 'abandon_run')).toMatchObject({ run_id: 'chat-1' })
  expect(await ui.find({ type: 'Text', text: /^✓ The matter is free again\./ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Paused$/ })).toBeDefined()
  await ui.unmount()
})

test('the app’s own run is never offered to be let go', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  agents(on, 'Building the packet: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia])
  await tap('main:build')
  expect(await ui.find({ type: 'Button', key: 'not-working' })).toBeUndefined()
  await ui.unmount()
})
