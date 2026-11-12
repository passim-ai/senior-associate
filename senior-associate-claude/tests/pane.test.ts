// The attorney's path through the app, on the desktop surface, as
// docs/EXPERIENCE.md lays it out: getting set up and the welcome (the first
// time), naming the client and the case, adding files and a folder, every
// document, the steps, building (and the Your details question before it),
// Claude at work, a finished build and its notification, a stopped one, the
// list again, a draft packet with what's left and the memo, answering
// Claude's questions, new documents and Update the packet, the request that
// goes into the chat box when the app can't start Claude itself, and the
// attorney's own details.
//
// The server is stood in for by answering `process.run` with the payloads the
// real server sends (tests/world.ts), the background agent by answering
// `agent.spawn` and `agent.list`, what the app remembers by answering the
// store, and the large buttons are pressed the way the drawn bar presses them:
// a post from the Client region. Everything else is the host's own Button.
import type { AgentStatus } from 'claude-code'
import { expect, test } from 'claude-code/testing'
import { PLUGIN, ROOT, CATALOG, card, payload, answer, GOOD_CHECKS, NO_GS, world, agents, ROW, SEEN, ANA, DOCS, OPTS, act, inActions, open, boot, mount, unfold } from './world'

test('the first time: getting set up, the welcome, the first matter, files and a folder, every document, the steps', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const { ops, store, toasts, copied, submitted } = world(on)
  const filled: string[] = []
  on('prompt.fill', async (_$, e) => { filled.push(e.text); return { isFilled: true } })
  const { ui, tap } = await mount($, clock)

  // Nothing stored: the setup check comes first, each line plain; where Claude can fix one, a press sends it the request.
  expect(ops).toContain('doctor')
  expect(await ui.find({ type: 'Text', text: /^Getting set up$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Once, about 5 minutes/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Makes the cover letter’s PDF match Word exactly/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^LibreOffice$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Case-law research/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Ask Claude to do it sends the request to Claude in the chat\./ })).toBeDefined()
  await tap('ask:libreoffice')
  expect(submitted).toHaveLength(1)
  expect(submitted[0]).toMatch(/^Install LibreOffice for Immigration Packet Builder\.\n\n\(Sent from Immigration Packet Builder when I pressed “Ask Claude to do it”\.\)$/)
  expect(copied).toEqual([])
  expect(filled).toEqual([])
  expect(toasts.at(-1)).toMatch(/Claude is on it in the chat/)
  expect(await ui.find({ type: 'Text', text: /Terminal/ })).toBeUndefined()
  expect(await inActions(ui, /^Continue$/)).toBeDefined()
  await tap('main:setup-continue')
  expect(store.prefs).toMatchObject({ setupSeen: true })

  // The welcome: three steps, the times, that nothing is filed or sent; Your details first while they're missing.
  expect(await ui.find({ type: 'Text', text: /Client documents in/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^YOUR FIRST MATTER$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /^Add your details$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Name the client and the case$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /about 1–1½ hours, in the background/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Nothing is filed or sent/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Type \/matters any time to come back/ })).toBeDefined()
  expect(await inActions(ui, /Add your details/)).toBeDefined()
  expect(await inActions(ui, /^New matter$/)).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'help' })).toBeDefined()
  await tap('main:start')

  // New matter: where you are, the way back, the client's name and what is being filed.
  expect(await ui.find({ type: 'Button', key: 'nav-all' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^New matter$/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'name' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^New filing or a response\?$/ })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'name', text: 'maria garcia', kind: 'change' })
  await tap('main:create')
  expect(ops).not.toContain('create')
  expect(await ui.find({ type: 'Text', text: /^Choose one below, then press Create matter\.$/ })).toBeDefined()
  await tap('type:i130_i485')
  expect(await ui.find({ type: 'Text', text: /^Choose one below/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /folder will be named “Maria Garcia I-130 I-485”/ })).toBeDefined()
  await tap('main:create')
  expect(ops).toContain('create')
  expect(toasts.at(-1)).toBe('Maria Garcia I-130 I-485 created. Add the client’s documents next.')
  expect(await ui.find({ type: 'Text', text: /^Maria Garcia I-130 I-485$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Needs documents$/ })).toBeDefined()
  expect(store.prefs).toMatchObject({ onboarded: true, lastMatter: `${ROOT}/Maria Garcia I-130 I-485` })

  // The next step with nothing in the matter: the two ways to add documents, and the System Events heads-up.
  expect(await ui.find({ type: 'Text', text: /^NEXT STEP$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Add the client’s documents$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /macOS may ask whether Claude can control System Events/ })).toBeDefined()
  expect(await inActions(ui, /Add files/)).toBeDefined()
  expect(await inActions(ui, /Build packet/)).toBeUndefined()

  // Add files through the picker: Ready to build, with the times on the buttons.
  await tap('main:add-files')
  expect(ops).toContain('add_documents')
  // Said on the page, where it stays until the next screen.
  expect(await ui.find({ type: 'Text', text: /^✓ Added 2 files\.$/ })).toBeDefined()
  expect(store.prefs).toMatchObject({ pickerSeen: true })
  expect(await ui.find({ type: 'Text', text: /^Ready to build$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Before you build, set the permission setting under the prompt box to Auto\./ })).toBeDefined()
  expect(await inActions(ui, /About 1–1½ hours · runs in the background/)).toBeDefined()
  expect(await inActions(ui, /About 5–10 minutes · see what’s missing first/)).toBeDefined()
  // The numbers, and the matter's details folded under them.
  expect(await ui.find({ type: 'Button', key: 'metric-docs' })).toMatchObject({ props: { label: 'Documents ›' } })
  await unfold(ui, tap, 'sec-details')
  expect(await ui.find({ type: 'Text', text: /^2 files/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Not started · 10 steps/ })).toBeDefined()

  // Documents: a folder can be added from here; the copy is said out loud, and the list groups by folder.
  await tap('docs')
  expect(await ui.find({ type: 'Button', text: /^Documents$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /your originals stay where they are/ })).toBeDefined()
  await tap('main:add-folder')
  expect(ops).toContain('add_folder')
  expect(await ui.find({ type: 'Text', text: /^✓ Added 2 files\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /4 files in the matter folder/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Tax returns · 1$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /^2025 return.pdf$/ })).toBeDefined()
  await tap('nav-matter')

  // Packet: the steps, the review notes in plain words, and the way back at the foot.
  await tap('packet')
  expect(await ui.find({ type: 'Text', text: /^Steps$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Final review$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Review notes · 2 open$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Worth fixing · RFE likely · found in Final review · to fix: the client$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Minor · found in Forms review · to fix: you$/ })).toBeDefined()
  await tap('nav-matter')
  expect(await inActions(ui, /Build packet/)).toBeDefined()

  // Ask Claude about this matter: a question typed in its box goes to the chat as the attorney's own words, in the
  // opening the matter chat answers to, and the box comes back empty. Without BIA Edge, it says how to connect it.
  expect(await ui.find({ type: 'Text', text: /^Ask Claude about this matter$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Connect BIA Edge in Claude’s Connectors so Claude can cite case law\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'ask' })).toBeUndefined() // the old link at the foot is gone
  await ui.input({ plugin: PLUGIN, key: 'ask', text: 'Does the 2019', kind: 'change' })
  await ui.input({ plugin: PLUGIN, key: 'ask', text: '  Does the 2019 arrest affect eligibility? ', kind: 'submit' })
  await clock.settle()
  expect(submitted.at(-1)).toBe('Ask Immigration Packet Builder about Maria Garcia I-130 I-485: Does the 2019 arrest affect eligibility?')
  expect(filled).toEqual([])
  expect(await ui.find({ type: 'Text', text: /^✓ Claude is answering in the chat\.$/ })).toBeDefined()
  expect((await ui.find({ type: 'Input', key: 'ask' }))?.text).toBe('')
  // Before a build, the suggestions are about the case itself; one press sends one.
  expect(await ui.find({ type: 'Text', text: /^Does the client qualify, on the documents we have\?$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /weakest point in the cover letter/ })).toBeUndefined()
  await tap('ask-try:0')
  expect(submitted.at(-1)).toMatch(/^Ask Immigration Packet Builder about Maria Garcia I-130 I-485: How do we answer this: “Joint records begin two months before filing\.”$/)
  expect(toasts).not.toContain('Type your question in the chat box below.')
  await ui.unmount()
})

test('build: the Your details question first, then Claude at work, then the finished draft and its notification', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { matters, toasts } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } })
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const notified: string[] = []
  on('ui.notify', async (_$, e) => { notified.push(e.text); return { value: { isSent: false, reason: 'no-surface' } } })
  const views: unknown[] = []
  on('ui.view', async (_$, e) => { views.push(e); return { value: {} } })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)

  // Your details are empty: Build says what that means before anything starts.
  await tap('main:build')
  expect(run.spawned.length).toBe(0)
  expect(await ui.find({ type: 'Text', text: /^Before you build$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Your details aren’t filled in, so the G-28 and the letter’s signature will be left blank/ })).toBeDefined()
  expect(await inActions(ui, /Add your details first/)).toBeDefined()
  await tap('main:gate-build')

  // Build anyway starts the app's own background agent; nothing goes into the conversation.
  expect(run.spawned.length).toBe(1)
  expect(run.spawned[0]).toMatchObject({ tool: 'Agent', run_in_background: true, subagent_type: 'senior-associate:senior-associate' })
  expect(String(run.spawned[0]!.prompt)).toMatch(/Build the packet/)
  expect(String(run.spawned[0]!.description)).toBe('Building the packet: Garcia I-130 I-485')
  expect(toasts.at(-1)).toBe('Building the packet in the background. You’ll get a notification when it’s done.')

  // Claude at work: which step, how long so far and how long to go, and that Claude must stay open.
  matters[0] = card('Garcia I-130 I-485', 'building', DOCS, { stage: i => (i < 3 ? 'passed' : i === 3 ? 'in_progress' : 'pending') })
  await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Building the packet · step 4 of 10: Cover letter$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Started .* · about 50 min left$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Keep Claude open until it finishes/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'watch' })).toBeDefined()
  expect(await ui.find({ type: 'Box', key: 'actions' })).toBeUndefined()
  await tap('watch')
  expect(views).toEqual([{ agentId: 'agent-1' }])

  // The list says it's working, and where.
  await tap('nav-all')
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /step 4 of 10 · updated/ })).toBeDefined()
  await tap(`open:${garcia.path}`)

  // It finishes with a report: the page offers the next step, and a notification says what came of it.
  matters[0] = card('Garcia I-130 I-485', 'draft', DOCS)
  await ($ as never as { turn: { complete: (e: unknown) => Promise<unknown> } }).turn.complete({ agentId: 'agent-1', answer: 'I built the draft packet. It isn’t ready to file: 2 items stand in the way.', reason: 'answer', durationMs: 1000, isAborted: false, turnId: 't1' })
  run.finish('completed')
  await clock.settle()
  expect(notified).toEqual(['A draft packet is ready. 2 items are needed before filing.'])
  // No notification channel on the desktop: the same words as a toast.
  expect(toasts.at(-1)).toBe('A draft packet is ready. 2 items are needed before filing.')
  expect(await ui.find({ type: 'Text', text: /^What Claude did$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Packet build · finished .*, took / })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /I built the draft packet/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Draft packet$/ })).toBeDefined()
  await ui.unmount()
})

test('Claude at work: waiting for your OK, then twenty minutes with no progress, then Stop and try again', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { matters } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  on('tool.check', async (_$, e) => ({ decision: e.tool === 'Bash' ? 'ask' : 'allow' }))
  const stops: unknown[] = []
  on('tool.call', { tool: 'TaskStop' }, async (_$, e) => { stops.push(e); return { result: 'stopped' } as never })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  expect(run.spawned.length).toBe(1)
  matters[0] = card('Garcia I-130 I-485', 'building', DOCS, { stage: i => (i < 3 ? 'passed' : i === 3 ? 'in_progress' : 'pending') })
  await clock.advance(15000)
  await clock.settle()

  // The agent asks to run something the attorney must OK: the page says where to answer.
  await ($ as never as { tool: { check: (e: unknown) => Promise<unknown> } }).tool.check({ tool: 'Bash', input: { command: 'gs -v' }, agentId: 'agent-1', approver: 'person' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Claude is waiting for your OK in the chat\. The build continues once you answer\.$/ })).toBeDefined()
  // And the way out of several hundred of these: Auto, under the prompt box.
  expect(await ui.find({ type: 'Text', text: /^A build asks like this several hundred times in Claude’s usual setting\. Under the prompt box, switch the permission setting to Auto/ })).toBeDefined()
  await ($ as never as { tool: { check: (e: unknown) => Promise<unknown> } }).tool.check({ tool: 'Read', input: {}, agentId: 'agent-1', approver: 'person' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /waiting for your OK in the chat\. The build/ })).toBeUndefined()

  // Twenty minutes and nothing has moved: say so, and offer a way out.
  await clock.advance(21 * 60000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Nothing has changed for 20 minutes\. Claude may be waiting for your OK in the chat, or it stopped\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'stop-retry' })).toBeDefined()
  await tap('stop-retry')
  expect(stops).toMatchObject([{ tool: 'TaskStop', task_id: 'agent-1' }])
  // Started again where it stopped: the build continues rather than starting over.
  expect(run.spawned.length).toBe(2)
  expect(String(run.spawned[1]!.prompt)).toMatch(/^Continue\./)
  await ui.unmount()
})

test('a stopped run: what happened in plain words, nothing raw, and Try again picks up where it stopped', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { matters } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const notified: string[] = []
  on('ui.notify', async (_$, e) => { notified.push(e.text); return { value: { isSent: true, channel: 'iterm2' } } })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  matters[0] = card('Garcia I-130 I-485', 'building', DOCS, { stage: i => (i < 2 ? 'passed' : i === 2 ? 'in_progress' : 'pending') })
  await clock.advance(15000)
  await clock.settle()
  await ($ as never as { turn: { complete: (e: unknown) => Promise<unknown> } }).turn.complete({ agentId: 'agent-1', answer: 'API Error: 529 overloaded_error', reason: 'error', durationMs: 1000, isAborted: false, turnId: 't1' })
  await clock.settle()

  expect(notified).toEqual(['The build on one of your matters stopped at Forms review. Type /matters to try again.'])
  expect(await ui.find({ type: 'Text', text: /^Stopped$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^The build stopped at step 3 of 10 \(Forms review\): Claude hit a temporary problem, such as a busy service or a dropped connection\. Everything finished before that is saved\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /overloaded|529|API Error/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^What Claude did$/ })).toBeUndefined()
  expect(await inActions(ui, /Picks up at Forms review/)).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'watch' })).toBeDefined()

  // The list puts it under Needs you, with a red Stopped.
  await tap('nav-all')
  expect(await ui.find({ type: 'Text', text: /^Needs you$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Open it to try again/ })).toBeDefined()
  await tap(`open:${garcia.path}`)
  await tap('main:retry-run')
  expect(run.spawned.length).toBe(2)
  expect(String(run.spawned[1]!.prompt)).toMatch(/^Continue\./)
  await ui.unmount()
})

test('setup before a build: a missing tool holds the build until it is installed, then Continue starts it', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { setChecks, submitted } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA, checks: NO_GS, dropSubmit: 'Auto mode' })
  const filled: string[] = []
  on('prompt.fill', async (_$, e) => { filled.push(e.text); return { isFilled: true } })
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  expect(run.spawned.length).toBe(0)
  expect(await ui.find({ type: 'Text', text: /^Getting set up$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Before Claude builds, 1 thing needs setting up on this Mac/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Claude can install Ghostscript for you\.$/ })).toBeDefined()
  // When the chat won't take the request (here, dropped), it waits in the chat box for the attorney to send.
  await tap('ask:ghostscript')
  expect(submitted).toHaveLength(1)
  expect(filled[0]).toMatch(/^Install Ghostscript for Immigration Packet Builder\./)
  expect(await ui.find({ type: 'Text', text: /The request is in your chat box\. Press Enter to send it to Claude\./ })).toBeDefined()
  expect(await inActions(ui, /Check again/)).toBeDefined()
  expect(await inActions(ui, /Continue anyway/)).toBeDefined()

  // Still missing after Check again: it says what, and what to do.
  await tap('main:setup-check')
  expect(await ui.find({ type: 'Text', text: /Still missing: Ghostscript/ })).toBeDefined()

  // Installed: Continue starts the build that was held back.
  setChecks(GOOD_CHECKS)
  await tap('main:setup-check')
  expect(await inActions(ui, /Start the build/)).toBeDefined()
  await tap('main:setup-continue')
  expect(run.spawned.length).toBe(1)
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  await ui.unmount()
})

test('the second time: the list opens folded with no client named; pick up where you left off says the case, and Show opens a group', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const lopez = card('Lopez I-130 I-485', 'complete', DOCS)
  const silva = card('Silva I-751', 'needs_you', DOCS)
  silva.needs_you = [{ text: 'q', kind: 'decision', who: 'attorney' }, { text: 'r', kind: 'decision', who: 'attorney' }]
  const haddad = card('Haddad I-612', 'filed', DOCS)
  const { ui, tap } = await boot($, on, [garcia, lopez, silva, haddad], { profile: {}, open: false, folded: true })
  // Everything on screen that has words: the texts and what each press is called.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const said = (el: any, out: string[] = []): string[] => {
    if (typeof el === 'string') out.push(el)
    else if (el && typeof el === 'object') {
      if (el.props?.label) out.push(String(el.props.label))
      for (const child of el.children ?? []) said(child, out)
    }
    return out
  }
  const named = async () => said(await ui.drawn()).filter(t => /Garcia|Lopez|Silva|Haddad/.test(t))

  // As it opens: what stands where, how many in each group, and nobody's name.
  expect(await ui.find({ type: 'Text', text: /^1 needs your answer · 1 ready to file$/ })).toBeDefined()
  expect(await named()).toEqual([])
  expect(await ui.find({ type: 'Text', text: /^Client names stay hidden until you show a group\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Pick up where you left off/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^I-130 \/ I-485 immediate relative · Ready to build · / })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `main:open:${garcia.path}` })).toMatchObject({ text: 'Open it' })
  expect(await ui.find({ type: 'Text', text: /^Needs you$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^In preparation$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Ready to file$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'grp:needs_you' })).toMatchObject({ text: 'Show' })
  expect(await ui.find({ type: 'Button', key: `open:${silva.path}` })).toBeUndefined()
  // The list's order has nothing to order yet.
  expect(await ui.find({ type: 'Button', key: 'sort:name' })).toBeUndefined()

  // Show opens that group and no other.
  await tap('grp:needs_you')
  expect(await ui.find({ type: 'Button', key: `open:${silva.path}` })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Answer 2 questions/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${lopez.path}` })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Client names are showing\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'grp:needs_you' })).toMatchObject({ text: 'Hide' })
  expect(await ui.find({ type: 'Button', key: 'sort:name' })).toBeDefined()
  await tap('show-all')
  expect(await ui.find({ type: 'Button', key: `open:${lopez.path}` })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${garcia.path}` })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'show-all' })).toBeUndefined()
  // Filed matters wait, folded, until asked for.
  expect(await ui.find({ type: 'Button', key: 'filed-group' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${haddad.path}` })).toBeUndefined()
  await tap('filed-group')
  expect(await ui.find({ type: 'Button', key: `open:${haddad.path}` })).toBeDefined()

  // Hide names folds every group again, Filed with them.
  await tap('hide-all')
  expect(await named()).toEqual([])

  await tap(`main:${`open:${garcia.path}`}`)
  expect(await inActions(ui, /Build packet/)).toBeDefined()
  await ui.unmount()
})

test('a short list has no Pick up card: New matter, then the matters', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { ui } = await boot($, on, [garcia, card('Lopez N-400', 'complete', DOCS)], { profile: {}, open: false })
  expect(await ui.find({ type: 'Text', text: /Pick up where you left off/ })).toBeUndefined()
  expect(await inActions(ui, /^New matter$/)).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${garcia.path}` })).toBeDefined()
  await ui.unmount()
})

test('the tenth time: a search field filters a long list', OPTS(), async ($, on) => {
  const names = ['Garcia', 'Lopez', 'Nguyen', 'Patel', 'Okafor', 'Silva', 'Haddad', 'Kim']
  const { clock, ui } = await boot($, on, names.map(n => card(`${n} I-130 I-485`, 'ready', DOCS)), { profile: {}, open: false }, { prefs: SEEN })
  expect(await ui.find({ type: 'Input', key: 'search' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${ROOT}/Kim I-130 I-485` })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'search', text: 'pat', kind: 'change' })
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: `open:${ROOT}/Patel I-130 I-485` })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${ROOT}/Kim I-130 I-485` })).toBeUndefined()
  await ui.unmount()
})

test('new matter with Enter, and a name already taken', OPTS(), async ($, on) => {
  const { ui, tap, ops } = await boot($, on, [card('Lopez I-130 I-485', 'complete', DOCS)], { profile: {}, open: false }, { prefs: SEEN })
  await tap('main:new')
  await tap('type:i130_i485')
  await ui.input({ plugin: PLUGIN, key: 'name', text: 'lopez', kind: 'change' })
  await tap('type:i130_i485')
  expect(await ui.find({ type: 'Text', text: /^You already have Lopez I-130 I-485\. This one will be named “Lopez I-130 I-485 \(2\)”\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${ROOT}/Lopez I-130 I-485` })).toBeDefined()
  // An RFE response asks for the notice too.
  await tap('posture:RFE response')
  expect(await ui.find({ type: 'Text', text: /^Add the RFE notice along with the client’s documents\.$/ })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'name', text: 'lopez' })
  expect(ops).toContain('create')
  await ui.unmount()
})

test('a server that couldn’t run shows on the page in plain words, with a retry', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('ui.toast', async () => ({ value: undefined }))
  on('fs.exists', async () => ({ value: true }))
  on('store.get', async () => ({ value: undefined }))
  on('process.run', async () => ({ value: { exitCode: 1, stdout: '', stderr: 'Traceback (most recent call last):\nKeyError: matters_root', isStdoutTruncated: false, isStderrTruncated: false } }))
  const { ui } = await mount($, clock)
  expect(await ui.find({ type: 'Text', text: /^⚠ That didn’t work, and nothing was changed\. Try again\./ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /matters_root|Traceback/ })).toBeUndefined()
  expect(await inActions(ui, /Try again/)).toBeDefined()
  await ui.unmount()
})

test('without uv, the app says so, and Claude installs it', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('ui.toast', async () => ({ value: undefined }))
  on('fs.exists', async () => ({ value: false }))
  on('store.get', async () => ({ value: undefined }))
  on('process.run', async () => ({ value: { exitCode: 127, stdout: '', stderr: 'zsh: command not found: uv', isStdoutTruncated: false, isStderrTruncated: false } }))
  const submitted: string[] = []
  on('prompt.submit', async (_$, e) => { submitted.push(e.text); return { text: e.text } })
  const { ui, tap } = await mount($, clock)
  expect(await ui.find({ type: 'Text', text: /^⚠ Immigration Packet Builder needs uv, a free helper that runs its tools\. Claude can install it for you; then type \/matters again\.$/ })).toBeDefined()
  await tap('note-ask')
  expect(submitted[0]).toMatch(/^Install uv for Immigration Packet Builder\./)
  await ui.unmount()
})

test('while the folder picker is open, the app says so, and other clicks say why they wait', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'new', [])
  let releasePicker: () => void = () => {}
  const picking = new Promise<void>(resolve => { releasePicker = resolve })
  const ops: string[] = []
  on('ui.toast', async () => ({ value: undefined }))
  on('fs.exists', async () => ({ value: true }))
  on('store.get', async (_$, e) => ({ value: e.key === 'prefs' ? { ...SEEN, lastMatter: garcia.path } : undefined }))
  on('store.set', async () => ({ value: undefined }))
  on('process.run', async (_$, e) => {
    const argv = e.argv as readonly string[]
    const request = JSON.parse(argv[argv.length - 1] ?? '{}') as Record<string, string>
    ops.push(request.op ?? '')
    if (request.op === 'add_folder') {
      await picking // the macOS picker stays open until the attorney chooses
      return answer({ ...payload(garcia, [garcia]), added: ['Passport.pdf'], skipped: [], cancelled: false })
    }
    return answer(payload(request.matter_path ? garcia : null, [garcia]))
  })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:add-folder')
  expect(await ui.find({ type: 'Text', text: /^⏳ Choose the folder in the Finder window/ })).toBeDefined()
  // Back to the list needs the server, which is busy: the click explains instead of doing nothing.
  const before = ops.length
  await tap('nav-all')
  expect(ops.length).toBe(before)
  expect(await ui.find({ type: 'Text', text: /it may be behind this window/ })).toBeDefined()
  releasePicker()
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /Choose the folder in the Finder window/ })).toBeUndefined()
  await ui.unmount()
})

test('a cancelled picker says so in a toast; a message under the navigation can be dismissed and leaves with the screen', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const toasts: string[] = []
  on('ui.toast', async (_$, e) => { toasts.push(e.text); return { value: undefined } })
  on('fs.exists', async () => ({ value: true }))
  on('store.get', async (_$, e) => ({ value: e.key === 'prefs' ? { ...SEEN, lastMatter: garcia.path } : undefined }))
  on('store.set', async () => ({ value: undefined }))
  on('process.run', async (_$, e) => {
    const argv = e.argv as readonly string[]
    const request = JSON.parse(argv[argv.length - 1] ?? '{}') as Record<string, string>
    if (request.op === 'add_documents') return answer({ ...payload(garcia, [garcia]), cancelled: true })
    if (request.op === 'open_folder') return answer({ error: "Garcia I-130 I-485 isn't in your Matters folder anymore. It may have been moved or renamed in Finder." }, 1)
    return answer(payload(request.matter_path ? garcia : null, [garcia]))
  })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('docs')
  await tap('main:add-files')
  expect(toasts.at(-1)).toBe('No files added.')
  await tap('open-folder')
  expect(await ui.find({ type: 'Text', text: /^⚠ Garcia I-130 I-485 isn't in your Matters folder anymore\./ })).toBeDefined()
  await tap('dismiss-note')
  expect(await ui.find({ type: 'Text', text: /isn't in your Matters folder/ })).toBeUndefined()
  await tap('open-folder')
  expect(await ui.find({ type: 'Text', text: /isn't in your Matters folder/ })).toBeDefined()
  await tap('nav-matter')
  expect(await ui.find({ type: 'Text', text: /isn't in your Matters folder/ })).toBeUndefined()
  await ui.unmount()
})

test('the main actions are the host’s own buttons: focusable, named, the primary marked, and b presses the matter’s main action', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  // The Finder picker stays open until the test lets it go.
  let release: () => void = () => {}
  const picking = new Promise<void>(r => { release = r })
  const { clock, ui, ops, tap } = await boot($, on, [garcia], { picking }, { prefs: { ...SEEN, onboarded: false } })
  // Build packet is a native button with its name, the primary one, and the b key presses it; its companion is secondary.
  const build = await ui.find({ type: 'Button', key: 'main:build' })
  expect(build?.props).toMatchObject({ label: 'Build packet', variant: 'primary', hotkey: 'b' })
  expect((await ui.find({ type: 'Button', key: 'main:review' }))?.props).toMatchObject({ label: 'Review documents first', variant: 'secondary' })
  expect((await ui.find({ type: 'Button', key: 'main:review' }))?.props?.hotkey).toBeUndefined()
  // What each does is said under it, in words, not drawn into the button.
  expect(await inActions(ui, /^About 1–1½ hours · runs in the background$/)).toBeDefined()
  // While a Mac picker is open, the buttons dim; nothing else does.
  await unfold(ui, tap, 'sec-more')
  const pressed = ui.press({ plugin: PLUGIN, key: 'do-add-files' })
  let dimmed = false
  for (let i = 0; i < 20 && !dimmed; i++) {
    await clock.settle()
    dimmed = (await ui.find({ type: 'Button', key: 'main:build' }))?.props?.dimColor === true
  }
  expect(dimmed).toBe(true)
  expect(await ui.find({ type: 'Button', key: 'note-press:close-picker' })).toBeDefined()
  release()
  await pressed
  await clock.settle()
  expect(ops).toContain('add_documents')
  expect((await ui.find({ type: 'Button', key: 'main:build' }))?.props?.dimColor).toBeUndefined()
  await ui.unmount()
})

test('inline in the conversation: the /matters row draws the app with a tip, and points to an open side panel instead of drawing twice', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  world(on, [card('Garcia I-130 I-485', 'ready', DOCS)], { prefs: { ...SEEN, inlineUses: 1 } })
  let paneUp = false
  const opened: string[] = []
  on('ui.open', async (_$, e) => { opened.push(e.id); paneUp = true; return { value: { isPlaced: true } } })
  on('ui.panes', async () => ({ value: paneUp ? [{ id: 'senior-associate', title: 'Immigration Packet Builder', isShown: true, isFocused: false, isPlaced: true }] : [] }))
  const ui = (await $.ui.mount({ ...ROW, props: ROW.props } as never)) as any
  await clock.advance(10)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Tip: Open as side panel keeps this beside your chat while Claude works\.$/ })).toBeDefined()
  // Drawn in the conversation, the list is folded too.
  expect(await ui.find({ type: 'Button', key: `open:${ROOT}/Garcia I-130 I-485` })).toBeUndefined()
  await ui.press({ plugin: PLUGIN, key: 'grp:preparing' })
  await clock.settle()
  await ui.press({ plugin: PLUGIN, key: `open:${ROOT}/Garcia I-130 I-485` })
  await clock.settle()
  expect(await inActions(ui, /Build packet/)).toBeDefined()
  await ui.press({ plugin: PLUGIN, key: 'dock' })
  await clock.settle()
  expect(opened).toEqual(['senior-associate'])
  expect(await ui.find({ type: 'Text', text: /^Immigration Packet Builder is open beside the chat\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'show-pane' })).toBeDefined()
  await ui.unmount()
})

test('a draft packet: what is needed before filing, who owes it, what is left with its actions, and the client request as plain text', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  const { ui, tap, requests, copied } = await boot($, on, [garcia])

  expect(await ui.find({ type: 'Text', text: /^Draft packet$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^The draft packet is built\. 2 things are needed before filing: 1 from the client and 1 for you\.$/ })).toBeDefined()
  // The client owes something: sending the request is the first thing to do.
  expect(await inActions(ui, /Copy the client request/)).toBeDefined()
  expect(await inActions(ui, /2 needed before filing/)).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'open-packet' })).toBeDefined()
  // The numbers, and what needs attention, each with the way to it.
  expect(await ui.find({ type: 'Button', key: 'metric-needed' })).toMatchObject({ props: { label: 'Needed before filing ›' } })
  expect(await ui.find({ type: 'Text', text: /^Needs attention$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'view:doc-i94' })).toBeDefined()
  // Everything else that can be done now, each with what it does, folded until asked for.
  expect(await ui.find({ type: 'Button', text: /^▸ More you can do$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'do-change' })).toBeUndefined()
  await unfold(ui, tap, 'sec-more')
  for (const key of ['do-add-files', 'do-change', 'do-steps', 'do-stress', 'do-intake', 'do-mark-filed']) expect(await ui.find({ type: 'Button', key })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'do-review-again' })).toBeUndefined() // a fresh review is for before a build
  await unfold(ui, tap, 'sec-details')
  expect(await ui.find({ type: 'Text', text: /^Draft built · 2 needed before filing$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^1 from the client · 1 decision · 1 for you to do · 2 needed before filing$/ })).toBeDefined()

  // Questions: the decisions first, then the rest grouped by who acts, each with what to do about it.
  await tap('main:items')
  expect(await ui.find({ type: 'Text', text: /^Attorney decisions$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Include an I-765 work permit application with the I-485\?$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^From the client · 1$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^For you to do · 1$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Needed before filing$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'recv:doc-i94' })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'answer-decide-i765' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'rec:decide-i765' })).toBeDefined()
  await tap('done:act-sign')
  expect(requests.at(-1)).toMatchObject({ op: 'resolve_item', matter_path: garcia.path, id: 'act-sign' })
  expect(await ui.find({ type: 'Text', text: /^✓ Marked done\. Changed your mind\?/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Questions & missing evidence$/ })).toBeDefined()
  await tap('copy-request')
  expect(copied[0]).toBe('Documents and information we still need\n\nNeeded before we can file:\n1. Your most recent I-94. Download it from the CBP site (https://i94.cbp.dhs.gov).\n\nThank you,')
  // Show the client request reads it right here, the way the memo is read; no other app opens.
  const opens = requests.filter(r => r.op === 'open_output').length
  await tap('show-request')
  expect(await ui.find({ type: 'Button', key: 'request' })).toMatchObject({ props: { label: 'Client request', variant: 'primary' } })
  expect(await ui.find({ type: 'Text', text: /Your most recent I-94/ })).toBeDefined()
  expect(requests.filter(r => r.op === 'open_output').length).toBe(opens)
  await tap('main:copy-request')
  expect(copied).toHaveLength(2)
  expect(copied[1]).toBe(copied[0])
  // It is the Memo & request tab, beside the memo; Questions is a tab away.
  await tap('items')
  expect(await ui.find({ type: 'Button', key: 'show-request' })).toBeDefined()

  // The memo reads right here.
  await tap('memo')
  expect(await ui.find({ type: 'Text', text: /The marriage is well documented/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^ATTORNEY WORK PRODUCT$/ })).toBeDefined()
  await ui.unmount()
})

test('new documents after a build: Update the packet works them in', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS, { fresh: ['Passport.pdf', 'Marriage certificate.pdf'] })
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^2 new files arrived since the packet was built\. Update the packet to work them in and re-check it\.$/ })).toBeDefined()
  expect(await inActions(ui, /Works in the 2 new files/)).toBeDefined()
  await unfold(ui, tap, 'sec-details')
  expect(await ui.find({ type: 'Text', text: /2 new since the build/ })).toBeDefined()

  // Adding more files to a built matter says what to do next.
  await tap('docs')
  expect(await ui.find({ type: 'Text', text: /^new$/ })).toBeDefined()
  await tap('main:add-files')
  expect(await ui.find({ type: 'Text', text: /^✓ Added 2 files\. Press Update the packet to work them in\.$/ })).toBeDefined()
  await tap('nav-matter')

  await tap('main:update')
  expect(run.spawned.length).toBe(1)
  expect(String(run.spawned[0]!.prompt)).toMatch(/^Update the packet\./)
  expect(String(run.spawned[0]!.description)).toBe('Updating the packet: Garcia I-130 I-485')
  expect(await ui.find({ type: 'Text', text: /^Updating the packet/ })).toBeDefined()
  await ui.unmount()
})

test('changes made in chat after a build: the matter says the reviews haven’t seen them, and Update the packet re-checks', OPTS(), async ($, on) => {
  const garcia = { ...card('Garcia I-130 I-485', 'draft', DOCS), chat_changes: [{ at: new Date().toISOString(), what: 'Cover letter: leads with the joint lease' }] }
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { ui, tap, requests } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^Since the packet was built, you made a change in chat \(Cover letter: leads with the joint lease\)\. Update the packet to have the reviews check it\.$/ })).toBeDefined()
  expect(await inActions(ui, /Re-checks what you changed in chat/)).toBeDefined()
  // After a build, the suggestions turn to the officer's objection, the decision waiting, and the packet.
  expect(await ui.find({ type: 'Text', text: /^How do we answer this: “Joint records begin two months before filing\.”$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Help me decide: Include an I-765 work permit application with the I-485\?$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^What would an officer question first in this packet\?$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Does the client qualify/ })).toBeUndefined()
  await tap('main:update')
  expect(run.spawned.length).toBe(1)
  expect(requests.some(r => r.op === 'resolve_item')).toBe(false)
  await ui.unmount()
})

test('ask Claude about an open item or a review note: the chat box gets the matter, the item and a first question, and nothing is sent', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  const { submitted } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  const filled: string[] = []
  on('prompt.fill', async (_$, e) => { filled.push(e.text); return { isFilled: true } })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('items')
  await tap('ask-item:decide-i765')
  expect(filled.at(-1)).toBe('Ask Immigration Packet Builder about Garcia I-130 I-485, about “Include an I-765 work permit application with the I-485?”: Help me decide. What are the options, and the risk of each?')
  expect(await ui.find({ type: 'Text', text: /^⏳ Your question is in the chat box below\. Change it if you like, then press Enter\.$/ })).toBeDefined()
  await tap('ask-item:doc-i94')
  expect(filled.at(-1)).toBe('Ask Immigration Packet Builder about Garcia I-130 I-485, about “Most recent I-94 arrival record”: Why is this needed, and what could stand in for it if the client can’t get it?')
  await tap('packet')
  await tap('ask-note:1')
  expect(filled.at(-1)).toBe('Ask Immigration Packet Builder about Garcia I-130 I-485, about “Joint records begin two months before filing.”: Is this right, and how should we fix it?')
  expect(submitted).toEqual([])
  await ui.unmount()
})

test('a question the chat won’t take waits in the chat box', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { submitted } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA, dropSubmit: 'Auto mode' })
  const filled: string[] = []
  on('prompt.fill', async (_$, e) => { filled.push(e.text); return { isFilled: true } })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await ui.input({ plugin: PLUGIN, key: 'ask', text: '   ', kind: 'submit' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^⚠ Type your question first, then press Ask\.$/ })).toBeDefined()
  expect(submitted).toEqual([])
  await ui.input({ plugin: PLUGIN, key: 'ask', text: 'What should we file?', kind: 'submit' })
  await clock.settle()
  expect(submitted).toEqual(['Ask Immigration Packet Builder about Garcia I-130 I-485: What should we file?'])
  expect(filled).toEqual(['Ask Immigration Packet Builder about Garcia I-130 I-485: What should we file?'])
  expect(await ui.find({ type: 'Text', text: /^⏳ Your question is in the chat box\. Press Enter to send it to Claude\.$/ })).toBeDefined()
  await ui.unmount()
})

test('needs your answer: one box per question, the recommendation fills one, the client’s and the Mac’s items apart, and Update sends the answers', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.needs_you = [
    { text: 'I-765 with the I-485', question: 'Include an I-765 work permit application with the I-485?', recommendation: 'Yes, if he wants to work while the I-485 is pending.', detail: 'He has no work authorization now.', kind: 'decision', who: 'attorney', id: 'decide-i765', stage: 'Forms' },
    { text: 'How should Part 8 item 22 be answered, given the 2019 overstay?', kind: 'decision', who: 'attorney', id: 'decide-item-22' },
    { text: 'I-94 arrival record', kind: 'blocker', who: 'client', stage: 'Document review' },
    { text: 'Ghostscript isn’t installed', kind: 'blocker', who: 'system', fix: 'Claude can install Ghostscript for you. Then build again.', ask: 'Install Ghostscript for Immigration Packet Builder.' },
  ]
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { clock, ui, tap, submitted } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^Your judgment is needed$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Answer what you can on Questions, then press Update the packet\. Anything you leave blank stays on the list for later\.$/ })).toBeDefined()
  expect(await inActions(ui, /^2 questions · 0 answered$/)).toBeDefined()
  // What waits on the Mac is said on the Overview; the questions and what the client owes are on Questions.
  expect(await ui.find({ type: 'Text', text: /^Claude can install Ghostscript for you\. Then build again\.$/ })).toBeDefined()
  await tap('ask-fix:3')
  expect(submitted[0]).toMatch(/^Install Ghostscript for Immigration Packet Builder\./)
  expect(await ui.find({ type: 'Button', key: 'check-again:3' })).toBeDefined()
  await tap('main:items')
  expect(await ui.find({ type: 'Text', text: /^Attorney decisions · 0 of 2 answered$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Recommended: Yes, if he wants to work while the I-485 is pending\.$/ })).toBeDefined()
  // One box per question for the attorney; none for what waits on the client or on the Mac.
  expect(await ui.find({ type: 'Input', key: 'answer-decide-i765' })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'answer-decide-item-22' })).toBeDefined()
  expect((await ui.findAll({ type: 'Input' })).filter((i: { key?: string }) => i.key?.startsWith('answer-'))).toHaveLength(2)
  expect(await ui.find({ type: 'Text', text: /^Waiting on the client$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^• I-94 arrival record$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'client-add' })).toBeDefined()
  // Only the question with a recommendation offers one.
  expect(await ui.find({ type: 'Button', key: 'rec:decide-i765' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'rec:decide-item-22' })).toBeUndefined()
  // Update with nothing answered says what to do, and starts nothing.
  await tap('main:update')
  expect(run.spawned.length).toBe(0)
  expect(await ui.find({ type: 'Text', text: /Answer at least one question first, add what the client sent, or use Tell Claude what to change/ })).toBeDefined()
  await tap('rec:decide-i765')
  expect(await ui.find({ type: 'Input', key: 'answer-decide-i765', text: 'Go with your recommendation: Yes, if he wants to work while the I-485 is pending.' })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'answer-decide-item-22', text: 'Answer yes and explain in the letter.', kind: 'submit' })
  await clock.settle()
  // The box's save visibly lands: a mark under that box and a line that says which button sends it.
  expect(await ui.find({ type: 'Text', text: /^✓ Answer saved\. Claude gets it when you press Update the packet\.$/ })).toBeDefined()
  expect(await ui.find({ key: `saved:${garcia.path}#decide-item-22`, text: /^✓ Saved$/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'answer-decide-item-22', text: 'Answer yes and explain in the letter.' })).toBeDefined()
  // The foot of Questions takes the saved answers to Claude.
  expect(await ui.find({ type: 'Text', text: /^Ready to use your answers\?$/ })).toBeDefined()
  await tap('main:update')
  expect(run.spawned.length).toBe(1)
  const prompt = String(run.spawned[0]!.prompt)
  expect(prompt).toContain("answers to the open questions:\n1. Include an I-765 work permit application with the I-485? (open item decide-i765)\n   Answer: Go with your recommendation: Yes, if he wants to work while the I-485 is pending.")
  expect(prompt).toContain('2. How should Part 8 item 22 be answered, given the 2019 overstay? (open item decide-item-22)\n   Answer: Answer yes and explain in the letter.')
  expect(prompt).not.toContain('I-94 arrival record')
  await ui.unmount()
})

test('questions asked only in a report get one box each', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Reviewing the documents: Garcia I-130 I-485')
  const { clock, ui, tap } = await boot($, on, [garcia])
  await tap('main:review')
  expect(await ui.find({ type: 'Text', text: /^Reviewing the documents$/ })).toBeDefined()
  await ($ as never as { turn: { complete: (e: unknown) => Promise<unknown> } }).turn.complete({ agentId: 'agent-1', answer: 'I reviewed the 2 documents.\n\nTwo things need you:\n\n1. Should we include an I-765?\n2. The I-94 shows a 2019 entry but the client says 2018. Which is right?', reason: 'answer', durationMs: 1000, isAborted: false, turnId: 't1' })
  run.finish('completed')
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Your judgment is needed$/ })).toBeDefined()
  await tap('main:items')
  expect(await ui.find({ type: 'Text', text: /^Should we include an I-765\?$/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'rq-0' })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'rq-1' })).toBeDefined()
  // The report doesn't repeat the questions under their boxes.
  await tap('nav-matter')
  expect(await ui.find({ type: 'Text', text: /^I reviewed the 2 documents\.$/ })).toBeDefined()
  expect((await ui.findAll({ type: 'Text', text: /Should we include/ })).filter((t: { text: string }) => !/^View/.test(t.text) && t.text !== 'Should we include an I-765?')).toEqual([])
  await tap('main:items')
  await ui.input({ plugin: PLUGIN, key: 'rq-1', text: '2019, per the I-94.', kind: 'submit' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^✓ Answer saved\. Claude gets it when you press Update the packet\.$/ })).toBeDefined()
  expect(await ui.find({ key: `saved:${garcia.path}#report-1`, text: /^✓ Saved$/ })).toBeDefined()
  expect(await ui.find({ key: `saved:${garcia.path}#report-0` })).toBeUndefined()
  await tap('main:update')
  expect(run.spawned.length).toBe(2)
  expect(String(run.spawned[1]!.prompt)).toContain('1. The I-94 shows a 2019 entry but the client says 2018. Which is right?\n   Answer: 2019, per the I-94.')
  await ui.unmount()
})

test('documents reviewed: what is missing, the client request, and Build', OPTS(), async ($, on) => {
  const kim = card('Kim I-129F', 'reviewed', DOCS)
  const { ui, tap, copied } = await boot($, on, [kim])
  expect(await ui.find({ type: 'Text', text: /^Documents reviewed$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Claude reviewed the 2 documents\. 1 thing is missing; they’re on the client request\. Send it now and build when they arrive, or build now and Claude leaves placeholders\.$/ })).toBeDefined()
  expect(await inActions(ui, /About 1–1½ hours · runs in the background/)).toBeDefined()
  await tap('main:copy-request')
  expect(copied[0]).toMatch(/^Documents and information we still need/)
  await unfold(ui, tap, 'sec-details')
  expect(await ui.find({ type: 'Text', text: /^1 of 10 steps done · next: Forms$/ })).toBeDefined()
  await ui.unmount()
})

test('documents reviewed with questions: the answers go with Build packet, and there is no Update before a packet exists', OPTS(), async ($, on) => {
  const kim = card('Kim I-129F', 'reviewed', DOCS)
  kim.needs_you = [{ text: 'Was the couple’s meeting in person within the last two years?', question: 'Was the couple’s meeting in person within the last two years?', kind: 'decision', who: 'attorney', id: 'decide-meeting' }]
  const run = agents(on, 'Building the packet: Kim I-129F')
  const { ui, tap } = await boot($, on, [kim])
  expect(await ui.find({ type: 'Text', text: /^Documents reviewed$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Your answers go with the build/ })).toBeDefined()
  expect(await inActions(ui, /Update the packet/)).toBeUndefined()
  await tap('items')
  expect(await inActions(ui, /Update the packet/)).toBeUndefined()
  expect(await inActions(ui, /^Your saved answers go with the build$/)).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'answer-decide-meeting', text: 'Yes, in Lisbon in May 2025.', kind: 'change' })
  await tap('main:build')
  expect(run.spawned.length).toBe(1)
  expect(String(run.spawned[0]!.prompt)).toContain('1. Was the couple’s meeting in person within the last two years? (open item decide-meeting)\n   Answer: Yes, in Lisbon in May 2025.')
  await ui.unmount()
})

test('additional attorney instructions: saved on the matter, cleared, and saved first when Build is pressed so the brief names them', OPTS(), async ($, on) => {
  const lee = card('Lee I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Lee I-130 I-485')
  const { clock, ui, tap, ops, requests } = await boot($, on, [lee])
  expect(await ui.find({ type: 'Button', text: /^▸ Attorney instructions$/ })).toBeDefined()
  await unfold(ui, tap, 'sec-instructions')
  expect(await ui.find({ type: 'Button', text: /^▾ Attorney instructions$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Claude reads these before every step, in the build and every update after it\.$/ })).toBeDefined()

  // Saved: into the matter, and the page says when Claude follows them.
  await ui.input({ plugin: PLUGIN, key: 'instructions', text: 'Lead the letter with the joint lease.', kind: 'submit' })
  await clock.settle()
  expect(requests.filter(r => r.op === 'set_instructions').at(-1)).toMatchObject({ matter_path: lee.path, text: 'Lead the letter with the joint lease.' })
  expect(await ui.find({ type: 'Text', text: /^✓ Instructions saved\. Claude follows them in every step of the build\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^✓ Saved$/ })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'instructions', text: '', kind: 'submit' })
  await clock.settle()
  expect(requests.filter(r => r.op === 'set_instructions').at(-1)).toMatchObject({ text: '' })
  expect(await ui.find({ type: 'Text', text: /^✓ Instructions cleared\.$/ })).toBeDefined()

  // Typed but not saved, then Build packet: saved first, and the run's brief is the one that names them.
  await ui.input({ plugin: PLUGIN, key: 'instructions', text: 'Don’t include an I-765.', kind: 'change' })
  await tap('main:build')
  expect(requests.filter(r => r.op === 'set_instructions').at(-1)).toMatchObject({ text: 'Don’t include an I-765.' })
  expect(ops.lastIndexOf('set_instructions')).toBeGreaterThan(ops.lastIndexOf('state'))
  expect(run.spawned.length).toBe(1)
  expect(String(run.spawned[0]!.prompt)).toContain(`Attorney instructions: ${lee.path}/output/working/workflow/attorney-instructions.md`)
  await ui.unmount()
})

test('additional attorney instructions after a build say how to apply them now, and a filed matter has no box', OPTS(), async ($, on) => {
  const ruiz = card('Ruiz I-130 I-485', 'draft', DOCS)
  ruiz.attorney_instructions = 'Lead the letter with the joint lease.'
  const haddad = card('Haddad I-612', 'filed', DOCS)
  const { clock, ui, tap } = await boot($, on, [ruiz, haddad])
  expect(await ui.find({ type: 'Text', text: /^Saved; Claude follows them$/ })).toBeDefined()
  await unfold(ui, tap, 'sec-instructions')
  await ui.input({ plugin: PLUGIN, key: 'instructions', text: 'Lead the letter with the joint lease. Don’t include an I-765.', kind: 'submit' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^✓ Instructions saved\. Claude follows them from its next run\. To redo the packet with them now, use Tell Claude what to change\.$/ })).toBeDefined()

  await tap('nav-all')
  await tap('filed-group')
  await tap(`open:${haddad.path}`)
  expect(await ui.find({ type: 'Text', text: /^Filed/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'sec-instructions' })).toBeUndefined()
  expect(await ui.find({ type: 'Input', key: 'instructions' })).toBeUndefined()
  await ui.unmount()
})

test('documents reviewed, then the client sends more: add documents, review them again, and only the review runs', OPTS(), async ($, on) => {
  const kim = card('Kim I-129F', 'reviewed', DOCS)
  const run = agents(on, 'Reviewing the documents again: Kim I-129F')
  const { ui, tap, matters } = await boot($, on, [kim])
  // With nothing new, the build comes first, and adding more and looking again is under More you can do, each said plainly.
  await unfold(ui, tap, 'sec-more')
  expect(await ui.find({ type: 'Button', text: /^▾ More you can do$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /^Add documents… ›$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^What the client sent, or anything left out\. Then Review the documents again shows what’s still missing\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'do-review-again' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'do-change' })).toBeUndefined() // nothing is built yet
  await unfold(ui, tap, 'sec-details')
  expect(await ui.find({ type: 'Text', text: /^Client request$/ })).toBeDefined()

  // The client sends more: the page says which button works them in.
  await tap('do-add-files')
  expect(await ui.find({ type: 'Text', text: /^✓ Added 2 files\. Press Review the documents again to see what’s still missing, or Build packet to start the build with them\.$/ })).toBeDefined()
  // The server now counts them as new since the review (the next time the matter is opened).
  matters[0] = card('Kim I-129F', 'reviewed', [...DOCS, 'I-94.pdf'], { fresh: ['I-94.pdf'] })
  await tap('nav-all')
  await tap(`open:${kim.path}`)
  expect(await ui.find({ type: 'Text', text: /^1 new file arrived since Claude reviewed the documents\.$/ })).toBeDefined()
  expect(await inActions(ui, /About 5–10 minutes · see what’s still missing/)).toBeDefined()
  expect(await inActions(ui, /About 1–1½ hours · reviews them first/)).toBeDefined()

  // Documents has the same next step, so nobody has to go back to find it; starting it shows Claude at work.
  await tap('docs')
  expect(await ui.find({ type: 'Text', text: /^1 new file since Claude reviewed the documents\.$/ })).toBeDefined()
  await tap('main:review-again')
  expect(run.spawned.length).toBe(1)
  expect(String(run.spawned[0]!.prompt)).toMatch(/^Review the documents again\./)
  expect(String(run.spawned[0]!.description)).toBe('Reviewing the documents again: Kim I-129F')
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Reviewing the documents again$/ })).toBeDefined()
  await ui.unmount()
})

test('redo a step: Packet says what each step does, Redo from here says what happens, and the run names the step', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  const run = agents(on, 'Redoing Forms and the steps after it: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia])
  await tap('do-steps')
  expect(await ui.find({ type: 'Text', text: /^Fills the current USCIS forms from the documents/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'redo:docs_review' })).toBeDefined()
  await tap('redo:forms_preparer')
  expect(await ui.find({ type: 'Text', text: /^Claude redoes Forms and every step after it: Forms review, Cover letter, Research, Letter revision, Letter review, Packet, Final review, Your memo\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Document review stays as it is\.$/ })).toBeDefined()
  // Cancel changes nothing and goes back where it came from.
  await tap('main:redo-cancel')
  expect(await ui.find({ type: 'Text', text: /^Steps$/ })).toBeDefined()
  expect(run.spawned.length).toBe(0)

  await tap('redo:forms_preparer')
  await ui.input({ plugin: PLUGIN, key: 'redo-note', text: 'Use the 2024 tax return, not the 2023 one.', kind: 'change' })
  await tap('main:redo-start')
  expect(run.spawned.length).toBe(1)
  const prompt = String(run.spawned[0]!.prompt)
  expect(prompt).toMatch(/^Redo Forms \(forms_preparer\)\./)
  expect(prompt).toContain('instructions for this run (record what they settle on the open items, and redo whatever work they change):\nUse the 2024 tax return, not the 2023 one.')
  expect(String(run.spawned[0]!.description)).toBe('Redoing Forms and the steps after it: Garcia I-130 I-485')
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  await ui.unmount()
})

test('tell Claude what to change: it asks for the change, then the update carries it', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia])
  await tap('do-change')
  expect(await ui.find({ type: 'Text', text: /^What should Claude change\?$/ })).toBeDefined()
  await tap('main:redo-start')
  expect(run.spawned.length).toBe(0)
  expect(await ui.find({ type: 'Text', text: /^⚠ Type what Claude should change first\./ })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'redo-note', text: 'Lead the letter with the joint lease.', kind: 'change' })
  await tap('main:redo-start')
  expect(run.spawned.length).toBe(1)
  expect(String(run.spawned[0]!.prompt)).toMatch(/^Update the packet\.[\s\S]*instructions for this run[\s\S]*Lead the letter with the joint lease\.$/)
  await ui.unmount()
})

test('stop while Claude works: Stop asks first, then the matter shows where it stopped and Continue building', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { matters } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const stops: unknown[] = []
  on('tool.call', { tool: 'TaskStop' }, async (_$, e) => { stops.push(e); return { result: 'stopped' } as never })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  matters[0] = card('Garcia I-130 I-485', 'building', DOCS, { stage: i => (i < 3 ? 'passed' : i === 3 ? 'in_progress' : 'pending') })
  await clock.advance(15000)
  await clock.settle()
  // While it works, adding documents is still possible, and says what happens to them.
  await unfold(ui, tap, 'sec-more')
  expect(await ui.find({ type: 'Text', text: /^Claude won’t see them in this run\. When it finishes, Update the packet works them in\.$/ })).toBeDefined()
  await tap('stop')
  expect(await ui.find({ type: 'Text', text: /^Stop Claude now\? Everything finished so far is kept\. Continue building picks up where it stopped\.$/ })).toBeDefined()
  await tap('stop-keep')
  expect(await ui.find({ type: 'Text', text: /^Stop Claude now\?/ })).toBeUndefined()
  expect(stops).toHaveLength(0)
  await tap('stop')
  await tap('stop-yes')
  expect(stops).toMatchObject([{ tool: 'TaskStop', task_id: 'agent-1' }])
  expect(await ui.find({ type: 'Text', text: /^✓ Stopped\. Everything Claude finished is saved\. Continue building picks up where it stopped\.$/ })).toBeDefined()
  // The server still calls the step in progress, but nobody is on it: a pause, not a red Stopped.
  expect(await ui.find({ type: 'Text', text: /^Paused$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Stopped$/ })).toBeUndefined()
  expect(await inActions(ui, /Picks up at Cover letter/)).toBeDefined()
  // The list says the same: paused, not Claude is working.
  await tap('nav-all')
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Paused$/ })).toBeDefined()
  await tap(`open:${garcia.path}`)
  await tap('main:continue')
  expect(run.spawned.length).toBe(2)
  expect(String(run.spawned[1]!.prompt)).toMatch(/^Continue\./)
  await ui.unmount()
})

test('stopping keeps what the attorney typed: Continue building sends the same answers again', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'needs_you', DOCS)
  garcia.needs_you = [{ text: 'Include an I-765?', question: 'Include an I-765?', kind: 'decision', who: 'attorney', id: 'decide-i765' }]
  const { matters } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  const run = agents(on, 'Updating the packet: Garcia I-130 I-485')
  on('tool.call', { tool: 'TaskStop' }, async () => ({ result: 'stopped' }) as never)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('items')
  await ui.input({ plugin: PLUGIN, key: 'answer-decide-i765', text: 'Yes, include it.', kind: 'change' })
  await tap('main:update')
  expect(String(run.spawned[0]!.prompt)).toContain('Answer: Yes, include it.')
  // The matter moves on; the answer it keeps stays with it until a run settles its question.
  matters[0] = Object.assign(card('Garcia I-130 I-485', 'building', DOCS, { stage: i => (i < 1 ? 'passed' : i === 1 ? 'in_progress' : 'pending') }), { answers: (matters[0] as { answers?: unknown }).answers })
  await clock.advance(15000)
  await clock.settle()
  await tap('stop')
  await tap('stop-yes')
  expect(await ui.find({ type: 'Text', text: /^Paused$/ })).toBeDefined()
  await tap('main:continue')
  expect(run.spawned.length).toBe(2)
  expect(String(run.spawned[1]!.prompt)).toMatch(/^Continue\.[\s\S]*Answer: Yes, include it\./)
  await ui.unmount()
})

test('a stop before Claude changed anything keeps Try again, and the list never says Claude is working', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  const run = agents(on, 'Redoing Forms and the steps after it: Garcia I-130 I-485')
  on('tool.call', { tool: 'TaskStop' }, async () => ({ result: 'stopped' }) as never)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('do-steps')
  await tap('redo:forms_preparer')
  await ui.input({ plugin: PLUGIN, key: 'redo-note', text: 'Use the 2024 return.', kind: 'change' })
  await tap('main:redo-start')
  await tap('stop')
  await tap('stop-yes')
  expect(await ui.find({ type: 'Text', text: /^✓ Stopped before Claude changed anything\. Try again starts it again; Not now leaves the matter as it was\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Stopped$/ })).toBeDefined()
  await tap('main:retry-run')
  expect(run.spawned.length).toBe(2)
  expect(String(run.spawned[1]!.prompt)).toMatch(/^Redo Forms \(forms_preparer\)\.[\s\S]*Use the 2024 return\.$/)
  await ui.unmount()
})

test('after a build: a document taken out leads to Update the packet, and Clean up asks first', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  ;(garcia.documents as Record<string, unknown>).removed_since_build = ['IDs/Passport.pdf']
  const run = agents(on, 'Cleaning up working files: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia])
  expect(await ui.find({ type: 'Text', text: /^Since the packet was built, you took out Passport\.pdf\. Update the packet to bring it up to date and re-check it\.$/ })).toBeDefined()
  expect(await inActions(ui, /Brings the packet up to date/)).toBeDefined()
  await tap('do-closeout')
  expect(run.spawned.length).toBe(0)
  expect(await ui.find({ type: 'Text', text: /^Delete Claude’s working copies of the client’s documents\? Your documents and the finished files stay\.$/ })).toBeDefined()
  await tap('closeout-keep')
  expect(await ui.find({ type: 'Text', text: /^Delete Claude’s working copies/ })).toBeUndefined()
  await tap('do-closeout')
  await tap('closeout-yes')
  expect(run.spawned.length).toBe(1)
  expect(String(run.spawned[0]!.prompt)).toMatch(/^Clean up\./)
  await ui.unmount()
})

test('a stopped run can be set aside: Not now shows where the matter stands, with every way forward', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  agents(on, 'Running the officer’s review: Garcia I-130 I-485')
  const { clock, ui, tap } = await boot($, on, [garcia])
  await tap('do-stress')
  await ($ as never as { turn: { complete: (e: unknown) => Promise<unknown> } }).turn.complete({ agentId: 'agent-1', answer: '', reason: 'error', durationMs: 1000, isAborted: false, turnId: 't1' })
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Stopped$/ })).toBeDefined()
  await tap('dismiss-run')
  expect(await ui.find({ type: 'Text', text: /^Stopped$/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Draft packet$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'do-stress' })).toBeDefined()
  await tap('nav-all')
  expect(await ui.find({ type: 'Text', text: /^Needs you$/ })).toBeUndefined()
  await ui.unmount()
})

test('what’s left: Resolved shows what’s settled, and Reopen puts an item back on the list', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'draft', DOCS)
  const { ui, tap, requests } = await boot($, on, [garcia])
  await tap('items')
  expect(await ui.find({ type: 'Button', text: /^Resolved \(1\) ›$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Passport photos$/ })).toBeUndefined()
  await tap('resolved-group')
  expect(await ui.find({ type: 'Text', text: /^Passport photos$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Done \(marked by the attorney on October 28, 2026\)$/ })).toBeDefined()
  await tap('reopen:act-photos')
  expect(requests.at(-1)).toMatchObject({ op: 'reopen_item', matter_path: garcia.path, id: 'act-photos' })
  expect(await ui.find({ type: 'Text', text: /^✓ Back on the list\. Claude takes it up again on the next update\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^For you to do · 2$/ })).toBeDefined()
  await ui.unmount()
})

test('documents: a file opens, Remove asks first and keeps the file, and Put back returns it', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { ui, tap, requests } = await boot($, on, [garcia])
  await tap('docs')
  await tap('open-doc:Passport.pdf')
  expect(requests.at(-1)).toMatchObject({ op: 'open_document', matter_path: garcia.path, path: 'Passport.pdf' })
  await tap('remove:Passport.pdf')
  expect(await ui.find({ type: 'Text', text: /^Take Passport\.pdf out of the matter\? It’s kept, and Put back returns it\.$/ })).toBeDefined()
  await tap('remove-keep')
  expect(await ui.find({ type: 'Text', text: /^Take Passport\.pdf out/ })).toBeUndefined()
  expect(requests.some(r => r.op === 'remove_document')).toBe(false)
  await tap('remove:Passport.pdf')
  await tap('remove-yes:Passport.pdf')
  expect(requests.at(-1)).toMatchObject({ op: 'remove_document', path: 'Passport.pdf' })
  expect(await ui.find({ type: 'Text', text: /^✓ Removed Passport\.pdf from the matter\. It’s kept with the matter’s files: Put back, under Removed, returns it\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Removed · 1$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^1 file in the matter folder$/ })).toBeDefined()
  await tap('restore:output/removed documents/Passport.pdf')
  expect(requests.at(-1)).toMatchObject({ op: 'restore_document', kept: 'output/removed documents/Passport.pdf' })
  expect(await ui.find({ type: 'Text', text: /^✓ Passport\.pdf is back in the matter\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Removed · / })).toBeUndefined()
  await ui.unmount()
})

test('change what is being filed: it starts on the case as it is, says what happens, and the matter starts over', OPTS(), async ($, on) => {
  const kim = card('Kim I-130 I-485', 'reviewed', DOCS)
  const { ui, tap, requests } = await boot($, on, [kim])
  await tap('do-intake')
  expect(await ui.find({ type: 'Text', text: /^Now: I-130 \/ I-485 immediate relative · New filing$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^The steps start over for the new case, and your documents stay\./ })).toBeDefined()
  expect(await inActions(ui, /Choose a different case or posture/)).toBeDefined()
  // Nothing changed yet: the press says so instead of starting over.
  await tap('main:intake-save')
  expect(await ui.find({ type: 'Text', text: /^⚠ That’s what is being filed now\. Choose a different case, posture or way of filing, or press Cancel\.$/ })).toBeDefined()
  // Cancel leaves it as it was.
  await tap('main:intake-cancel')
  expect(await ui.find({ type: 'Text', text: /^Documents reviewed$/ })).toBeDefined()
  expect(requests.some(r => r.op === 'change_intake')).toBe(false)
  await tap('do-intake')
  await tap('type:n400')
  expect(await inActions(ui, /As N-400 naturalization/)).toBeDefined()
  await tap('main:intake-save')
  expect(requests.at(-1)).toMatchObject({ op: 'change_intake', matter_path: kim.path, matter_type: 'n400', filing_posture: 'new filing packet' })
  expect(await ui.find({ type: 'Text', text: /^✓ Changed\. The steps start over for the new case/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Ready to build$/ })).toBeDefined()
  await ui.unmount()
})

test('a folder made outside the app: choose what is being filed, then Save', OPTS(), async ($, on) => {
  const loose = card('Nguyen', 'ready', DOCS) as ReturnType<typeof card> & { needs_intake?: boolean }
  loose.needs_intake = true
  const { ui, tap, requests } = await boot($, on, [loose])
  expect(await ui.find({ type: 'Text', text: /^What is being filed\?$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /made outside Immigration Packet Builder/ })).toBeDefined()
  expect(await inActions(ui, /Build packet/)).toBeUndefined()
  await tap('main:set-intake')
  expect(await ui.find({ type: 'Text', text: /^Choose one below, then press Save\.$/ })).toBeDefined()
  await tap('type:n400')
  await tap('main:set-intake')
  expect(requests.at(-1)).toMatchObject({ op: 'set_intake', matter_path: loose.path, matter_type: 'n400', filing_posture: 'new filing packet' })
  expect(await ui.find({ type: 'Text', text: /^✓ Saved\. Claude knows what is being filed now\.$/ })).toBeDefined()
  await ui.unmount()
})

test('paused: when and where Claude stopped, and Continue building picks up there', OPTS(), async ($, on) => {
  // Two hours ago is yesterday in the first two hours after midnight.
  const chen = card('Chen I-765', 'paused', DOCS, { stage: i => (i < 3 ? 'passed' : 'pending'), updated: new Date(Date.now() - 2 * 3600000 - 60000).toISOString() })
  const run = agents(on, 'Building the packet: Chen I-765')
  const { ui, tap } = await boot($, on, [chen])
  expect(await ui.find({ type: 'Text', text: /^Paused$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Claude stopped working on this (?:2 hours ago|yesterday), at step 4 of 10 \(Cover letter\)\. Everything finished so far is saved\.$/ })).toBeDefined()
  expect(await inActions(ui, /Picks up at Cover letter/)).toBeDefined()
  await tap('main:continue')
  expect(run.spawned.length).toBe(1)
  expect(String(run.spawned[0]!.prompt)).toMatch(/^Continue\./)
  await ui.unmount()
})

test('waiting on the client: how many items, what they are, and Add files', OPTS(), async ($, on) => {
  const ramos = card('Ramos I-360', 'waiting_client', DOCS)
  ramos.needs_you = [{ text: 'Divorce decree', kind: 'blocker', who: 'client' }, { text: 'Two sworn letters from friends', kind: 'blocker', who: 'client' }]
  const { ui, tap, ops } = await boot($, on, [ramos])
  expect(await ui.find({ type: 'Text', text: /^Waiting on the client$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Waiting on the client for 2 items\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^• Two sworn letters from friends$/ })).toBeDefined()
  expect(await inActions(ui, /What the client sent/)).toBeDefined()
  expect(await inActions(ui, /Copy the client request/)).toBeDefined()
  await tap('main:add-files')
  expect(ops).toContain('add_documents')
  await ui.unmount()
})

test('ready to file, then marked as filed, then undone', OPTS(), async ($, on) => {
  const lopez = card('Lopez N-400', 'complete', DOCS)
  lopez.open_items = null
  const { ui, tap, requests, matters } = await boot($, on, [lopez])
  expect(await ui.find({ type: 'Text', text: /^Ready to file$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /follow the memo’s Filing logistics: signatures, photos, fees and mailing/ })).toBeDefined()
  matters[0] = card('Lopez N-400', 'filed', DOCS)
  await tap('mark-filed')
  expect(requests.at(-1)).toMatchObject({ op: 'mark_filed', matter_path: lopez.path })
  expect(await ui.find({ type: 'Text', text: /^✓ Lopez N-400 is marked as filed\. Undo, below, puts it back\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Filed October 20, 2026\.$/ })).toBeDefined()
  matters[0] = card('Lopez N-400', 'complete', DOCS)
  await tap('unmark-filed')
  expect(requests.at(-1)).toMatchObject({ op: 'unmark_filed', matter_path: lopez.path })
  expect(await ui.find({ type: 'Button', key: 'mark-filed' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^✓ Lopez N-400 is no longer marked as filed\.$/ })).toBeDefined()
  await ui.unmount()
})

test('a long document list: how many are shown, folders with their counts, and Show all', OPTS(), async ($, on) => {
  const files = Array.from({ length: 30 }, (_, i) => (i % 2 ? `Photos/IMG_${i}.jpg` : `Doc ${i}.pdf`))
  const okafor = card('Okafor I-140 I-485', 'ready', files)
  okafor.documents.count = 450
  okafor.documents.folders = [{ path: '', count: 200 }, { path: 'Photos', count: 250 }]
  const { ui, tap } = await boot($, on, [okafor])
  await tap('docs')
  expect(await ui.find({ type: 'Text', text: /^450 files · showing the 30 most recent$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Photos · 250$/ })).toBeDefined()
  expect((await ui.findAll({ type: 'Button', text: /^IMG_/ })).length).toBe(8)
  await tap('more:Photos')
  expect((await ui.findAll({ type: 'Button', text: /^IMG_/ })).length).toBe(15)
  expect(await ui.find({ type: 'Text', text: /…and 235 older in Finder/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'open-folder' })).toBeDefined()
  await ui.unmount()
})

test('when the app can’t start Claude, the request goes into the chat box, and the page follows once it starts', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  on('agent.spawn', async () => ({ deny: 'The server-side auto mode classifier gave no verdict for Agent' }))
  let listed: { id: string; description: string; type: string; status: AgentStatus }[] = []
  on('agent.list', async () => ({ value: listed }))
  const filled: string[] = []
  on('prompt.fill', async (_$, e) => { filled.push(e.text); return { isFilled: true } })
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  expect(filled.length).toBe(1)
  expect(filled[0]).toMatch(/^Build the packet for Garcia I-130 I-485 with Immigration Packet Builder, in the background\.\n\n/)
  expect(filled[0]).toContain(garcia.prompts.build)
  expect(await ui.find({ type: 'Text', text: /^Waiting for you$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Claude needs your OK to start\. Press Enter to send the request in your chat box\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /classifier/ })).toBeUndefined()

  // The attorney presses Enter; Claude starts the agent; the page switches by itself.
  listed = [{ id: 'agent-7', description: 'Building the packet: Garcia I-130 I-485', type: 'senior-associate:senior-associate', status: 'running' }]
  await clock.advance(15000)
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'watch' })).toBeDefined()
  await ui.unmount()
})

test('when the chat box can’t be filled either, the page says what to type', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  on('agent.spawn', async () => ({ deny: 'Permission to use Agent has been denied.' }))
  on('prompt.fill', async () => ({ isFilled: false }))
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  expect(await ui.find({ type: 'Text', text: /^⚠ Claude couldn’t start the build from here\. In the chat box below, type: Build the packet for Garcia I-130 I-485, then press Enter\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /denied/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Ready to build$/ })).toBeDefined()
  await ui.unmount()
})

test('your details: Enter saves and stays, Save goes back to where you came from', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { clock, ui, tap, requests, toasts } = await boot($, on, [garcia], { profile: {}, open: false }, { prefs: SEEN })
  expect(await ui.find({ type: 'Button', text: /^Add your details$/ })).toBeDefined()
  await tap('profile')
  expect(await ui.find({ type: 'Text', text: /^Saved on this Mac, in your Matters folder\.$/ })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'profile-attorney_name', text: 'Ana Ruiz' })
  await clock.settle()
  // The save shows on the page itself (the side panel can hold toasts): a green line at the top and a mark under the field.
  expect(await ui.find({ type: 'Text', text: /^✓ Saved\. Every build from now on uses your details\.$/ })).toBeDefined()
  expect(await ui.find({ key: 'saved:profile-attorney_name', text: /^✓ Saved$/ })).toBeDefined()
  expect(await ui.find({ key: 'saved:profile-bar_number' })).toBeUndefined()
  expect(toasts).not.toContain('Saved.')
  expect(await ui.find({ type: 'Input', key: 'profile-bar_number' })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'profile-bar_number', text: '24012345', kind: 'change' })
  await tap('main:save-profile')
  const saved = requests.filter(r => r.op === 'save_profile').at(-1)
  expect(saved?.profile).toMatchObject({ attorney_name: 'Ana Ruiz', bar_number: '24012345' })
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /^Your details$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^✓ Your details are saved\. Every build from now on uses them\.$/ })).toBeDefined()
  await ui.unmount()
})

test('the Your details question before a build: Add your details first, then back to the matter to build', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  const { ui, tap } = await boot($, on, [garcia], { profile: {} })
  await tap('main:build')
  await tap('main:gate-details')
  expect(await ui.find({ type: 'Input', key: 'profile-attorney_name' })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'profile-attorney_name', text: 'Ana Ruiz', kind: 'change' })
  await tap('main:save-profile')
  expect(await ui.find({ type: 'Text', text: /^✓ Your details are saved\. Press Build packet to start\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Garcia I-130 I-485$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Before you build$/ })).toBeUndefined()
  await tap('main:build')
  expect(run.spawned.length).toBe(1)
  await ui.unmount()
})

test('your details: the G-28 discipline answer, with an explanation only when there is an order', OPTS(), async ($, on) => {
  const { clock, ui, tap, requests } = await boot($, on, [card('Garcia I-130 I-485', 'ready', DOCS)], { profile: {}, open: false }, { prefs: SEEN })
  await tap('profile')
  expect(await ui.find({ type: 'Input', key: 'profile-discipline_order_details' })).toBeUndefined()
  await tap('discipline:yes')
  const saves = () => requests.filter(r => r.op === 'save_profile')
  expect(saves().at(-1)?.profile).toMatchObject({ subject_to_discipline_order: 'yes' })
  expect(await ui.find({ type: 'Text', text: /^✓ Saved\. Every build from now on uses your details\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Input', key: 'profile-discipline_order_details' })).toBeDefined()
  // Enter saves and stays on Your details.
  await ui.input({ plugin: PLUGIN, key: 'profile-discipline_order_details', text: 'Public reprimand, 2019', kind: 'submit' })
  await clock.settle()
  expect(saves().at(-1)?.profile).toMatchObject({ subject_to_discipline_order: 'yes', discipline_order_details: 'Public reprimand, 2019' })
  expect(await ui.find({ type: 'Input', key: 'profile-discipline_order_details' })).toBeDefined()
  expect(await ui.find({ key: 'saved:profile-discipline_order_details', text: /^✓ Saved$/ })).toBeDefined()
  await tap('discipline:no')
  expect(saves().at(-1)?.profile).toMatchObject({ subject_to_discipline_order: 'no', discipline_order_details: '' })
  expect(await ui.find({ type: 'Input', key: 'profile-discipline_order_details' })).toBeUndefined()
  await ui.unmount()
})

test('help: how it works, what each status means, and the way to the setup check', OPTS(), async ($, on) => {
  const { ui, tap, ops } = await boot($, on, [card('Garcia I-130 I-485', 'ready', DOCS)], { profile: {}, open: false }, { prefs: SEEN })
  expect(await ui.find({ type: 'Button', key: 'help', text: 'Help' })).toBeDefined()
  await tap('help')
  expect(await ui.find({ type: 'Text', text: /^Immigration Packet Builder 0\.9\.1$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^What each status means$/ })).toBeDefined()
  // How to go back, redo and change things, in the attorney's own questions.
  expect(await ui.find({ type: 'Text', text: /^How do I…$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Add documents after Claude has reviewed or built$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Redo one part, such as the forms or the letter$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^If something goes wrong$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Questions or a problem: github\.com\/passim-ai\/senior-associate\/issues$/ })).toBeDefined()
  await tap('help-setup')
  expect(ops).toContain('doctor')
  expect(await ui.find({ type: 'Text', text: /^Getting set up$/ })).toBeDefined()
  await tap('nav-back-setup')
  expect(await ui.find({ type: 'Text', text: /^What each status means$/ })).toBeDefined()
  await tap('nav-back-help')
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  await ui.unmount()
})

test('new matter: a case that is not in the list is described in words', OPTS(), async ($, on) => {
  const { clock, ui, tap, requests } = await boot($, on, [], { profile: {} }, { prefs: SEEN })
  await tap('main:new')
  await ui.input({ plugin: PLUGIN, key: 'name', text: 'lee', kind: 'change' })
  await tap('type:other')
  expect(await ui.find({ type: 'Input', key: 'other' })).toBeDefined()
  await ui.input({ plugin: PLUGIN, key: 'other', text: 'I-485 based on asylee status' })
  await clock.settle()
  const created = requests.find(r => r.op === 'create')
  expect(created).toMatchObject({ name: 'Lee', matter_type: 'I-485 based on asylee status', filing_posture: 'new filing packet' })
  await ui.unmount()
})

test('new matter: the VAWA cases are listed, and the folder name never says VAWA', OPTS(), async ($, on) => {
  const { ui, tap, requests } = await boot($, on, [], { profile: {} }, { prefs: SEEN })
  await tap('main:new')

  // Both VAWA cases are offered, each with its label and hint.
  expect(await ui.find({ type: 'Button', key: 'type:i360_vawa' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'type:i360_i485_vawa' })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /^○ I-360 VAWA self-petition$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', text: /^○ I-360 \/ I-485 VAWA self-petition and adjustment$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Self-petition and adjustment filed together/ })).toBeDefined()

  // The name a VAWA matter goes by here is the client's name and form numbers only, and its folder in Finder gets a
  // neutral name: the page says both.
  await ui.input({ plugin: PLUGIN, key: 'name', text: 'ramos', kind: 'change' })
  await tap('type:i360_vawa')
  expect(await ui.find({ type: 'Text', text: /^Here it will be called “Ramos I-360”\. Its folder in Finder gets a neutral name instead/ })).toBeDefined()
  await tap('type:i360_i485_vawa')
  expect(await ui.find({ type: 'Text', text: /^Here it will be called “Ramos I-360 I-485”\./ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /will be (named|called) .*VAWA/i })).toBeUndefined()

  await tap('main:create')
  const created = requests.find(r => r.op === 'create')
  expect(created).toMatchObject({ name: 'Ramos I-360 I-485', matter_type: 'i360_i485_vawa', filing_posture: 'new filing packet' })
  expect(String(created?.name)).not.toMatch(/VAWA/i)
  expect(await ui.find({ type: 'Text', text: /^Ramos I-360 I-485$/ })).toBeDefined()
  await ui.unmount()
})

test('new matter: a protected case with no short never puts its label in the folder name', OPTS(), async ($, on) => {
  const catalog = { ...CATALOG, matter_types: CATALOG.matter_types.map(t => (t.id === 'i360_vawa' ? { ...t, short: undefined } : t)) }
  const { clock, ui, tap, requests } = await boot($, on, [], { profile: {}, catalog }, { prefs: SEEN })
  await tap('main:new')
  await tap('type:i360_vawa')
  await ui.input({ plugin: PLUGIN, key: 'name', text: 'Ramos' })
  await clock.settle()
  expect(requests.find(r => r.op === 'create')).toMatchObject({ name: 'Ramos', matter_type: 'i360_vawa' })
  await ui.unmount()
})
