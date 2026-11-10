// BIA Edge and the Passim account behind it: what the app says about the research behind a letter, the way to a
// trial, the check of the law before filing, and what it does when Passim answers that the account has no research
// access. The connector is stood in for by the session's tool list (tests/world.ts, `tools`) and by answering
// `tool.call`; Passim's answers are written here as app/billing/mcp_gate.py writes them.
import { expect, test } from 'claude-code/testing'
import { denialOf } from '../hooks/library'
import { researchCheck } from '../hooks/server'
import { HEAD, WARN } from '../hooks/theme'
import { PLUGIN, DOCS, OPTS, agents, boot, card, unfold } from './world'

const EDGE = ['mcp__c0ffee__check_validity', 'mcp__c0ffee__search_cases']

const CHECKED = {
  state: 'checked', reason: '', headline: 'Checked November 9, 2026 with BIA Edge',
  lines: [
    'The research supports the letter with 24 authorities, 6 of them cases.',
    'Later treatment was checked for all 6 cases: 2 carry a limit that the research notes explain, and nothing adverse was found for the other 4.',
    '7 points were researched for this client beyond the standard authorities, and 9 adverse authorities were identified and answered.',
  ],
  caveat: 'A clean check means no adverse treatment was found in the library that day. It isn’t a guarantee that a case is still good law.',
  checked_at: '2026-11-09', receipt_at: '2026-11-09T21:00:00+00:00', age_days: 1, authorities: 24, cases: 6, not_researched: [] as string[], not_researched_count: 0,
  unresolved: ['The attorney has not confirmed the controlling circuit.'], similar: 0,
}
const WITHOUT = {
  state: 'without', reason: 'not_connected', headline: 'Researched without BIA Edge',
  lines: [
    'When the letter was researched, BIA Edge wasn’t connected.',
    'The research supports the letter with 13 authorities, 4 of them cases, as last verified October 30, 2026. Nothing after that was checked: not the cases’ later treatment, and not new decisions or policy.',
    '5 points specific to this client got no case-law research.',
  ],
  caveat: '', checked_at: '', age_days: null, authorities: 13, cases: 4,
  not_researched: ['A single DWI without aggravating elements is not a crime involving moral turpitude.', 'Unauthorized employment is weighed against stable work history.'],
  not_researched_count: 5, unresolved: [] as string[], similar: 0,
}

const TAIL = ' In Claude, Passim is listed as BIA Edge. No Passim research results were returned for this request.'
const TRIAL = `Start your 14-day free trial to use Passim research. A card is required, and after 14 days your plan renews at $29/month or $299/year unless you cancel.${TAIL}\n\n[Start your free trial](https://account.passimai.com/billing/start?intent=enroll)`
const ENDED = 'Your free trial of Passim, listed as BIA Edge in Claude, has ended. Plans are $29/month or $299/year. Subscribe to resume research; you won\'t need to reconnect your assistant. No Passim research results were returned for this request.\n\n[Subscribe](https://account.passimai.com/billing/start?intent=enroll)'
const REVOKED = `Research access has been disabled for this Passim account. Contact Passim support for help.${TAIL}\n\n[Review your Passim account](https://account.passimai.com/billing/access)`
const UNVERIFIED = `Passim could not verify account access. Please try again shortly.${TAIL}`

type Call = (e: unknown) => Promise<{ deny?: string; isError?: boolean; text?: string }>
const callOf = ($: unknown) => ($ as { tool: { call: Call } }).tool.call

test('Passim’s no-access answer is read in its own words; a moment’s fault and any other error are not', () => {
  expect(denialOf(TRIAL)).toEqual({ message: 'Start your 14-day free trial to use Passim research. A card is required, and after 14 days your plan renews at $29/month or $299/year unless you cancel.', plan: true })
  expect(denialOf(`Error: ${ENDED}`)).toEqual({ message: 'Your free trial of Passim, listed as BIA Edge in Claude, has ended. Plans are $29/month or $299/year. Subscribe to resume research; you won\'t need to reconnect your assistant.', plan: true })
  expect(denialOf(REVOKED)).toEqual({ message: 'Research access has been disabled for this Passim account. Contact Passim support for help.', plan: false })
  // Passim couldn't check the account just now: nothing about the account, and nothing to keep.
  expect(denialOf(UNVERIFIED)).toBeNull()
  expect(denialOf('The search timed out. Try again.')).toBeNull()
  expect(denialOf('')).toBeNull()
})

test('the research line: what BIA Edge is and costs when it isn’t connected, Passim’s words when the account has no access', () => {
  const none = researchCheck(false, null)
  expect(none).toMatchObject({ id: 'research', ok: false, level: 'optional', link: { id: 'passim_trial', label: 'Start a free trial' } })
  expect(none.detail).toMatch(/^BIA Edge is Passim’s immigration law library for Claude/)
  expect(none.detail).toMatch(/\$29 a month, with 14 days free for a new account \(a card is required\)\.$/)
  // Not connected: whatever Passim said last time is beside the point.
  expect(researchCheck(false, { message: 'x', at: '2026-11-10T15:00:00Z', plan: true, server: 'mcp__c0ffee' }).link?.id).toBe('passim_trial')
  const denied = researchCheck(true, { message: 'Your Passim free trial has ended.', at: '2026-11-10T15:00:00Z', plan: true, server: 'mcp__c0ffee' })
  expect(denied).toMatchObject({ ok: false, link: { id: 'passim_account', label: 'Open your Passim account' } })
  expect(denied.detail).toBe('BIA Edge is connected, but Passim returned no research on November 10, 2026: “Your Passim free trial has ended.”')
  // A plan doesn't fix a disabled account: the link is the one Passim itself gives for it.
  expect(researchCheck(true, { message: 'Disabled.', at: '2026-11-10T15:00:00Z', plan: false, server: 'mcp__c0ffee' }).link).toEqual({ id: 'passim_review', label: 'Review your Passim account' })
  expect(researchCheck(true, null)).toMatchObject({ ok: true, detail: 'BIA Edge is connected, so letters can cite case law.' })
})

test('setup without BIA Edge: what it is, what it costs, and a press that opens Passim’s sign-up in the browser', OPTS(), async ($, on) => {
  const { ui, tap, requests, toasts } = await boot($, on, [card('Garcia I-130 I-485', 'ready', DOCS)])
  await tap('nav-setup')
  expect(await ui.find({ type: 'Text', text: /^Case-law research \(optional\)$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^BIA Edge is Passim’s immigration law library for Claude: .* \$29 a month, with 14 days free for a new account \(a card is required\)\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Once you have an account, connect BIA Edge in Claude’s Connectors so letters can cite case law\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'setup-link:passim_trial' })).toMatchObject({ props: { label: 'Start a free trial ›' } })
  await tap('setup-link:passim_trial')
  // The app names the page; the server holds the address, and opens no other.
  expect(requests.at(-1)).toEqual(expect.objectContaining({ op: 'open_link', which: 'passim_trial' }))
  expect(Object.keys(requests.at(-1)!).sort()).toEqual(['exemplars_dir', 'matters_root', 'op', 'which'])
  expect(toasts.at(-1)).toBe('Opening Passim in your browser.')
  await tap('setup-link:connectors')
  expect(requests.at(-1)).toMatchObject({ op: 'open_link', which: 'connectors' })
  await ui.unmount()
})

test('research checked with BIA Edge: the matter’s page says what was checked and when, and the law can be checked again', OPTS(), async ($, on) => {
  const done = Object.assign(card('Lopez I-601A', 'complete', DOCS), { research: CHECKED })
  done.filing_readiness = { eligible: true, approved: false, digest: 'v1', blockers: [], risks: [], attorney: '', approved_at: '' }
  const run = agents(on, 'Checking the law again: Lopez I-601A')
  const { spawned } = run
  const notified: string[] = []
  on('ui.notify', async (_$, e) => { notified.push(e.text); return { value: { isSent: false, reason: 'no-surface' } } })
  const { ui, tap, requests, clock, matters } = await boot($, on, [done], { tools: EDGE })
  expect(await ui.find({ type: 'Text', text: /^Research$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Checked November 9, 2026 with BIA Edge$/ })).toMatchObject({ props: { color: HEAD } })
  expect(await ui.find({ type: 'Text', text: /^Later treatment was checked for all 6 cases: 2 carry a limit/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Still open: The attorney has not confirmed the controlling circuit\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^A clean check means no adverse treatment was found in the library that day\./ })).toBeDefined()
  // BIA Edge is there, so nothing sells it.
  expect(await ui.find({ type: 'Button', text: /Start a free trial/ })).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /Connect BIA Edge/ })).toBeUndefined()
  // Beside the approval too: when the law was last checked.
  await tap('packet')
  expect(await ui.find({ type: 'Text', text: /^The law the letter cites: checked November 9, 2026 with BIA Edge \(yesterday\)\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'approval-recheck' })).toMatchObject({ props: { label: 'Check the law again ›' } })
  await tap('nav-matter')
  await unfold(ui, tap, 'sec-more')
  expect(await ui.find({ type: 'Button', key: 'do-recheck' })).toMatchObject({ props: { label: 'Check the law again ›' } })
  expect(await ui.find({ type: 'Text', text: /^About 5 minutes\. Checks every case the letter cites for later treatment/ })).toBeDefined()
  await tap('research-recheck')
  expect(requests.find(r => r.op === 'start_run')).toMatchObject({ kind: 'recheck', matter_path: done.path })
  expect(String(spawned[0]?.prompt)).toMatch(/^Check the law again\./)
  expect(spawned[0]).toMatchObject({ description: 'Checking the law again: Lopez I-601A' })
  expect(await ui.find({ type: 'Text', text: /^Claude is working$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Checking the law again$/ })).toBeDefined()
  // While it runs, nothing offers to start it twice.
  expect(await ui.find({ type: 'Button', key: 'research-recheck' })).toBeUndefined()
  // It finishes, and the matter's record now shows a check made today: the notification says what was done (the
  // matter was ready to file before and still is), and the report is on the page under the check's own name.
  // (The receipt's time of writing is after the run's start: it is this run's work.)
  Object.assign(matters[0]!, { research: { ...CHECKED, checked_at: '2026-11-10', receipt_at: '2099-01-01T00:00:00+00:00', age_days: 0, headline: 'Checked November 10, 2026 with BIA Edge', treatment_checked: true } })
  await ($ as never as { turn: { complete: (e: unknown) => Promise<unknown> } }).turn.complete({ agentId: 'agent-1', answer: 'I checked the six cases and the updates since November 9. Nothing the letter relies on has changed.', reason: 'answer', durationMs: 1000, isAborted: false, turnId: 't1' })
  run.finish('completed')
  await clock.settle()
  expect(notified).toEqual(['Lopez I-601A: the law the letter cites has been checked again.'])
  expect(await ui.find({ type: 'Text', text: /^Check of the law · finished .*, took / })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Nothing the letter relies on has changed/ })).toBeDefined()
  await ui.unmount()
})

test('a law check that could not check says only that it finished, and the report says why', OPTS(), async ($, on) => {
  // Checked earlier the same day, by the build: today's date on the record is not this run's doing.
  const done = Object.assign(card('Lopez I-601A', 'complete', DOCS), { research: { ...CHECKED, age_days: 0, receipt_at: '2020-01-01T00:00:00+00:00', treatment_checked: true } })
  const run = agents(on, 'Checking the law again: Lopez I-601A')
  const notified: string[] = []
  on('ui.notify', async (_$, e) => { notified.push(e.text); return { value: { isSent: false, reason: 'no-surface' } } })
  const { ui, tap, clock } = await boot($, on, [done], { tools: EDGE })
  await tap('research-recheck')
  // BIA Edge returned Passim's notice to the agent, so the receipt is as it was before the run.
  await ($ as never as { turn: { complete: (e: unknown) => Promise<unknown> } }).turn.complete({ agentId: 'agent-1', answer: 'I could not check the law again: BIA Edge returned no research because the Passim trial has ended. Nothing was changed.', reason: 'answer', durationMs: 1000, isAborted: false, turnId: 't1' })
  run.finish('completed')
  await clock.settle()
  expect(notified).toEqual(['Lopez I-601A: the check of the law has finished. Open it to see what Claude found.'])
  expect(await ui.find({ type: 'Text', text: /BIA Edge returned no research because the Passim trial has ended/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Checked November 9, 2026 with BIA Edge$/ })).toBeDefined()
  await ui.unmount()
})

test('the library answered but the treatment check was not finished: said as a warning, with the check again', OPTS(), async ($, on) => {
  const partial = { ...CHECKED, treatment_checked: false, caveat: '', headline: 'Checked November 9, 2026 with BIA Edge; the check of later treatment wasn’t finished', lines: ['The research supports the letter with 24 authorities, 6 of them cases.', 'The check of the cases’ later treatment wasn’t finished.'] }
  const done = Object.assign(card('Lopez I-601A', 'complete', DOCS), { research: partial })
  const { ui } = await boot($, on, [done], { tools: EDGE })
  expect(await ui.find({ type: 'Text', text: /^Checked November 9, 2026 with BIA Edge; the check of later treatment wasn’t finished$/ })).toMatchObject({ props: { color: WARN } })
  expect(await ui.find({ type: 'Text', text: /^The check of the cases’ later treatment wasn’t finished\.$/ })).toBeDefined()
  // Not sold a trial and not told to redo the research: the library is here, and the check is what is missing.
  expect(await ui.find({ type: 'Button', key: 'research-recheck' })).toMatchObject({ props: { label: 'Check the law again ›' } })
  expect(await ui.find({ type: 'Button', key: 'research-redo' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', text: /Start a free trial/ })).toBeUndefined()
  await ui.unmount()
})

test('a check more than a week old is said so on the page', OPTS(), async ($, on) => {
  const done = Object.assign(card('Lopez I-601A', 'complete', DOCS), { research: { ...CHECKED, age_days: 12, checked_at: '2026-10-29', headline: 'Checked October 29, 2026 with BIA Edge' } })
  const { ui } = await boot($, on, [done], { tools: EDGE })
  expect(await ui.find({ type: 'Text', text: /^Checked October 29, 2026 with BIA Edge · 12 days ago$/ })).toBeDefined()
  await ui.unmount()
})

test('researched without BIA Edge: the page says what wasn’t checked and what got no case law, with the way to a trial', OPTS(), async ($, on) => {
  const draft = Object.assign(card('Lopez I-601A', 'draft', DOCS), { research: WITHOUT })
  draft.filing_readiness = { eligible: true, approved: false, digest: 'v1', blockers: [], risks: ['The letter was researched without BIA Edge: the cases it cites weren’t checked for later treatment, and nothing was checked for changes in the law.'], attorney: '', approved_at: '' }
  const { ui, tap, requests } = await boot($, on, [draft])
  expect(await ui.find({ type: 'Text', text: /^Researched without BIA Edge$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /Nothing after that was checked: not the cases’ later treatment/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^• A single DWI without aggravating elements is not a crime involving moral turpitude\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^…and 3 more\.$/ })).toBeDefined()
  // What it is and costs, once on the card, and the press.
  expect(await ui.find({ type: 'Button', key: 'research-link:passim_trial' })).toMatchObject({ props: { label: 'Start a free trial ›' } })
  expect(await ui.find({ type: 'Button', key: 'research-redo' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'research-recheck' })).toBeUndefined()
  await tap('research-link:passim_trial')
  expect(requests.at(-1)).toMatchObject({ op: 'open_link', which: 'passim_trial' })
  // The check of the law isn't offered without the library; asked for anyway, the page says why not.
  await unfold(ui, tap, 'sec-more')
  expect(await ui.find({ type: 'Button', key: 'do-recheck' })).toBeUndefined()
  await tap('packet')
  expect(await ui.find({ type: 'Text', text: /^The law the letter cites: researched without BIA Edge\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'approval-link:passim_trial' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'approval-recheck' })).toBeUndefined()
  await ui.unmount()
})

test('researched without BIA Edge, and it is connected now: the research step can be redone with it', OPTS(), async ($, on) => {
  const draft = Object.assign(card('Lopez I-601A', 'draft', DOCS), { research: WITHOUT })
  const { ui, tap } = await boot($, on, [draft], { tools: EDGE })
  expect(await ui.find({ type: 'Text', text: /^Researched without BIA Edge$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'research-link:passim_trial' })).toBeUndefined()
  expect(await ui.find({ type: 'Button', key: 'research-redo' })).toMatchObject({ props: { label: 'Redo the research with BIA Edge ›' } })
  await tap('research-redo')
  // The Redo screen, on the Research step: Claude redoes it and every step after it.
  expect(await ui.find({ type: 'Text', text: /Research/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'main:redo-start' })).toBeDefined()
  await ui.unmount()
})

test('Passim answers that the account has no access: the page and Setup say so in its words until research answers again', OPTS(), async ($, on) => {
  const draft = Object.assign(card('Lopez I-601A', 'draft', DOCS), { research: CHECKED })
  let reply: unknown = { result: undefined, isError: true, text: ENDED }
  on('tool.call', async () => reply as never)
  on('agent.list', async () => ({ value: [] }))
  const { ui, tap, requests, store, clock } = await boot($, on, [draft], { tools: EDGE })
  expect(await ui.find({ type: 'Text', text: /BIA Edge returned no research/ })).toBeUndefined()
  // The attorney's own chat asks BIA Edge something; Passim answers about the account. The call's answer is untouched.
  const res = await callOf($)({ tool: 'mcp__c0ffee__search_cases', query: 'extreme hardship to a citizen spouse' })
  expect(res).toMatchObject({ isError: true, text: ENDED })
  await clock.settle()
  expect(store.access).toMatchObject({ plan: true, server: 'mcp__c0ffee', message: expect.stringMatching(/^Your free trial of Passim, listed as BIA Edge in Claude, has ended\./) })
  expect(await ui.find({ type: 'Text', text: /^BIA Edge returned no research for your Passim account, so Claude can’t cite case law\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'ask-link:passim_account' })).toMatchObject({ props: { label: 'Open your Passim account ›' } })
  // The check of the law needs research that answers: pressed anyway, the page says what Passim said, with the way there.
  expect(await ui.find({ type: 'Button', key: 'research-recheck' })).toBeUndefined()
  await tap('nav-setup')
  expect(await ui.find({ type: 'Text', text: /^BIA Edge is connected, but Passim returned no research on .*: “Your free trial of Passim, listed as BIA Edge in Claude, has ended\./ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Until research answers again, letters are written without case-law research\.$/ })).toBeDefined()
  await tap('setup-link:passim_account')
  expect(requests.at(-1)).toMatchObject({ op: 'open_link', which: 'passim_account' })
  // An ordinary error from another connector changes nothing; nor does Passim failing to check the account for a moment.
  reply = { result: undefined, isError: true, text: 'The calendar is unavailable.' }
  await callOf($)({ tool: 'mcp__calendar__list_events' })
  reply = { result: undefined, isError: true, text: UNVERIFIED }
  await callOf($)({ tool: 'mcp__c0ffee__search_cases', query: 'x' })
  expect(store.access).toMatchObject({ plan: true })
  // Research answers again (the attorney subscribed): the line goes, here and on the matter's page.
  reply = { result: { ok: true }, text: '{"ok":true}' }
  await callOf($)({ tool: 'mcp__c0ffee__check_validity', document_ids: [300] })
  await clock.settle()
  expect(store.access).toBeNull()
  expect(await ui.find({ type: 'Text', text: /^BIA Edge is connected, so letters can cite case law\.$/ })).toBeDefined()
  await ui.unmount()
})

test('research answering again clears the notice, even when BIA Edge was added again under another name', OPTS(), async ($, on) => {
  const draft = Object.assign(card('Lopez I-601A', 'draft', DOCS), { research: CHECKED })
  const kept = { message: 'Your Passim free trial has ended.', at: '2026-11-08T15:00:00Z', plan: true, server: 'mcp__c0ffee' }
  let reply: unknown = { result: { ok: true }, text: '{"ok":true}' }
  on('tool.call', async () => reply as never)
  on('agent.list', async () => ({ value: [] }))
  // The connector is in the session under a new server name; the kept notice names the old one.
  const { ui, store, clock } = await boot($, on, [draft], { tools: ['mcp__fresh1d__check_validity', 'mcp__fresh1d__search_passages', 'mcp__docs__get_document'] }, { access: kept })
  expect(await ui.find({ type: 'Button', key: 'ask-link:passim_account' })).toBeDefined()
  // Another connector answering, even through a method BIA Edge also has, says nothing about Passim.
  await callOf($)({ tool: 'mcp__docs__get_document', id: 'x' })
  await clock.settle()
  expect(store.access).toMatchObject({ server: 'mcp__c0ffee' })
  // An error from BIA Edge that isn't Passim's notice (a timeout) leaves the notice as it was.
  reply = { result: undefined, isError: true, text: 'The search timed out.' }
  await callOf($)({ tool: 'mcp__fresh1d__search_passages', query: 'extreme hardship', document_id: 618 })
  expect(store.access).toMatchObject({ server: 'mcp__c0ffee' })
  // BIA Edge answering with results, by a method only its listing identifies: the notice goes.
  reply = { result: { ok: true }, text: '{"ok":true}' }
  await callOf($)({ tool: 'mcp__fresh1d__search_passages', query: 'extreme hardship', document_id: 618 })
  await clock.settle()
  expect(store.access).toBeNull()
  expect(await ui.find({ type: 'Button', key: 'ask-link:passim_account' })).toBeUndefined()
  await ui.unmount()
})

test('what Passim said is still on the page in the next session, with its date', OPTS(), async ($, on) => {
  const draft = Object.assign(card('Lopez I-601A', 'draft', DOCS), { research: WITHOUT })
  const kept = { message: 'Your Passim free trial has ended.', at: '2026-11-08T15:00:00Z', plan: true, server: 'mcp__c0ffee' }
  const { ui, tap } = await boot($, on, [draft], { tools: EDGE }, { access: kept })
  expect(await ui.find({ type: 'Text', text: /^BIA Edge is connected, but Passim returned no research on November 8, 2026: “Your Passim free trial has ended\.”$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'research-link:passim_account' })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'research-redo' })).toBeUndefined()
  await tap('nav-setup')
  expect(await ui.find({ type: 'Button', key: 'setup-link:passim_account' })).toBeDefined()
  await ui.unmount()
})

test('check the law again once BIA Edge has gone from the session: nothing starts, and the page says what it needs', OPTS(), async ($, on) => {
  const done = Object.assign(card('Lopez I-601A', 'complete', DOCS), { research: CHECKED })
  const o: { tools: string[] } = { tools: EDGE }
  const { ui, tap, requests } = await boot($, on, [done], o)
  expect(await ui.find({ type: 'Button', key: 'research-recheck' })).toBeDefined()
  // The connector was removed after the page was drawn: the press looks again before it starts anything.
  o.tools = []
  await tap('research-recheck')
  expect(requests.find(r => r.op === 'start_run')).toBeUndefined()
  expect(await ui.find({ type: 'Text', text: /^⚠ Checking the law again needs BIA Edge\. BIA Edge is Passim’s immigration law library for Claude/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'note-press:open-link:passim_trial' })).toMatchObject({ props: { label: 'Start a free trial' } })
  await tap('note-press:open-link:passim_trial')
  expect(requests.at(-1)).toMatchObject({ op: 'open_link', which: 'passim_trial' })
  // And the page now knows: the offer is gone, and the way to BIA Edge is there instead.
  expect(await ui.find({ type: 'Button', key: 'research-recheck' })).toBeUndefined()
  await ui.unmount()
})
