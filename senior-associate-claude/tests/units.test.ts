// The app's pure parts, one by one: the status every screen shows (row by row against the status table in
// docs/EXPERIENCE.md), the words it shows (plain text, friendly errors, briefs, times, names), how it reads Claude's
// questions, the counts, and the research gate's matching.
import type { Card, CardStatus, Lease, Run } from '../types'
import { expect, test } from 'claude-code/testing'
import { neededBeforeFiling, neededParts, reportQuestions } from '../hooks/matter'
import { holdsTerm, isResearch, onlyCitations, readTerms } from '../hooks/privacy'
import { notInBrief } from '../hooks/runs'
import { sortRows } from '../hooks/screens/home'
import { timelineDays } from '../hooks/screens/timeline'
import { matterStatus } from '../hooks/status'
import { brief, capitalizeWords, friendly, plainText, time, when } from '../hooks/words'

const NOW = Date.parse('2026-10-29T15:00:00Z')
const ago = (minutes: number) => new Date(NOW - minutes * 60000).toISOString()

function status(phase: string, extra: Partial<CardStatus> = {}): CardStatus {
  return { phase, label: '', running: [], step_index: 1, step_total: 10, lease: null, open_items_state: 'ok', ...extra }
}
const lease = (o: Partial<Lease> = {}): Lease => ({ run_id: 'run-1', kind: 'build', holder: 'orchestrator', started_at: ago(5), heartbeat_at: ago(1), fresh: true, ...o })
function run(o: Partial<Run> = {}): Run {
  return {
    agentId: 'agent-1', kind: 'build', matter: '/m/A', name: 'A', label: 'Building the packet', startedAt: ago(10), endedAt: '', status: 'running',
    answer: '', reason: '', reply: '', step: '', stepLabel: '', lastSeen: '', lastChangeAt: ago(10), waitingOk: false, ...o,
  }
}

test('the status table, row by row: each status from the server, with its words, and the app adding only what it alone knows', () => {
  const rows: [string, string][] = [
    ['new', 'Needs documents'], ['ready', 'Ready to build'], ['reviewed', 'Documents reviewed'], ['building', 'Claude is working'],
    ['paused', 'Paused'], ['needs_you', 'Needs your answer'], ['waiting_client', 'Waiting on the client'], ['draft', 'Draft packet'],
    ['complete', 'Ready to file'], ['filed', 'Filed'],
  ]
  for (const [phase, label] of rows) {
    const s = matterStatus({ phase, status: status(phase) }, null, NOW)
    expect([s.phase, s.label]).toEqual([phase, label])
  }
  // The server's own words win when it gives them.
  expect(matterStatus({ phase: 'complete', status: status('complete', { label: 'Complete' }) }, null, NOW).label).toBe('Complete')
  // Waiting for you: a start waits in the chat box; once the server says Claude is working, it is.
  expect(matterStatus({ phase: 'ready', status: status('ready') }, run({ status: 'starting' }), NOW)).toMatchObject({ phase: 'starting', label: 'Waiting for you', group: 'needs_you' })
  // The app's own lease for that start (the server says building) is still the start waiting; once the orchestrator
  // renews it, Claude is at work.
  expect(matterStatus({ phase: 'building', status: status('building', { lease: lease({ holder: 'app' }) }) }, run({ status: 'starting', runId: 'run-1' }), NOW).phase).toBe('starting')
  expect(matterStatus({ phase: 'building', status: status('building', { lease: lease({ holder: 'orchestrator' }) }) }, run({ status: 'starting', runId: 'run-1' }), NOW).phase).toBe('building')
  expect(matterStatus({ phase: 'building', status: status('building', { lease: lease({ holder: 'app', run_id: 'someone-else' }) }) }, run({ status: 'starting', runId: 'run-1' }), NOW).phase).toBe('building')
  // Claude is working in the app's own agent, or elsewhere (the chat, an orchestrator started by hand).
  expect(matterStatus({ phase: 'ready', status: status('ready') }, run(), NOW)).toMatchObject({ phase: 'building', elsewhere: false })
  expect(matterStatus({ phase: 'building', status: status('building', { lease: lease() }) }, null, NOW)).toMatchObject({ phase: 'building', elsewhere: true, group: 'working' })
  // Stopped: a run of this session's stopped and hasn't been set aside; set aside, the matter's own status shows.
  const stopped = run({ status: 'failed', endedAt: ago(2), reason: 'error' })
  expect(matterStatus({ phase: 'paused', status: status('paused') }, stopped, NOW)).toMatchObject({ phase: 'stopped', label: 'Stopped', group: 'needs_you' })
  expect(matterStatus({ phase: 'paused', status: status('paused') }, { ...stopped, dismissed: true }, NOW).phase).toBe('paused')
  // ...and once someone starts another run after it stopped, that run is what shows.
  expect(matterStatus({ phase: 'building', status: status('building', { lease: lease({ started_at: ago(1) }) }) }, stopped, NOW).phase).toBe('building')
  // Filed stays filed whatever ended before.
  expect(matterStatus({ phase: 'filed', status: status('filed') }, stopped, NOW).phase).toBe('filed')
})

test('the status never reads a time: a matter the server calls paused is paused, however recently a step was marked running', () => {
  const c = { phase: 'paused', status: status('paused'), progress: { stages: [{ id: 'forms_preparer', label: 'Forms', status: 'in_progress' }] } } as never
  expect(matterStatus(c, null, NOW).phase).toBe('paused')
})

test('two matters at once: each has its own status from its own run', () => {
  const a = matterStatus({ phase: 'ready', status: status('ready') }, run({ matter: '/m/A' }), NOW)
  const b = matterStatus({ phase: 'building', status: status('building', { lease: lease(), running: [{ id: 'forms_reviewer', label: 'Forms review' }, { id: 'cover_letter_writer_draft', label: 'Cover letter' }] }) }, null, NOW)
  expect([a.phase, a.elsewhere, b.phase, b.elsewhere]).toEqual(['building', false, 'building', true])
})

test('a list row says what the server says: a finished run’s report never changes it, and building is never Paused', () => {
  const done = run({ status: 'done', endedAt: ago(1), answer: 'Built the draft packet. Two items need attorney decision before filing.' })
  expect(matterStatus({ phase: 'draft', label: 'Draft packet' }, done, NOW).label).toBe('Draft packet')
  expect(matterStatus({ phase: 'building', label: 'Claude is working' }, done, NOW).phase).toBe('building')
  expect(matterStatus({ phase: 'building', label: 'Claude is working' }, run({ status: 'failed', endedAt: ago(1), dismissed: true }), NOW).phase).toBe('building')
  // A card from the same server, with its list, says the same.
  const card = { phase: 'draft', status: status('draft', { label: 'Draft packet' }), open_items: { open: [] } } as never
  expect(matterStatus(card, done, NOW).label).toBe('Draft packet')
})

test('a run with no progress for 20 minutes is stalled, unless it waits for the attorney’s OK', () => {
  expect(matterStatus({ phase: 'building' }, run({ lastChangeAt: ago(21) }), NOW).stalled).toBe(true)
  expect(matterStatus({ phase: 'building' }, run({ lastChangeAt: ago(21), waitingOk: true }), NOW).stalled).toBe(false)
  expect(matterStatus({ phase: 'building' }, run({ lastChangeAt: ago(5) }), NOW).stalled).toBe(false)
})

test('plain text for an email: headings, bold, code and links become plain words; lists stay', () => {
  expect(plainText('# Needed\n\n**Your I-94.** See [the CBP site](https://i94.cbp.dhs.gov).\n* one\n\n\n\nThanks')).toBe('Needed\n\nYour I-94. See the CBP site (https://i94.cbp.dhs.gov).\n- one\n\nThanks')
  expect(plainText('`code` and __under__ and _it_')).toBe('code and under and it')
})

test('friendly errors: the host’s own in plain words, the server’s sentences kept, anything of a program’s never shown', () => {
  expect(friendly('spawn EACCES')).toMatch(/^Immigration Packet Builder can’t save in your Matters folder\./)
  expect(friendly('The process timed out after 600000 ms')).toBe('That took too long and was stopped. Try again.')
  expect(friendly("Garcia I-130 isn't in your Matters folder anymore. It may have been moved or renamed in Finder.")).toMatch(/^Garcia I-130 isn't in your Matters folder anymore\./)
  expect(friendly('Claude is already working on this matter. Try again when it finishes.')).toBe('Claude is already working on this matter. Try again when it finishes.')
  for (const raw of ['', 'KeyError: matter_path', 'Traceback (most recent call last)', 'Could not read /Users/someone/Matters/x/open-items.json.', 'Stage forms_preparer failed.', 'Bad value {"a": 1}.', 'release_action']) {
    expect(friendly(raw)).toMatch(/^That didn’t work, and nothing was changed\. Try again\./)
  }
})

test('brief: the first sentences within the limit, ids and paths left out', () => {
  expect(brief('Upload the passport (open item doc-passport.json). It is missing.')).toBe('Upload the passport. It is missing.')
  const long = `${'A sentence of some length that goes on. '.repeat(10)}`
  expect(brief(long, 100).length).toBeLessThanOrEqual(100)
  expect(brief(long, 100).endsWith('.')).toBe(true)
})

test('when: just now, minutes, hours, yesterday, a date', () => {
  time.now = NOW
  expect(when(ago(0))).toBe('just now')
  expect(when(ago(12))).toBe('12 min ago')
  expect(when('')).toBe('')
  expect(when('not a date')).toBe('')
  expect(when(new Date(NOW - 86400000).toISOString())).toMatch(/yesterday|Oct 28/)
  time.now = 0
})

test('names with particles: the small words stay lower case except at the start', () => {
  expect(capitalizeWords('maria de la cruz')).toBe('Maria de la Cruz')
  expect(capitalizeWords('ana dos santos')).toBe('Ana dos Santos')
  expect(capitalizeWords('jan van der berg')).toBe('Jan van der Berg')
  expect(capitalizeWords('de la rosa')).toBe('De la Rosa')
  expect(capitalizeWords('omar bin rashid')).toBe('Omar bin Rashid')
  expect(capitalizeWords('lucía y garcía')).toBe('Lucía y García')
  expect(capitalizeWords('DE LEON')).toBe('DE LEON') // typed in capitals: left as typed
})

test('a report’s questions: the numbered list it ends with, wrapped lines joined', () => {
  expect(reportQuestions('I reviewed it.\n\n1. Should we include an I-765?\n2. Which entry date is right,\n   2018 or 2019?')).toEqual(['Should we include an I-765?', 'Which entry date is right, 2018 or 2019?'])
  expect(reportQuestions('Done. Nothing to ask.')).toEqual([])
})

test('needed before filing: the parts of the server’s counts always add up to the total', () => {
  const needed = neededBeforeFiling({ counts: { needed_before_filing: 99, blocking: { client: 1, you: 1, risks: 1 }, decisions_open: 0, decisions_answered: 0, open_total: 5, resolved_total: 0 } } as unknown as Card)
  expect(needed).toEqual({ total: 3, client: 1, you: 1, risks: 1 })
  expect(neededParts(needed)).toBe('1 from the client, 1 for you and 1 risk to weigh')
})

test('the brief carries only the answers the server’s brief doesn’t already', () => {
  const reply = '1. Include an I-765?\n   Answer: Yes.\n2. Which address?\n   Answer: The Austin one.'
  expect(notInBrief(reply, 'Update.\nSaved answers:\n- Include an I-765? Yes.')).toBe('1. Which address?\n   Answer: The Austin one.')
  expect(notInBrief(reply, 'Update.')).toBe(reply)
  expect(notInBrief('free text answers', 'Update.')).toBe('free text answers')
})

test('the research gate: BIA Edge and the web tools only, and a term matches however it is written', () => {
  expect(isResearch('mcp__biaedge__search_cases')).toBe(true)
  expect(isResearch('mcp__claude_ai_BIA_Edge__check_validity')).toBe(true)
  expect(isResearch('mcp__passim__lookup')).toBe(true)
  expect(isResearch('WebSearch')).toBe(true)
  expect(isResearch('mcp__github__create_issue')).toBe(true)
  expect(isResearch('Read')).toBe(false)
  const terms = ['Ana Example', 'A123456789', '555-0142']
  expect(holdsTerm({ query: 'Is ana example eligible for a waiver?' }, terms)).toBe(true)
  expect(holdsTerm({ query: 'A-123-456-789 removal history' }, terms)).toBe(true)
  expect(holdsTerm({ query: 'call 555 0142' }, terms)).toBe(true)
  expect(holdsTerm({ query: 'Matter of Example, 25 I&N Dec. 1 (BIA 2010): good faith marriage' }, terms)).toBe(false)
  expect(holdsTerm({ query: 'What evidence shows a bona fide marriage?' }, terms)).toBe(false)
})

test('the gate matches the server’s names, full names and identifiers, without accents, and passes a precedent’s name', () => {
  const t = readTerms({ terms: [], names: ['García', 'Example'], full_names: ['Ana García Example'], identifiers: ['A-123-456-789'] })
  expect(holdsTerm({ query: 'Garcia bona fide marriage' }, t)).toBe(true)
  expect(holdsTerm({ query: 'García bona fide marriage' }, readTerms({ names: ['Garcia'] }))).toBe(true)
  expect(holdsTerm({ query: 'ana garcia example' }, readTerms({ full_names: ['Ana García Example'] }))).toBe(true)
  expect(holdsTerm({ query: 'A123 456789' }, t)).toBe(true)
  expect(holdsTerm({ citation: 'Matter of Garcia, 16 I&N Dec. 653 (BIA 1978)' }, t)).toBe(false)
  expect(holdsTerm({ query: 'Garcia, 16 I&N Dec. 653: good faith marriage' }, t)).toBe(false)
  expect(holdsTerm({ query: 'Garcia v. Holder on stop-time' }, t)).toBe(false)
  expect(holdsTerm({ query: 'Matter of Garcia and our client Garcia' }, t)).toBe(true)
  expect(onlyCitations({ citation: 'Matter of Garcia, 16 I&N Dec. 653 (BIA 1978)' })).toBe(true)
  expect(onlyCitations({ citation: 'Matter of Garcia, and Ana García Example’s divorce' })).toBe(false)
})

test('the timeline groups by day, newest first; the list sorts within its groups', () => {
  time.now = NOW
  const days = timelineDays([
    { at: ago(60 * 30), kind: 'created', text: 'Matter created.', actor: 'attorney' },
    { at: ago(5), kind: 'run_started', text: 'Build started.', actor: 'app' },
    { at: ago(1), kind: 'stage_passed', text: 'Forms review passed.', actor: 'claude' },
  ], NOW)
  expect(days.map(d => d.day)).toEqual(['Today', 'Yesterday'])
  expect(days[0]!.events.map(e => e.text)).toEqual(['Forms review passed.', 'Build started.'])
  time.now = 0
  const row = (name: string, updated: string, kase: string, phase: string) => ({ m: { name, path: `/m/${name}`, phase, case_line: kase, updated_at: updated } as never, s: { phase } as never })
  const rows = [row('Bravo', ago(1), 'N-400', 'draft'), row('alpha', ago(9), 'I-751', 'stopped'), row('Charlie', ago(5), 'I-130', 'new')]
  expect(sortRows(rows, 'updated').map(r => r.m.name)).toEqual(['Bravo', 'Charlie', 'alpha'])
  expect(sortRows(rows, 'name').map(r => r.m.name)).toEqual(['alpha', 'Bravo', 'Charlie'])
  expect(sortRows(rows, 'case').map(r => r.m.name)).toEqual(['Charlie', 'alpha', 'Bravo'])
  expect(sortRows(rows, 'status').map(r => r.m.name)).toEqual(['alpha', 'Bravo', 'Charlie'])
})
