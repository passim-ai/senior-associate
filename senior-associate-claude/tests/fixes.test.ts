// The overhaul's fixes, each as the attorney would meet the bug it fixes: answers that bled between questions, a list
// that never refreshed, a double press that started two agents, a refresh that overwrote an action, raw review codes,
// counts that didn't add up, a moved folder that went silent, colours that vanished in the dark theme, controls a
// keyboard or a screen reader couldn't reach, and research that could carry a client's name.
import type { On } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import { ANA, DOCS, OPTS, PLUGIN, ROOT, SEEN, act, agents, boot, card, inActions, metaOf, mount, offTheme, open, unfold, world } from './world'
import type { Matter } from './world'


const complete = ($: unknown, e: Record<string, unknown>) => ($ as { turn: { complete: (x: unknown) => Promise<unknown> } }).turn.complete({ durationMs: 1000, isAborted: false, turnId: 't1', ...e })

test('answers to questions with empty ids stay in their own boxes, go to the matter, and only answered ones go with the update', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.open_items = null
  garcia.needs_you = [
    { text: 'Q one?', question: 'Q one?', kind: 'manual_review', who: 'attorney', id: '' },
    { text: 'Q two?', question: 'Q two?', kind: 'blocker', who: 'attorney', id: '' },
  ]
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { clock, ui, tap, requests } = await boot($, on, [garcia])
  await tap('items')
  const boxes = (await ui.findAll({ type: 'Input' })).filter((i: { key?: string }) => i.key?.startsWith('answer-'))
  expect(boxes).toHaveLength(2)
  expect(boxes[0].key).not.toBe(boxes[1].key)
  await ui.input({ plugin: PLUGIN, key: boxes[0].key, text: 'Only answering the first.', kind: 'submit' })
  await clock.settle()
  expect((await ui.find({ type: 'Input', key: boxes[1].key }))?.text).toBe('')
  // Kept in the matter, by the question's key, so quitting Claude doesn't lose it.
  expect(requests.find(r => r.op === 'save_answer')).toMatchObject({ key: boxes[0].key.slice('answer-'.length), question: 'Q one?', answer: 'Only answering the first.' })
  expect(await ui.find({ type: 'Text', text: /^Attorney decisions · 1 of 2 answered$/ })).toBeDefined()
  await tap('main:update')
  const prompt = String(run.spawned[0]!.prompt)
  expect(prompt).toContain('1. Q one?\n   Answer: Only answering the first.')
  expect(prompt).not.toContain('Q two?')
  await ui.unmount()
})

test('an answer the matter kept is in its box when the matter opens, with nothing typed this session', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.needs_you = [{ text: 'Include an I-765?', question: 'Include an I-765?', kind: 'decision', who: 'attorney', id: 'decide-i765', key: 'decide-i765' } as never]
  ;(garcia as Matter & { answers?: unknown }).answers = { 'decide-i765': { question: 'Include an I-765?', answer: 'Yes, include it.', saved_at: '2026-10-28T10:00:00Z' } }
  const { ui, tap } = await boot($, on, [garcia])
  await tap('items')
  expect((await ui.find({ type: 'Input', key: 'answer-decide-i765' }))?.text).toBe('Yes, include it.')
  await ui.unmount()
})

test('twelve and more questions: counted, those needed before filing first, each with its box on Questions', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.needs_you = Array.from({ length: 13 }, (_, i) => ({ text: `Decision ${i + 1}?`, question: `Decision ${i + 1}?`, kind: 'decision', who: 'attorney', id: `d-${i + 1}`, blocks_filing: i === 12 }))
  garcia.open_items!.open = garcia.needs_you.map(n => ({ id: n.id!, type: 'attorney_decision', title: n.text, question: n.question, detail: '', blocks_filing: n.blocks_filing, status: 'open' as const, resolution: '' })) as never
  const { ui, tap } = await boot($, on, [garcia])
  expect(await inActions(ui, /^13 questions · 0 answered$/)).toBeDefined()
  await tap('items')
  expect(await ui.find({ type: 'Text', text: /^Attorney decisions · 0 of 13 answered$/ })).toBeDefined()
  const texts = (await ui.findAll({ type: 'Text' })).map((t: { text: string }) => t.text)
  expect(texts.indexOf('Decision 13?')).toBeLessThan(texts.indexOf('Decision 1?'))
  expect(texts[texts.indexOf('Decision 13?') + 1]).toBe('Needed before filing')
  expect(await ui.find({ type: 'Input', key: 'answer-d-7' })).toBeDefined()
  // The Overview's Needs attention lists the one needed before filing first; its View brings Questions back.
  await tap('nav-matter')
  await tap('view:d-13')
  expect(await ui.find({ type: 'Input', key: 'answer-d-13' })).toBeDefined()
  await ui.unmount()
})

test('the list refreshes by itself when a run finishes while the attorney is on Matters', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const lopez = card('Lopez I-751', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  on('ui.notify', async () => ({ value: { isSent: true, channel: 'iterm2' } }))
  const { clock, ui, tap, matters, ops } = await boot($, on, [garcia, lopez])
  await tap('main:build')
  matters[0] = card('Garcia I-130 I-485', 'building', DOCS, { stage: i => (i < 3 ? 'passed' : i === 3 ? 'in_progress' : 'pending') })
  await clock.advance(15000)
  await clock.settle()
  await tap('nav-all')
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  matters[0] = card('Garcia I-130 I-485', 'complete', DOCS)
  await complete($, { agentId: 'agent-1', answer: 'Done.', reason: 'answer' })
  run.finish('completed')
  await clock.settle()
  await clock.advance(15000)
  await clock.settle()
  expect(ops).toContain('list')
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^1 ready to file$/ })).toBeDefined()
  await ui.unmount()
})

test('a double press of Build packet starts one agent, and the run lease is taken first, renewed, and released', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const spawned: { prompt?: string }[] = []
  let release: () => void = () => {}
  const gate = new Promise<void>(r => { release = r })
  on('agent.spawn', async (_$, e) => { spawned.push(e as never); await gate; return { model: 'opus', agentId: 'agent-1' } })
  let status: 'running' | 'completed' = 'running'
  on('agent.list', async () => ({ value: spawned.length ? [{ id: 'agent-1', description: 'Building the packet: Garcia I-130 I-485', type: 'senior-associate:senior-associate', status }] : [] }))
  on('turn.complete', async () => ({ text: '' }))
  const { clock, ui, requests } = await boot($, on, [garcia])
  const first = act(ui, 'build')
  const second = act(ui, 'build')
  await second
  await clock.settle()
  release()
  await first
  await clock.settle()
  expect(spawned).toHaveLength(1)
  expect(requests.filter(r => r.op === 'start_run')).toHaveLength(1)
  expect(requests.findIndex(r => r.op === 'start_run')).toBeGreaterThan(-1)
  expect(String(spawned[0]!.prompt)).toContain('Your run id is run-1.')
  await clock.advance(15000)
  await clock.settle()
  expect(requests.find(r => r.op === 'heartbeat_run')).toMatchObject({ run_id: 'run-1' })
  status = 'completed'
  await complete($, { agentId: 'agent-1', answer: 'Built.', reason: 'answer' })
  await clock.settle()
  expect(requests.find(r => r.op === 'release_run')).toMatchObject({ run_id: 'run-1', outcome: 'done' })
  await ui.unmount()
})

test('while Claude works on the matter elsewhere, Build is refused in plain words and nothing starts', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const { ui, tap, leases } = await boot($, on, [garcia])
  const at = new Date().toISOString()
  leases[garcia.path] = { run_id: 'chat-1', kind: 'chat', holder: 'chat', started_at: at, heartbeat_at: at, stage: null, fresh: true }
  await tap('main:build')
  expect(run.spawned).toHaveLength(0)
  expect(await ui.find({ type: 'Text', text: /^⏳ Claude is already working on this matter\. Try again when it finishes\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Claude is changing this matter in the chat\./ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'continue-link' })).toBeUndefined()
  await ui.unmount()
})

test('a refresh that set out before an action comes back after it, and is dropped', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  let hold: Promise<void> | undefined
  let letGo: () => void = () => {}
  const { clock, ui, tap } = await boot($, on, [garcia], { lateState: () => hold })
  await ui.press({ plugin: PLUGIN, key: 'items' }).catch(() => act(ui, 'items'))
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: 'resolved-group' })).toBeDefined()
  // The timer's refresh asks for the matter as it is now (one item resolved) and is slow to come back.
  hold = new Promise<void>(r => { letGo = r })
  const tick = clock.advance(15000)
  await clock.settle()
  hold = undefined
  // Meanwhile the attorney reopens the resolved item: the page shows it open, Resolved gone.
  await tap('resolved-group')
  await tap('reopen:act-photos')
  expect(await ui.find({ type: 'Button', key: 'resolved-group' })).toBeUndefined()
  letGo()
  await tick
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: 'resolved-group' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Passport photos$/ })).toBeDefined()
  await ui.unmount()
})

test('a matter the server calls paused, with a step still marked running, says to leave it if Claude is working in the chat', OPTS(), async ($, on) => {
  const old = new Date(Date.now() - 45 * 60000).toISOString()
  const garcia = card('Garcia I-130 I-485', 'paused', DOCS, { stage: i => (i < 3 ? 'passed' : i === 3 ? 'in_progress' : 'pending'), updated: old })
  const { ui } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^Paused$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /If Claude is still working on it in the chat, leave it/ })).toBeDefined()
  expect(await inActions(ui, /^Continue building$/)).toBeDefined()
  await ui.unmount()
})

// The server words the notes (test_server.py's test_review_notes_carry_words_never_codes); the app shows the first 40.
test('review notes past 40: the first 40 are shown, the rest counted', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  garcia.review_notes = Array.from({ length: 44 }, (_, i) => ({ id: `f-cover_letter_reviewer-${i + 1}`, title: `Minor point ${i + 1}.`, detail: '', severity_word: 'minor', outcome_word: '', owner_word: 'the client', stage_label: 'Letter review' }))
  const { ui, tap } = await boot($, on, [garcia])
  await tap('packet')
  expect(await ui.find({ type: 'Text', text: /^Review notes · 44 open$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: 'Minor · found in Letter review · to fix: the client' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^…and 4 more\./ })).toBeDefined()
  await ui.unmount()
})

test('what is needed before filing adds up: client, you, and risks to weigh', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  garcia.open_items!.open.push({ id: 'risk-1', type: 'risk', title: 'Gap in joint residence', detail: '', blocks_filing: true, status: 'open', resolution: '' } as never)
  garcia.open_items!.blocking = 7 // the list's own count, which disagrees: the app says the server's counts
  const { ui } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^The draft packet is built\. 3 things are needed before filing: 1 from the client, 1 for you and 1 risk to weigh\.$/ })).toBeDefined()
  await ui.unmount()
})

test('a temporary failure of the setup check doesn’t turn it off for the session', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const { ui, tap, ops } = await boot($, on, [garcia], { doctorFails: 1 })
  await tap('main:build')
  expect(run.spawned).toHaveLength(1)
  const before = ops.filter(o => o === 'doctor').length
  await tap('help')
  await tap('help-setup')
  expect(ops.filter(o => o === 'doctor').length).toBe(before + 1)
  expect(await ui.find({ type: 'Text', text: /^Ghostscript$/ })).toBeDefined()
  await ui.unmount()
})

test('a matter moved in Finder: after two failed refreshes the page says so, with the way back', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const gone: string[] = []
  const { clock, ui } = await boot($, on, [garcia], { gone })
  gone.push(garcia.path)
  await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /isn't in your Matters folder anymore/ })).toBeUndefined()
  await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^⚠ Garcia I-130 I-485 isn't in your Matters folder anymore\./ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'note-press:all' })).toBeDefined()
  await ui.unmount()
})

test('a reload while Claude works: the run is still the app’s own, so its wait for an OK still shows', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'building', DOCS, { stage: i => (i < 3 ? 'passed' : i === 3 ? 'in_progress' : 'pending') })
  const now = new Date().toISOString()
  const running = {
    [garcia.path]: { agentId: 'agent-9', runId: 'run-9', kind: 'build', matter: garcia.path, name: garcia.name, label: 'Building the packet', startedAt: now, endedAt: '', status: 'running',
      answer: '', reason: '', reply: '', step: '', stepLabel: '', lastSeen: '', lastChangeAt: now, waitingOk: false, description: `Building the packet: ${garcia.name}` },
  }
  // What the session held before the reload: the module starts over, $.state doesn't. The test keeps the runs value
  // as the host would, versioned, so the app's own writes to it land too.
  let kept: { value: unknown; version: number } = { value: running, version: 1 }
  on('state.get', async (_$, e, next) => (e.key === 'runs' ? { value: kept } as never : next(e)))
  on('state.set', async (_$, e, next) => {
    if (e.key !== 'runs') return next(e)
    const ifVersion = (e as { ifVersion?: number }).ifVersion
    if (ifVersion !== undefined && ifVersion !== kept.version) return { value: { isSet: false, version: kept.version } } as never
    kept = { value: (e as { value: unknown }).value, version: kept.version + 1 }
    return { value: { isSet: true, version: kept.version } } as never
  })
  on('command.register', async () => ({ value: { command: 'matters' } }))
  on('session.start', async (_$, e) => ({ cwd: (e as { cwd: string }).cwd }))
  on('tool.check', async (_$, e) => ({ decision: e.tool === 'Bash' ? 'ask' : 'allow' }))
  on('agent.list', async () => ({ value: [{ id: 'agent-9', description: `Building the packet: ${garcia.name}`, type: 'senior-associate:senior-associate', status: 'running' }] }))
  const { clock } = await open($, on)
  const { leases } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  leases[garcia.path] = { run_id: 'run-9', kind: 'build', holder: 'app', started_at: now, heartbeat_at: now, stage: null, fresh: true }
  await ($ as never as { session: { start: (e: unknown) => Promise<unknown> } }).session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await ($ as never as { tool: { check: (e: unknown) => Promise<unknown> } }).tool.check({ tool: 'Bash', input: { command: 'gs -v' }, agentId: 'agent-9', approver: 'person' })
  // (The test keeps the runs value itself, so the host's redraw on its change comes with the next refresh.)
  await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Claude is waiting for your OK in the chat\./ })).toBeDefined()
  await ui.unmount()
})

test('research by Claude’s agents is refused when it holds the client’s details; the attorney’s own chat is not gated', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const spawned: unknown[] = []
  on('agent.spawn', async (_$, e) => { spawned.push(e); return { model: 'opus', agentId: 'agent-1' } })
  on('agent.list', async () => ({ value: [
    { id: 'agent-1', description: 'Building the packet: Garcia I-130 I-485', type: 'senior-associate:senior-associate', status: 'running' },
    { id: 'agent-2', description: 'Cover letter research', type: 'senior-associate:cover-letter-researcher', status: 'running', parentId: 'agent-1' },
  ] }))
  on('tool.call', async () => ({ result: 'searched' } as never))
  const { ui, tap } = await boot($, on, [garcia], { terms: ['Ana Example', 'A123456789'] })
  await tap('main:build')
  const search = (query: string, agentId?: string) => ($ as never as { tool: { call: (e: unknown) => Promise<{ deny?: string; isError?: boolean; text?: string }> } }).tool.call({ tool: 'WebSearch', query, ...(agentId ? { agentId } : {}) })
  const named = await search('Is Ana Example eligible for a 212(i) waiver?', 'agent-2')
  expect(JSON.stringify(named)).toContain('Immigration Packet Builder blocked this: it contained the client’s details.')
  const numbered = await search('A-123-456-789 prior removal', 'agent-1')
  expect(JSON.stringify(numbered)).toContain('blocked')
  const legal = await search('Is a 212(i) waiver available after a false claim to citizenship?', 'agent-2')
  expect(JSON.stringify(legal)).not.toContain('blocked')
  const attorney = await search('Ana Example 212(i)')
  expect(JSON.stringify(attorney)).not.toContain('blocked')
  await ui.unmount()
})

test('every screen draws in the app’s theme, light or dark: no fixed text colour, no fill behind words, every press a labelled host button', OPTS(), async ($, on) => {
  const draft = card('Garcia I-130 I-485', 'draft', DOCS, { fresh: ['Passport.pdf'] })
  draft.needs_you = [{ text: 'Include an I-765?', question: 'Include an I-765?', kind: 'decision', who: 'attorney', id: 'decide-i765' }]
  const { clock, ui, tap } = await boot($, on, [draft, card('Lopez N-400', 'complete', DOCS)], { checks: undefined })
  const check = async (where: string) => {
    expect([where, ...offTheme(await ui.drawn())]).toEqual([where])
  }
  await check('matter')
  for (const section of ['sec-instructions', 'sec-more', 'sec-details']) await tap(section)
  await check('matter, unfolded')
  for (const key of ['packet', 'items', 'docs', 'memo', 'request', 'timeline']) {
    // The client request is the second half of the Memo & request tab.
    if (key === 'request') await tap('memo')
    await ui.press({ plugin: PLUGIN, key }).catch(() => act(ui, key))
    await clock.settle()
    await check(key)
    await tap('nav-matter')
  }
  await tap('help')
  await check('help')
  await tap('help-setup')
  await check('setup')
  await tap('nav-back-setup')
  await tap('nav-back-help')
  await tap('nav-all')
  await check('list')
  await tap('profile')
  await check('your details')
  await tap('nav-all')
  await tap('main:new')
  await check('new matter')
  await ui.unmount()
})

test('every box has its label above it, and each press says in words what it does', OPTS(), async ($, on) => {
  const draft = card('Garcia I-130 I-485', 'needs_you', DOCS)
  draft.needs_you = [{ text: 'Include an I-765?', question: 'Include an I-765?', kind: 'decision', who: 'attorney', id: 'decide-i765' }]
  const { clock, ui, tap } = await boot($, on, [draft])
  // The desktop draws an Input's own label beside the field; here each field is the second child of a Box whose first
  // is its label.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const unlabelled = (el: any, out: string[] = []): string[] => {
    if (!el || typeof el !== 'object') return out
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(el.children ?? []).forEach((c: any, i: number) => {
      if (c?.type === 'Input' && !(i === 1 && el.children[0]?.type === 'Text')) out.push(c.key)
    })
    for (const child of el.children ?? []) unlabelled(child, out)
    return out
  }
  expect(unlabelled(await ui.drawn())).toEqual([])
  await ui.press({ plugin: PLUGIN, key: 'items' }).catch(() => act(ui, 'items'))
  await clock.settle()
  expect(unlabelled(await ui.drawn())).toEqual([])
  expect((await ui.find({ type: 'Button', key: 'done:act-sign' }))?.props?.label).toBe('Mark done')
  expect((await ui.find({ type: 'Button', key: 'save-answer:decide-i765' }))?.props?.label).toBe('Save answer')
  expect((await ui.find({ type: 'Button', key: 'ask-item:decide-i765' }))?.props?.label).toBe('Ask Claude about this')
  await tap('nav-matter')
  await tap('docs')
  expect((await ui.find({ type: 'Button', key: 'remove:Passport.pdf' }))?.props?.label).toBe('Remove')
  await ui.unmount()
})

test('choices say which is selected: the case types, the posture, and how it is filed', OPTS(), async ($, on) => {
  const { ui, tap } = await boot($, on, [], { open: false }, { prefs: SEEN })
  await tap('main:new')
  await tap('type:n400')
  expect((await ui.find({ type: 'Button', key: 'type:n400' }))?.props?.label).toBe('● N-400 naturalization')
  expect((await ui.find({ type: 'Button', key: 'type:i130_i485' }))?.props?.label).toBe('○ I-130 / I-485 immediate relative')
  expect((await ui.find({ type: 'Button', key: 'posture:new filing packet' }))?.props).toMatchObject({ label: 'New filing', variant: 'primary' })
  expect((await ui.find({ type: 'Button', key: 'method:paper' }))?.props).toMatchObject({ label: 'On paper, by mail', variant: 'primary' })
  await ui.unmount()
})

test('new matter: a name with particles, filing online, and protection go to the matter', OPTS(), async ($, on) => {
  const { ui, tap, requests } = await boot($, on, [], { open: false }, { prefs: SEEN })
  await tap('main:new')
  await ui.input({ plugin: PLUGIN, key: 'name', text: 'maria de la cruz', kind: 'change' })
  await tap('type:i130_i485')
  expect(await ui.find({ type: 'Text', text: /folder will be named “Maria de la Cruz I-130 I-485”/ })).toBeDefined()
  await ui.press({ plugin: PLUGIN, key: 'method:online' })
  await tap('protect:toggle')
  await tap('main:create')
  expect(requests.find(r => r.op === 'create')).toMatchObject({ name: 'Maria de la Cruz I-130 I-485', filing_method: 'online', protected: true })
  expect(requests.filter(r => r.op === 'set_meta')).toEqual([]) // the server keeps them as it creates the matter
  await ui.unmount()
})

test('Your details: Back with changes typed asks first; I don’t have a USCIS online account saves at once', OPTS(), async ($, on) => {
  const { ui, tap, requests } = await boot($, on, [], { open: false }, { prefs: SEEN })
  await tap('profile')
  await tap('account:none')
  expect(requests.filter(r => r.op === 'save_profile').at(-1)).toMatchObject({ profile: { has_uscis_online_account: 'no', uscis_online_account_number: '' } })
  expect(await ui.find({ type: 'Input', key: 'profile-uscis_online_account_number' })).toBeUndefined()
  expect((await ui.find({ type: 'Button', key: 'account:yes' }))?.props?.label).toBe('● I don’t have a USCIS online account')
  await ui.input({ plugin: PLUGIN, key: 'profile-firm_name', text: 'Example Law', kind: 'change' })
  await tap('nav-back-profile')
  expect(await ui.find({ type: 'Text', text: /^You changed Firm and haven’t saved it\./ })).toBeDefined()
  const saves = requests.filter(r => r.op === 'save_profile').length
  await tap('profile-save-back')
  expect(requests.filter(r => r.op === 'save_profile').length).toBe(saves + 1)
  expect(requests.filter(r => r.op === 'save_profile').at(-1)).toMatchObject({ profile: { firm_name: 'Example Law' } })
  await ui.unmount()
})

test('archive and the sorted list: Archive moves a matter to Archived at the foot; Name sorts within the groups', OPTS(), async ($, on) => {
  const names = ['Garcia', 'Lopez', 'Nguyen', 'Bravo']
  const seed = names.map(n => card(`${n} I-130 I-485`, 'ready', DOCS))
  const { ui, tap, matters } = await boot($, on, seed)
  await tap('do-archive')
  expect(metaOf(matters[0]!).archived_at).toBeTruthy()
  expect(await ui.find({ type: 'Text', text: /^✓ Garcia I-130 I-485 is archived\./ })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /^Archived \(1\) ›$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${ROOT}/Garcia I-130 I-485` })).toBeUndefined()
  await tap('sort:name')
  const rows = (await ui.findAll({ type: 'Button' })).map((b: { key?: string }) => b.key).filter((k: string | undefined) => k?.startsWith('open:'))
  expect(rows).toEqual([`open:${ROOT}/Bravo I-130 I-485`, `open:${ROOT}/Lopez I-130 I-485`, `open:${ROOT}/Nguyen I-130 I-485`])
  expect((await ui.find({ type: 'Button', key: `open:${ROOT}/Bravo I-130 I-485` }))?.props?.hotkey).toBe('1')
  await ui.unmount()
})

test('the notification names the matter, and /matters opens that matter first', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const notified: string[] = []
  on('ui.notify', async (_$, e) => { notified.push(e.text); return { value: { isSent: true, channel: 'iterm2' } } })
  const { clock, ui, tap, matters } = await boot($, on, [garcia, card('Lopez I-751', 'ready', DOCS)])
  await tap('main:build')
  await tap('nav-all')
  matters[0] = card('Garcia I-130 I-485', 'complete', DOCS)
  await complete($, { agentId: 'agent-1', answer: 'Built.', reason: 'answer' })
  run.finish('completed')
  await clock.settle()
  expect(notified[0]).toBe('Garcia I-130 I-485 is ready to file.')
  await ($ as never as { command: { run: (e: unknown) => Promise<unknown> } }).command.run({ command: 'matters', args: '' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Ready to file$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'nav-all' })).toBeDefined()
  await ui.unmount()
})

test('Close the picker gives the page back at once, and the closed picker adds nothing', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'new', [])
  let release: () => void = () => {}
  const picking = new Promise<void>(r => { release = r })
  const { clock, ui, tap } = await boot($, on, [garcia], { picking })
  const pressed = act(ui, 'add-files')
  for (let i = 0; i < 20 && !(await ui.find({ type: 'Button', key: 'note-press:close-picker' })); i++) await clock.settle()
  await tap('note-press:close-picker')
  expect(await ui.find({ type: 'Text', text: /^✓ The file picker is closed and nothing was added\./ })).toBeDefined()
  expect((await ui.find({ type: 'Button', key: 'main:add-files' }))?.props?.dimColor).toBeUndefined()
  release()
  await pressed
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /Added 2 files/ })).toBeUndefined()
  await ui.unmount()
})

test('while Claude works: Mark done says Claude takes it into account when it finishes, and Put back waits', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  ;(garcia.documents as { removed?: unknown[] }).removed = [{ name: 'Old lease.pdf', path: 'Old lease.pdf', kept: 'output/removed documents/Old lease.pdf' }]
  agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia])
  await tap('main:items')
  await tap('nav-matter')
  await tap('do-update')
  await tap('items')
  await tap('done:act-sign')
  expect(await ui.find({ type: 'Text', text: /^✓ Marked done\. Claude takes this into account when it finishes\./ })).toBeDefined()
  await tap('nav-matter')
  await tap('docs')
  expect(await ui.find({ type: 'Button', key: 'restore:output/removed documents/Old lease.pdf' })).toBeUndefined()
  await ui.unmount()
})

test('redoing a review says it is fresh and full; the timeline lists what happened, by day', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  ;(garcia as Matter & { timeline?: unknown[] }).timeline = [
    { at: new Date().toISOString(), kind: 'run_finished', text: 'Packet build finished.', actor: 'app' },
    { at: new Date().toISOString(), kind: 'answer_saved', text: 'Answer saved.', actor: 'attorney' },
  ]
  const { ui, tap } = await boot($, on, [garcia])
  await tap('packet')
  await tap('redo:forms_reviewer')
  expect(await ui.find({ type: 'Text', text: /^Forms review is done fresh and in full: Claude checks everything again, not only what changed/ })).toBeDefined()
  await tap('main:redo-cancel')
  await tap('nav-matter')
  await tap('timeline')
  expect(await ui.find({ type: 'Text', text: /^Today$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^You: Answer saved\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Packet build finished\.$/ })).toBeDefined()
  await ui.unmount()
})

test('the client request: another language is the matter’s setting, and each language can be copied', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  garcia.translations.Spanish = '# Documentos que aún necesitamos\n\n1. **Su I-94.**'
  metaOf(garcia).client_language = 'Spanish'
  const { ui, tap, requests, copied } = await boot($, on, [garcia])
  await tap('memo')
  await tap('request')
  expect((await ui.find({ type: 'Button', key: 'lang:Spanish' }))?.props).toMatchObject({ label: 'Spanish', variant: 'primary' })
  await tap('main:copy-request-lang:Spanish')
  expect(copied.at(-1)).toBe('Documentos que aún necesitamos\n\n1. Su I-94.')
  await tap('lang:Portuguese')
  expect(requests.find(r => r.op === 'set_meta')).toMatchObject({ client_language: 'Portuguese' })
  expect(await ui.find({ type: 'Text', text: /^✓ Claude also writes the client request in Portuguese/ })).toBeDefined()
  await ui.unmount()
})

// ---------- the branch review's findings ----------

test('a start waiting in the chat box stays Waiting for you while its own lease holds the matter; unsent after 10 minutes, it lets go, clears the chat box and says so', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let box = ''
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: [] }))
  on('prompt.fill', async (_$, e) => { box = e.text; return { isFilled: true } })
  on('prompt.read', async () => ({ value: { text: box, cursor: box.length } }))
  const { clock, ui, tap, requests, leases } = await boot($, on, [garcia])
  await tap('main:build')
  await clock.advance(15000)
  await clock.settle()
  // The server says building (the app's own lease), and the page still says it waits for the attorney's Enter.
  expect(leases[garcia.path]?.holder).toBe('app')
  expect(await ui.find({ type: 'Text', text: /^Waiting for you$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'cancel-start' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /outside this page/ })).toBeUndefined()
  expect(box).toContain('Your run id is run-1.')
  for (let i = 0; i < 44; i++) await clock.advance(15000)
  await clock.settle()
  expect(requests.find(r => r.op === 'cancel_start')).toMatchObject({ run_id: 'run-1' })
  expect(requests.find(r => r.op === 'release_run')).toBeUndefined()
  expect(leases[garcia.path]).toBeUndefined()
  expect(box).toBe('')
  expect(await ui.find({ type: 'Text', text: /^⚠ The start in your chat box wasn’t sent\. Press Build packet to try again\.$/ })).toBeDefined()
  const beats = requests.filter(r => r.op === 'heartbeat_run').length
  for (let i = 0; i < 8; i++) await clock.advance(15000)
  await clock.settle()
  expect(requests.filter(r => r.op === 'heartbeat_run').length).toBe(beats)
  expect(await inActions(ui, /^Build packet$/)).toBeDefined()
  await ui.unmount()
})

test('a packet ready to file with a question not needed before filing: Ready to file, the question still answerable', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'complete', DOCS)
  const decision = { id: 'decide-i765', type: 'attorney_decision', title: 'I-765 with the I-485', question: 'Include an I-765 work permit application with the I-485?', recommendation: 'Yes, if he wants to work.', detail: '', blocks_filing: false, status: 'open' as const, resolution: '' }
  garcia.needs_you = [{ text: decision.question, question: decision.question, kind: 'decision', who: 'attorney', id: decision.id, blocks_filing: false } as never]
  ;(garcia as unknown as { open_items: unknown }).open_items = { packet_status: 'ready_to_file', updated_at: garcia.updated_at, open: [decision], resolved: [], resolved_count: 0, counts: { attorney_decision: 1 }, blocking: 0 }
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^Ready to file$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Your decision · Not needed before filing$/ })).toBeDefined()
  await tap('items')
  expect(await ui.find({ type: 'Text', text: /^Not needed before filing$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Needed before filing$/ })).toBeUndefined()
  await ui.input({ plugin: PLUGIN, key: 'answer-decide-i765', text: 'Yes, include it.', kind: 'change' })
  await tap('main:update')
  expect(String(run.spawned[0]?.prompt)).toContain('Answer: Yes, include it.')
  await ui.unmount()
})

test('a matter protected by its case type alone: Change what is being filed starts from it and keeps it', OPTS(), async ($, on) => {
  const older = card('Doe I-485', 'ready', DOCS)
  older.intake = { ...older.intake, matter_type: 'I-485 based on U nonimmigrant status', matter_type_label: 'I-485 based on U nonimmigrant status' }
  Object.assign(metaOf(older), { protected: true, protected_reason: 'case_type' })
  const { ui, tap, requests } = await boot($, on, [older])
  await tap('do-intake')
  expect(await ui.find({ type: 'Text', text: /^● This client is protected under 8 U\.S\.C\. 1367/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'protect:toggle' })).toBeUndefined()
  await ui.press({ plugin: PLUGIN, key: 'method:online' })
  await tap('main:intake-save')
  expect(requests.find(r => r.op === 'set_meta')).toMatchObject({ filing_method: 'online', protected: true })
  await ui.unmount()
})

test('a start the chat box can’t let go of says so: delete it there rather than send it', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let box = ''
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: [] }))
  // The box takes the request, then a dialog holds the keys when the app tries to clear it.
  on('prompt.fill', async (_$, e) => { if (box) return { isFilled: false, refusal: 'dialog' as const }; box = e.text; return { isFilled: true } })
  on('prompt.read', async () => ({ value: { text: box, cursor: box.length } }))
  const { clock, ui, tap } = await boot($, on, [garcia])
  await tap('main:build')
  for (let i = 0; i < 45; i++) await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^⚠ The start in your chat box wasn’t sent, so it was cancelled\. It’s still in your chat box: delete it there rather than send it\. Press Build packet to try again\.$/ })).toBeDefined()
  await ui.unmount()
})

test('a start sent from the chat box that the orchestrator took up is never let go of: the run keeps the matter', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let box = ''
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: [] })) // its agent is in another window: the app never sees it
  on('prompt.fill', async (_$, e) => { box = e.text; return { isFilled: true } })
  on('prompt.read', async () => ({ value: { text: box, cursor: box.length } }))
  const { clock, ui, tap, requests, leases } = await boot($, on, [garcia])
  await tap('main:build')
  // The attorney sent it; its orchestrator renewed the app's run under its own name.
  leases[garcia.path]!.holder = 'orchestrator'
  await clock.advance(15000)
  await clock.settle()
  expect(requests.find(r => r.op === 'cancel_start')).toMatchObject({ run_id: 'run-1' })
  expect(requests.find(r => r.op === 'release_run')).toBeUndefined()
  expect(leases[garcia.path]).toMatchObject({ run_id: 'run-1', holder: 'orchestrator' })
  expect(await ui.find({ type: 'Text', text: /wasn’t sent/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  // The app stops renewing it: the run holds the matter on its own renewals now.
  const beats = requests.filter(r => r.op === 'heartbeat_run').length
  for (let i = 0; i < 4; i++) await clock.advance(15000)
  await clock.settle()
  expect(requests.filter(r => r.op === 'heartbeat_run').length).toBe(beats)
  await ui.unmount()
})

test('a start sent from the chat box is matched to its matter by the run id in its brief, whatever the chat calls it', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const lopez = card('Lopez I-751', 'ready', DOCS)
  let box = ''
  let fromChat = false
  on('agent.spawn', async () => (fromChat ? { model: 'opus', agentId: 'agent-9' } : { deny: 'auto mode' }))
  on('agent.list', async () => ({ value: fromChat ? [{ id: 'agent-9', description: 'Immigration Packet Builder build', type: 'senior-associate:senior-associate', status: 'running' as const }] : [] }))
  on('prompt.fill', async (_$, e) => { box = e.text; return { isFilled: true } })
  on('prompt.read', async () => ({ value: { text: box, cursor: box.length } }))
  const { clock, ui, tap, requests } = await boot($, on, [garcia, lopez])
  await tap('main:build')
  // The chat starts the agent with the brief from the box, under a description of its own.
  fromChat = true
  await ($ as never as { agent: { spawn: (e: unknown) => Promise<unknown> } }).agent.spawn({ prompt: box.split('with this brief:\n\n')[1], description: 'Immigration Packet Builder build', subagentType: 'senior-associate:senior-associate' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Keep Claude open until it finishes\./ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'watch' })).toBeDefined()
  for (let i = 0; i < 45; i++) await clock.advance(15000)
  await clock.settle()
  expect(requests.find(r => r.op === 'cancel_start')).toBeUndefined()
  expect(requests.filter(r => r.op === 'heartbeat_run' && r.run_id === 'run-1').length).toBeGreaterThan(40)
  await ui.unmount()
})

test('research by a run the app lost track of is still checked, by the network gate’s rule', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'paused', DOCS)
  on('agent.list', async () => ({ value: [{ id: 'agent-orch', description: 'Build the packet', type: 'senior-associate:senior-associate', status: 'running' }] }))
  on('tool.call', async () => ({ result: 'searched' } as never))
  const { clock } = await open($, on)
  world(on, [garcia], { prefs: { ...SEEN } }, { profile: ANA, terms: ['Ana Example'], unattended: [garcia.path] })
  await clock.settle()
  const search = (query: string) => ($ as never as { tool: { call: (e: unknown) => Promise<unknown> } }).tool.call({ tool: 'WebSearch', query, agentId: 'agent-orch' })
  expect(JSON.stringify(await search('Ana Example waiver'))).toContain('Immigration Packet Builder blocked this')
})

test('a start sent from the chat box: once its agent appears, Claude is at work in the app’s own run', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let sent = false
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: sent ? [{ id: 'agent-7', description: 'Building the packet: Garcia I-130 I-485', type: 'senior-associate:senior-associate', status: 'running' }] : [] }))
  on('prompt.fill', async () => ({ isFilled: true }))
  const { clock, ui, tap } = await boot($, on, [garcia])
  await tap('main:build')
  sent = true
  await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Keep Claude open until it finishes\./ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'watch' })).toBeDefined()
  await ui.unmount()
})

test('answers typed and never saved go with the update: a report’s questions and an open item’s', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Reviewing the documents: Garcia I-130 I-485')
  const { clock, ui, tap } = await boot($, on, [garcia])
  await tap('main:review')
  await complete($, { agentId: 'agent-1', answer: 'I reviewed the 2 documents.\n\nTwo things need you:\n\n1. Should we include an I-765?\n2. Which entry date is right?', reason: 'answer' })
  run.finish('completed')
  await clock.settle()
  await tap('main:items')
  await ui.input({ plugin: PLUGIN, key: 'rq-1', text: '2019, per the I-94.', kind: 'change' })
  await clock.settle()
  await tap('main:update')
  expect(String(run.spawned[1]?.prompt)).toContain('Which entry date is right?\n   Answer: 2019, per the I-94.')
  await ui.unmount()
})

test('an open item’s answer typed and never saved is kept in the matter and goes with the update', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.needs_you = [{ text: 'Include an I-765?', question: 'Include an I-765?', kind: 'decision', who: 'attorney', id: 'decide-i765' }]
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { ui, tap, requests } = await boot($, on, [garcia])
  await tap('items')
  await ui.input({ plugin: PLUGIN, key: 'answer-decide-i765', text: 'Yes, include it.', kind: 'change' })
  await tap('main:update')
  expect(requests.find(r => r.op === 'save_answer')).toMatchObject({ key: 'decide-i765', answer: 'Yes, include it.' })
  expect(String(run.spawned[0]?.prompt)).toContain('Answer: Yes, include it.')
  await ui.unmount()
})

test('research from a run started in the chat, before /matters was opened, is checked against the matters the server says are at work', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  on('agent.list', async () => ({ value: [{ id: 'agent-chat', description: 'Build the packet', type: 'senior-associate:senior-associate', status: 'running' }] }))
  on('tool.call', async () => ({ result: 'searched' } as never))
  let terms: string[] = []
  const { clock } = await open($, on)
  const { leases } = world(on, [garcia], { prefs: { ...SEEN } }, { profile: ANA, terms: () => terms })
  const at = new Date().toISOString()
  leases[garcia.path] = { run_id: 'orch-1', kind: 'build', holder: 'orchestrator', started_at: at, heartbeat_at: at, stage: null, fresh: true }
  await clock.settle()
  const search = (query: string) => ($ as never as { tool: { call: (e: unknown) => Promise<unknown> } }).tool.call({ tool: 'WebSearch', query, agentId: 'agent-chat' })
  // No terms yet (the folder was just made): nothing to match, and nothing kept, so the next call asks again.
  expect(JSON.stringify(await search('Ana Example waiver'))).not.toContain('blocked')
  terms = ['Ana Example', 'Garcia']
  expect(JSON.stringify(await search('Ana Example waiver'))).toContain('Immigration Packet Builder blocked this')
  expect(JSON.stringify(await search('Is Garcia’s 2019 arrest a bar?'))).toContain('blocked')
  expect(JSON.stringify(await search('Matter of Garcia, 16 I&N Dec. 653 (BIA 1978): what does it hold on good faith?'))).not.toContain('blocked')
})

test('research from a matter’s own agent is refused, in plain words, when its private terms can’t be had', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  agents(on, 'Building the packet: Garcia I-130 I-485')
  on('tool.call', async () => ({ result: 'searched' } as never))
  const { ui, tap } = await boot($, on, [garcia], { termsFail: true })
  await tap('main:build')
  const res = await ($ as never as { tool: { call: (e: unknown) => Promise<unknown> } }).tool.call({ tool: 'WebSearch', query: 'good faith marriage evidence', agentId: 'agent-1' })
  expect(JSON.stringify(res)).toContain('Immigration Packet Builder couldn’t check this research request against the client’s details. Try again in a moment.')
  await ui.unmount()
})

test('the finish notification is said from the matter as release_run returns it, with no other look', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const notified: string[] = []
  on('ui.notify', async (_$, e) => { notified.push(e.text); return { value: { isSent: true, channel: 'iterm2' } } })
  const { clock, ui, tap, matters, requests } = await boot($, on, [garcia, card('Lopez I-751', 'ready', DOCS)])
  await tap('main:build')
  await tap('nav-all')
  matters[0] = card('Garcia I-130 I-485', 'draft', DOCS)
  const before = requests.length
  await complete($, { agentId: 'agent-1', answer: 'Built.', reason: 'answer' })
  run.finish('completed')
  await clock.settle()
  expect(notified).toEqual(['Garcia I-130 I-485: draft packet ready. 2 items are needed before filing.'])
  expect(requests.slice(before).filter(r => r.op === 'state' && r.matter_path === garcia.path)).toEqual([])
  await ui.unmount()
})

test('one start at a time per matter: a start held on one matter doesn’t hold up another', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const lopez = card('Lopez I-751', 'ready', DOCS)
  const spawned: string[] = []
  let release: () => void = () => {}
  const gate = new Promise<void>(r => { release = r })
  on('agent.spawn', async (_$, e) => {
    const d = String((e as { description?: string }).description)
    spawned.push(d)
    if (d.includes('Garcia')) await gate
    return { model: 'opus', agentId: d.includes('Garcia') ? 'agent-g' : 'agent-l' }
  })
  on('agent.list', async () => ({ value: [] }))
  on('turn.complete', async () => ({ text: '' }))
  const { clock, ui, tap } = await boot($, on, [garcia, lopez])
  const first = act(ui, 'build')
  for (let i = 0; i < 20 && !spawned.length; i++) await clock.settle()
  await act(ui, 'build') // the same matter: refused while its start is on its way
  await clock.settle()
  expect(spawned).toHaveLength(1)
  await tap('nav-all')
  await tap(`open:${lopez.path}`)
  await tap('main:build')
  expect(spawned).toEqual(['Building the packet: Garcia I-130 I-485', 'Building the packet: Lopez I-751'])
  release()
  await first
  await clock.settle()
  await ui.unmount()
})

test('adding files: the server’s own summary is said as it is, with the press that works them in', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  const { ui, tap } = await boot($, on, [garcia], { addMessage: 'Added 1 file. 1 was already in the matter. Lease.pages wasn’t added: export it as a PDF and add that.' })
  await tap('do-add-files')
  expect(await ui.find({ type: 'Text', text: /^✓ Added 1 file\. 1 was already in the matter\. Lease\.pages wasn’t added: export it as a PDF and add that\. Press Update the packet to work them in\.$/ })).toBeDefined()
  await ui.unmount()
})

// ---------- a document replaced in place (finding 8): offered exactly like new files ----------
// (The server's golden generator has no matter with a replaced file yet, so these are built by hand.)

const replaced = (m: Matter, changed: string[]) => { (m.documents as { changed_since_build?: string[] }).changed_since_build = changed; return m }

test('a file replaced since the build: the card says which and offers Update the packet; two, or with new ones, said together', OPTS(), async ($, on) => {
  const one = replaced(card('Garcia I-130 I-485', 'draft', DOCS), ['Passport.pdf'])
  const two = replaced(card('Lopez I-130 I-485', 'draft', DOCS), ['Passport.pdf', 'Marriage certificate.pdf'])
  const both = replaced(card('Nguyen I-130 I-485', 'draft', DOCS, { fresh: ['Lease.pdf'] }), ['Passport.pdf'])
  const { ui, tap } = await boot($, on, [one, two, both])
  expect(await ui.find({ type: 'Text', text: /^Passport\.pdf changed since the packet was built\. Update the packet to work in the new version\.$/ })).toBeDefined()
  expect(await inActions(ui, /^Works in the new version of Passport\.pdf$/)).toBeDefined()
  await unfold(ui, tap, 'sec-details')
  expect(await ui.find({ type: 'Text', text: /1 changed since the build/ })).toBeDefined()
  for (const [m, line] of [[two, /^2 files changed since the packet was built\. Update the packet to work in the new versions\.$/], [both, /^Since the packet was built, 1 new file arrived and Passport\.pdf changed\. Update the packet to bring it up to date and re-check it\.$/]] as const) {
    await tap('nav-all')
    await tap(`open:${m.path}`)
    expect(await ui.find({ type: 'Text', text: line })).toBeDefined()
  }
  // The Documents screen marks it, and works it in from there too.
  await tap('docs')
  expect(await ui.find({ type: 'Text', text: /^Since the packet was built, 1 new file arrived and Passport\.pdf changed\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^changed$/ })).toBeDefined()
  expect(await inActions(ui, /^Works in the 1 new file and the new version of Passport\.pdf$/)).toBeDefined()
  await ui.unmount()
})

test('a file replaced after only the document review: Review the documents again, the same way as a new one', OPTS(), async ($, on) => {
  const kim = replaced(card('Kim I-129F', 'reviewed', DOCS), ['Passport.pdf'])
  const { ui } = await boot($, on, [kim])
  expect(await ui.find({ type: 'Text', text: /^Passport\.pdf changed since Claude reviewed the documents\.$/ })).toBeDefined()
  expect(await inActions(ui, /^Review the documents again$/)).toBeDefined()
  expect(await inActions(ui, /About 5–10 minutes · see what’s still missing/)).toBeDefined()
  await ui.unmount()
})

test('a replaced file alone is reason enough for Update the packet, even with a question still open', OPTS(), async ($, on) => {
  const garcia = replaced(card('Garcia I-130 I-485', 'needs_you', DOCS), ['Passport.pdf'])
  garcia.needs_you = [{ text: 'Include an I-765?', question: 'Include an I-765?', kind: 'decision', who: 'attorney', id: 'decide-i765' }]
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { ui, tap, requests } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^It also works in the new version of Passport\.pdf, since the last build\.$/ })).toBeDefined()
  await tap('main:update')
  expect(requests.find(r => r.op === 'start_run')).toMatchObject({ kind: 'update' })
  expect(run.spawned).toHaveLength(1)
  await ui.unmount()
})

test('in a protected matter no file name is said: only how many changed', OPTS(), async ($, on) => {
  const lane = replaced(card('Lane I-360', 'draft', DOCS, { fresh: ['Shelter letter.pdf'] }), ['Passport.pdf'])
  metaOf(lane).protected = true
  const { ui, tap } = await boot($, on, [lane])
  expect(await ui.find({ type: 'Text', text: /^Since the packet was built, 1 new file arrived and 1 file changed\. Update the packet/ })).toBeDefined()
  expect(await inActions(ui, /^Works in the 1 new file and the new version of 1 file$/)).toBeDefined()
  await tap('docs')
  expect(await ui.find({ type: 'Text', text: /^Since the packet was built, 1 new file arrived and 1 file changed\.$/ })).toBeDefined()
  await ui.unmount()
})

test('filing approval sends the reviewed digest and the attorney’s risk reason', OPTS(), async ($, on) => {
  const draft = card('Synthetic filing test', 'draft', DOCS)
  draft.filing_readiness = { eligible: true, approved: false, digest: 'reviewed-version', blockers: [], risks: ['An unresolved merits issue'], attorney: '', approved_at: '' }
  const { clock, ui, tap, requests } = await boot($, on, [draft])
  await tap('packet')
  await unfold(ui, tap, 'sec-approval')
  expect(await ui.find({ type: 'Text', text: /Review risk: An unresolved merits issue/ })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'filing-risk-note', text: 'Reviewed and elect to file with this risk.', kind: 'change' })
  await tap('approve-filing')
  expect(requests.find(r => r.op === 'approve_filing')).toMatchObject({ digest: 'reviewed-version', risk_note: 'Reviewed and elect to file with this risk.' })
  await ui.unmount()
})

test('both host hook events refuse opaque outbound tools and identifiers hidden in citations', OPTS(), async ($, on) => {
  const matter = card('Synthetic privacy test', 'ready', DOCS)
  agents(on, 'Building the packet: Synthetic privacy test')
  const transmitted: unknown[] = []
  on('tool.call', async (_$, e) => { transmitted.push(e); return { result: 'sent' } as never })
  const { ui, tap } = await boot($, on, [matter], { terms: ['Li Wu', 'Grace Young', 'A123456789'] })
  await tap('main:build')
  const host = $ as never as { tool: { call: (e: unknown) => Promise<unknown>; check: (e: unknown) => Promise<unknown> } }
  for (const input of [
    { tool: 'mcp__opaque__send', message: 'legal inquiry' },
    { tool: 'WebSearch', query: 'Matter of Example, 25 I&N Dec. 1 (A123456789)' },
    { tool: 'WebSearch', query: 'Li Wu hardship' },
    { tool: 'WebSearch', query: 'Grace Young waiver' },
  ]) {
    const count = transmitted.length
    const called = await host.tool.call({ ...input, agentId: 'agent-1' })
    expect(JSON.stringify(called)).toMatch(/blocked|not approved/)
    expect(transmitted.length).toBe(count)
    const { tool, ...args } = input
    const checked = await host.tool.check({ tool, input: args, agentId: 'agent-1', approver: 'person' })
    expect(JSON.stringify(checked)).toMatch(/blocked|not approved/)
  }
  await ui.unmount()
})
