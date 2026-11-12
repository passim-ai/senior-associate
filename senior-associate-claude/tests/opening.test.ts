// How the app opens: beside the chat, on the matters list with every group folded, so no client's name is on screen
// (or left in the conversation) until the attorney asks for one; and the demo, which shows only the fictional sample
// matter from a folder of its own.
import { expect, test } from 'claude-code/testing'
import { ANA, DOCS, NO_GS, OPTS, PLUGIN, ROOT, SEEN, agents, boot, card, inActions, mount, open, world } from './world'

const DEMO = '/Users/example/Library/Application Support/Immigration Packet Builder/Demo'

// Everything on screen that has words: the texts and what each press is called.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function said(el: any, out: string[] = []): string[] {
  if (typeof el === 'string') out.push(el)
  else if (el && typeof el === 'object') {
    if (el.props?.label) out.push(String(el.props.label))
    for (const child of el.children ?? []) said(child, out)
  }
  return out
}

const command = ($: unknown, args: string) =>
  ($ as { command: { run: (e: unknown) => Promise<{ text?: string } | undefined> } }).command.run({ command: 'matters', args })

test('one matter does not open by itself: the list comes first, folded, and Show then Open reach it', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { ui, tap, requests } = await boot($, on, [garcia], { open: false, folded: true })
  // The server is never asked to pick the one matter.
  const lists = requests.filter(r => r.op === 'state' && !r.matter_path)
  expect(lists.length).toBeGreaterThan(0)
  expect(lists.every(r => r.auto_select === false)).toBe(true)
  expect(said(await ui.drawn()).filter(t => /Garcia/.test(t))).toEqual([])
  expect(await ui.find({ type: 'Text', text: /^In preparation$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^1 matter$/ })).toBeDefined()
  await tap('grp:preparing')
  await tap(`open:${garcia.path}`)
  expect(await inActions(ui, /Build packet/)).toBeDefined()
  await ui.unmount()
})

test('a search shows only the matters that match, in a folded list', OPTS(), async ($, on) => {
  const names = ['Garcia', 'Lopez', 'Nguyen', 'Bravo', 'Silva', 'Haddad', 'Okafor', 'Petrov']
  const seed = names.map(n => card(`${n} I-130 I-485`, 'ready', DOCS))
  const { ui, clock } = await boot($, on, seed, { open: false, folded: true })
  expect(said(await ui.drawn()).filter(t => names.some(n => t.includes(n)))).toEqual([])
  await ui.input({ plugin: PLUGIN, key: 'search', text: 'ngu', kind: 'change' })
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: `open:${ROOT}/Nguyen I-130 I-485` })).toBeDefined()
  expect(said(await ui.drawn()).filter(t => names.some(n => n !== 'Nguyen' && t.includes(n)))).toEqual([])
  await ui.unmount()
})

test('/matters opens the side panel on the folded list; a panel already open stays where it is; a closed one starts over', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { store } = world(on, [garcia, card('Lopez I-751', 'ready', DOCS)], { prefs: { ...SEEN, inlineUses: 0 } })
  let canPlace = true
  let paneUp = false
  const opened: string[] = []
  on('ui.open', async (_$, e) => { opened.push(e.id); paneUp = canPlace; return { value: { isPlaced: canPlace } } })
  on('ui.panes', async () => ({ value: paneUp ? [{ id: 'senior-associate', title: 'Immigration Packet Builder', isShown: true, isFocused: false, isPlaced: true }] : [] }))
  const { ui, tap } = await mount($, clock, true)

  expect((await command($, ''))?.text).toBe('Immigration Packet Builder is open in the side panel.')
  await clock.settle()
  expect(opened).toEqual(['senior-associate'])
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])
  // Opened beside the chat, it isn't counted as drawn in the conversation.
  expect((store.prefs as { inlineUses: number }).inlineUses).toBe(0)

  // With the panel up, /matters leaves the attorney where they are.
  await tap('show-all')
  await tap(`open:${garcia.path}`)
  await command($, '')
  await clock.settle()
  expect(await inActions(ui, /Build packet/)).toBeDefined()

  // The panel was closed on that matter: /matters starts at the folded list, not on the matter.
  paneUp = false
  await command($, '')
  await clock.settle()
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])
  expect(await ui.find({ type: 'Button', key: 'grp:preparing' })).toMatchObject({ text: 'Show' })

  // Where the panel can't be placed, and for /matters here, the app is drawn in the conversation, and counted so.
  canPlace = false
  paneUp = false
  expect((await command($, ''))?.text).toBe('Immigration Packet Builder')
  await clock.settle()
  expect((store.prefs as { inlineUses: number }).inlineUses).toBe(1)
  canPlace = true
  expect((await command($, 'here'))?.text).toBe('Immigration Packet Builder')
  await clock.settle()
  expect(opened.length).toBe(4)
  expect((store.prefs as { inlineUses: number }).inlineUses).toBe(2)
  await ui.unmount()
})

test('/matters demo: the demo’s own folder and no model letters, said on every screen; Leave the demo goes back to the folded list', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async (_$, e) => ({ value: e.name === 'HOME' ? '/Users/example' : undefined }))
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  agents(on, 'Building the packet: Garcia I-130 I-485')
  const { requests, store } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  expect(requests.at(-1)).toMatchObject({ op: 'state', matters_root: ROOT, exemplars_dir: `${ROOT}/Exemplar` })
  // A build is running on the attorney's own matter when the demo opens.
  await tap('main:build')

  const before = requests.length
  await command($, 'demo')
  await clock.settle()
  // Every request for the list goes to the demo's folder, asks for the sample, and reads no model letters.
  const asked = requests.slice(before).filter(r => !r.matter_path)
  expect(asked.length).toBeGreaterThan(0)
  for (const r of asked) expect([r.op, r.matters_root, r.exemplars_dir]).toEqual([r.op, DEMO, undefined])
  expect(asked.some(r => r.op === 'state' && r.ensure_sample === true && r.auto_select === false)).toBe(true)
  // The attorney's matter is off the screen, and every screen says this is the demo.
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Demo\. Only the fictional sample matter is shown; your own matters are not\.$/ })).toBeDefined()
  await tap('help')
  expect(await ui.find({ type: 'Text', text: /^Demo\. Only the fictional sample matter is shown/ })).toBeDefined()
  // What the demo opens is not remembered as the attorney's last matter.
  expect((store.prefs as { lastMatter: string }).lastMatter).toBe(garcia.path)

  // The build still running on the attorney's own matter keeps its place in their folder: its renewals name that
  // matter, and go there, while the list beside them is the demo's.
  const during = requests.length
  await clock.advance(16000)
  await clock.settle()
  const own = requests.slice(during).filter(r => r.matter_path === garcia.path)
  expect(own.some(r => r.op === 'heartbeat_run')).toBe(true)
  expect(own.every(r => r.matters_root === ROOT)).toBe(true)
  expect(requests.slice(during).filter(r => !r.matter_path).every(r => r.matters_root === DEMO)).toBe(true)
  expect(await ui.find({ type: 'Text', text: /Garcia/ })).toBeUndefined()

  // /matters again stays in the demo; only Leave the demo goes back, to the list with its groups folded.
  await command($, '')
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeDefined()
  const leaving = requests.length
  await tap('leave-demo')
  expect(requests.slice(leaving).length).toBeGreaterThan(0)
  expect(requests.slice(leaving).every(r => r.matters_root === ROOT)).toBe(true)
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: `open:${garcia.path}` })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'grp:working' })).toMatchObject({ text: 'Show' })
  await ui.unmount()
})

test('/matters demo finds the home folder from the plugin’s own folder when the Mac doesn’t say it', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async () => ({ value: undefined }))
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { requests } = world(on, [garcia], { prefs: SEEN })
  on('ui.open', async () => ({ value: { isPlaced: true } }))
  const { ui } = await mount($, clock, true)
  const before = requests.length
  await command($, 'demo')
  await clock.settle()
  const asked = requests.slice(before)
  expect(asked.length).toBeGreaterThan(0)
  expect(asked.every(r => /^\/(Users|home)\/[^/]+\/Library\/Application Support\/Immigration Packet Builder\/Demo$/.test(String(r.matters_root)))).toBe(true)
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeDefined()
  await ui.unmount()
})

// A panel the tests can open and close, as the host's own would be.
function panel(on: Parameters<typeof world>[0]) {
  const state = { up: true }
  on('ui.open', async () => { state.up = true; return { value: { isPlaced: true } } })
  on('ui.panes', async () => ({ value: state.up ? [{ id: 'senior-associate', title: 'Immigration Packet Builder', isShown: true, isFocused: false, isPlaced: true }] : [] }))
  return state
}

test('/matters on a closed panel clears the page before the panel shows, not once the server answers', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let held: Promise<void> | undefined
  let release: () => void = () => {}
  world(on, [garcia, card('Lopez I-751', 'ready', DOCS)], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA, hold: r => (r.op === 'state' && !r.matter_path ? held : undefined) })
  const pane = panel(on)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  expect(await ui.find({ type: 'Text', text: /^Garcia I-130 I-485$/ })).toBeDefined()

  // The panel went away on that matter without the app being told, and the server is slow to answer from here on.
  pane.up = false
  held = new Promise<void>(done => { release = done })
  await command($, '')
  await clock.settle()
  // Nothing has come back yet, and nothing of the matter is on the page: the list, folded.
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'main:build' })).toBeUndefined()
  held = undefined
  release()
  await clock.settle()
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])
  expect(await ui.find({ type: 'Button', key: 'grp:preparing' })).toMatchObject({ text: 'Show' })
  await ui.unmount()
})

test('the demo lists the sample alone; a build put off on one of the attorney’s matters can’t be started from inside it', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async (_$, e) => ({ value: e.name === 'HOME' ? '/Users/example' : undefined }))
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const run = agents(on, 'Building the packet: Garcia I-130 I-485')
  // Ghostscript is missing: Build is put off until the setup check passes.
  const { requests } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA, checks: NO_GS })
  panel(on)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  expect(await ui.find({ type: 'Text', text: /^Getting set up$/ })).toBeDefined()
  expect(run.spawned.length).toBe(0)

  await command($, 'demo')
  await clock.settle()
  // Only the sample is in the demo, shown like any matter once its group is opened.
  await tap('show-all')
  expect(await ui.find({ type: 'Button', key: `open:${DEMO}/Sample - Barrientos-Eckhardt` })).toBeDefined()
  expect(said(await ui.drawn()).filter(t => /Garcia/.test(t))).toEqual([])

  // Setup › Continue anyway, inside the demo: the build that was put off on the attorney's matter doesn't start, and
  // that matter is not opened.
  const before = requests.length
  await tap('nav-setup')
  await tap('main:setup-continue')
  expect(run.spawned.length).toBe(0)
  expect(requests.slice(before).filter(r => r.matter_path === garcia.path)).toEqual([])
  expect(said(await ui.drawn()).filter(t => /Garcia/.test(t))).toEqual([])
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeDefined()
  await ui.unmount()
})

test('an answer about one of the attorney’s matters that comes back after the demo opened is not put on the page', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async (_$, e) => ({ value: e.name === 'HOME' ? '/Users/example' : undefined }))
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let held: Promise<void> | undefined
  let release: () => void = () => {}
  const { requests } = world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA, hold: r => (r.op === 'set_instructions' ? held : undefined) })
  panel(on)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('sec-instructions')
  // The instructions are saved, and the server is slow to say so.
  held = new Promise<void>(done => { release = done })
  await ui.input({ plugin: PLUGIN, key: 'instructions', text: 'Lead with the joint lease.', kind: 'submit' })
  await clock.settle()
  expect(requests.at(-1)).toMatchObject({ op: 'set_instructions', matters_root: ROOT })

  await command($, 'demo')
  await clock.settle()
  held = undefined
  release()
  await clock.settle()
  // The late answer carries the attorney's matter and list: neither is on the page under the demo's line.
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeDefined()
  expect(said(await ui.drawn()).filter(t => /Garcia/.test(t))).toEqual([])
  await tap('show-all')
  expect(said(await ui.drawn()).filter(t => /Garcia/.test(t))).toEqual([])
  expect(await ui.find({ type: 'Button', key: `open:${DEMO}/Sample - Barrientos-Eckhardt` })).toBeDefined()
  await ui.unmount()
})

test('a start that timed out on one of the attorney’s matters is not said inside the demo, and never by name on the list', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async (_$, e) => ({ value: e.name === 'HOME' ? '/Users/example' : undefined }))
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const lopez = card('Lopez I-751', 'ready', DOCS)
  let box = ''
  on('agent.spawn', async () => ({ deny: 'auto mode' }))
  on('agent.list', async () => ({ value: [] }))
  on('prompt.fill', async (_$, e) => { box = e.text; return { isFilled: true } })
  on('prompt.read', async () => ({ value: { text: box, cursor: box.length } }))
  const { requests } = world(on, [garcia, lopez], { prefs: { ...SEEN, lastMatter: garcia.path } }, { profile: ANA })
  panel(on)
  const { ui, tap } = await mount($, clock)
  // Two starts wait in the chat box, unsent. The first times out while the attorney is on the list.
  await tap(`open:${garcia.path}`)
  await tap('main:build')
  await tap('nav-all')
  await tap('hide-all')
  for (let i = 0; i < 44; i++) await clock.advance(15000)
  await clock.settle()
  expect(requests.find(r => r.op === 'cancel_start' && r.matter_path === garcia.path)).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^⚠ A start for one of your matters in your chat box wasn’t sent\. Press Build packet to try again\.$/ })).toBeDefined()
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])

  // The second times out while the demo is on screen: it is still cancelled, in the attorney's own folder, and
  // nothing is said about it there.
  await tap('show-all')
  await tap(`open:${lopez.path}`)
  await tap('main:build')
  await command($, 'demo')
  await clock.settle()
  for (let i = 0; i < 44; i++) await clock.advance(15000)
  await clock.settle()
  expect(requests.find(r => r.op === 'cancel_start' && r.matter_path === lopez.path)).toMatchObject({ matters_root: ROOT })
  expect(await ui.find({ type: 'Text', text: /wasn’t sent/ })).toBeUndefined()
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])
  await ui.unmount()
})

test('Leave the demo while the demo is still loading: the attorney’s own list loads, and nothing is left waiting', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async (_$, e) => ({ value: e.name === 'HOME' ? '/Users/example' : undefined }))
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let held: Promise<void> | undefined
  let release: () => void = () => {}
  const { requests } = world(on, [garcia], { prefs: SEEN }, { profile: ANA, hold: r => (r.op === 'state' && r.matters_root === DEMO ? held : undefined) })
  panel(on)
  const { ui, tap } = await mount($, clock, true)
  await command($, 'demo')
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeDefined()
  // The demo's list is loading again, slowly, when Leave the demo is pressed.
  held = new Promise<void>(done => { release = done })
  await ui.press({ plugin: PLUGIN, key: 'nav-all' })
  await clock.settle()
  expect(requests.at(-1)).toMatchObject({ op: 'state', matters_root: DEMO })
  const leaving = requests.length
  await tap('leave-demo')
  expect(requests.slice(leaving).some(r => r.op === 'state' && r.matters_root === ROOT)).toBe(true)
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'grp:preparing' })).toMatchObject({ text: 'Show' })
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /couldn’t open|One moment|⏳/ })).toBeUndefined()
  held = undefined
  release()
  await clock.settle()
  // The demo's late answer changes nothing: the attorney's own list stays, folded.
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Barrientos/ })).toBeUndefined()
  await tap('grp:preparing')
  expect(await ui.find({ type: 'Button', key: `open:${garcia.path}` })).toBeDefined()
  await ui.unmount()
})

test('a message left on the list is gone when the panel is opened again', OPTS(), async ($, on) => {
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const pane = panel(on)
  let held: Promise<void> | undefined
  let release: () => void = () => {}
  const { clock, ui, tap } = await boot($, on, [garcia, card('Lopez I-751', 'ready', DOCS)], { hold: r => (r.op === 'state' && !r.matter_path ? held : undefined) })
  // Archiving a matter says so on the list, by name.
  await tap('do-archive')
  expect(await ui.find({ type: 'Text', text: /^✓ Garcia I-130 I-485 is archived\./ })).toBeDefined()
  // The panel is closed and opened again, the server slow to answer: the message is not there to be read.
  pane.up = false
  held = new Promise<void>(done => { release = done })
  await command($, '')
  await clock.settle()
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  held = undefined
  release()
  await clock.settle()
  expect(said(await ui.drawn()).filter(t => /Garcia|Lopez/.test(t))).toEqual([])
  await ui.unmount()
})

test('an error about one of the attorney’s matters that comes back after the demo opened is said to nobody', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async (_$, e) => ({ value: e.name === 'HOME' ? '/Users/example' : undefined }))
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  let held: Promise<void> | undefined
  let release: () => void = () => {}
  const o: Parameters<typeof world>[3] = { profile: ANA, hold: r => (r.op === 'set_instructions' ? held : undefined) }
  world(on, [garcia], { prefs: { ...SEEN, lastMatter: garcia.path } }, o)
  panel(on)
  const { ui, tap } = await mount($, clock)
  await tap(`open:${garcia.path}`)
  await tap('sec-instructions')
  // The instructions are being saved when the matter's folder is moved in Finder: the server will answer with an
  // error that names it.
  held = new Promise<void>(done => { release = done })
  await ui.input({ plugin: PLUGIN, key: 'instructions', text: 'Lead with the joint lease.', kind: 'submit' })
  await clock.settle()
  o.gone = [garcia.path]
  await command($, 'demo')
  await clock.settle()
  held = undefined
  release()
  await clock.settle()
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeDefined()
  expect(said(await ui.drawn()).filter(t => /Garcia|isn.t in your Matters folder/.test(t))).toEqual([])
  await ui.unmount()
})

test('a demo folder the server names by another path, through a link, still loads, and its sample opens there', OPTS(), async ($, on) => {
  const { clock } = await open($, on)
  on('env.get', async (_$, e) => ({ value: e.name === 'HOME' ? '/Users/example' : undefined }))
  const LINKED = '/Volumes/Data/PacketDemo'
  const garcia = card('Garcia I-130 I-485', 'ready', DOCS)
  const { requests } = world(on, [garcia], { prefs: SEEN }, { profile: ANA, demoCanonical: LINKED })
  panel(on)
  const { ui, tap } = await mount($, clock, true)
  await command($, 'demo')
  await clock.settle()
  expect(requests.some(r => r.op === 'state' && r.matters_root === DEMO)).toBe(true)
  expect(await ui.find({ type: 'Button', key: 'leave-demo' })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Matters$/ })).toBeDefined()
  await tap('show-all')
  expect(said(await ui.drawn()).filter(t => /Garcia/.test(t))).toEqual([])
  // The sample is asked for where the server keeps it, and opens.
  await tap(`open:${LINKED}/Sample - Barrientos-Eckhardt`)
  expect(requests.at(-1)).toMatchObject({ op: 'state', matters_root: LINKED, matter_path: `${LINKED}/Sample - Barrientos-Eckhardt` })
  expect(await ui.find({ type: 'Text', text: /^Sample - Barrientos-Eckhardt$/ })).toBeDefined()
  // Left, the attorney's own list is back, asked of their own folder.
  const leaving = requests.length
  await tap('leave-demo')
  expect(requests.slice(leaving).every(r => r.matters_root === ROOT)).toBe(true)
  expect(await ui.find({ type: 'Button', key: 'grp:preparing' })).toMatchObject({ text: 'Show' })
  await ui.unmount()
})
