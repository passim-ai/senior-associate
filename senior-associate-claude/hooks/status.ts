// A matter's status: one function, used by the pill, the matter page's card, the matters list, the band's subtitle
// and the notification. The server is the source of truth (CONTRACTS §4); the app adds only what it alone knows,
// from its own run record: a start waiting in the chat box, a run of this session's that stopped and hasn't been set
// aside, and Claude at work in the app's own agent before the server's next look. Nothing here reads a file's time.
import type { Card, CardStatus, Lease, MatterRow, RowLease, Run } from '../types'
import { REVIEW_KINDS, STALL_MS, asksAttorney, builtPast, partway, reviewOnly } from './matter'
import { ACCENT_LIGHT, AMBER_TINT, GREEN_TINT, NAVY_TINT, RED_TINT, SURFACE } from './theme'


// One name per status, the same on the pill, the card title and the list (docs/EXPERIENCE.md, "Status names").
export const PHASE_LABEL: Record<string, string> = {
  new: 'Needs documents', ready: 'Ready to build', reviewed: 'Documents reviewed', building: 'Claude is working', paused: 'Paused',
  needs_you: 'Needs your answer', waiting_client: 'Waiting on the client', draft: 'Draft packet', complete: 'Ready to file', filed: 'Filed',
  starting: 'Waiting for you', stopped: 'Stopped', problem: 'Can’t open',
}

// The status chip's fill: the accent's light shade where the attorney is needed, navy's where the work goes on, amber's
// where it waits, green once it can be filed, red when it stopped, and the plain chip otherwise. The text on each is
// the one colour that reads on it (theme.ts, onFill).
export const PHASE_FILL: Record<string, string> = {
  new: SURFACE, ready: NAVY_TINT, reviewed: NAVY_TINT, building: NAVY_TINT, paused: AMBER_TINT, needs_you: ACCENT_LIGHT, waiting_client: AMBER_TINT,
  draft: AMBER_TINT, complete: GREEN_TINT, filed: SURFACE, starting: ACCENT_LIGHT, stopped: RED_TINT, problem: RED_TINT,
}

// Which group of the matters list a status sits in.
export type Group = 'needs_you' | 'working' | 'preparing' | 'ready' | 'filed'
const GROUP: Record<string, Group> = {
  needs_you: 'needs_you', stopped: 'needs_you', starting: 'needs_you', problem: 'needs_you', building: 'working',
  new: 'preparing', ready: 'preparing', reviewed: 'preparing', paused: 'preparing', waiting_client: 'preparing', draft: 'preparing',
  complete: 'ready', filed: 'filed',
}

export type MatterStatus = {
  /** What the matter shows: the server's phase, or starting / stopped / building from the app's own run. */
  phase: string
  label: string
  fill: string
  group: Group
  /** The server's phase underneath what the app adds: what the matter shows once a stop is set aside. */
  base: string
  /** The app's own run that explains the phase (Waiting for you, Stopped, or Claude at work in the app's agent). */
  run: Run | null
  /** Claude is at work, but not in this session's agent: the chat, an orchestrator started by hand, an older plugin. */
  elsewhere: boolean
  /** The app's agent has shown no progress for STALL_MS (it may be waiting for an OK in the chat, or stuck). */
  stalled: boolean
  lease: Lease | RowLease | null
}

// The parts of a card or a list row the status reads: a card's status, or a row's phase, label and run lease.
export type StatusSource = Pick<Card, 'phase'> & Partial<Pick<Card, 'status'>> & Partial<Pick<MatterRow, 'label' | 'lease'>>

const at = (iso: string | undefined) => Date.parse(iso ?? '')

// The fresh lease is the one the app took for its own start that waits in the chat box.
function startHeldByApp(lease: Lease | RowLease | null, r: Run): boolean {
  return Boolean(lease && r.runId && lease.run_id === r.runId && (lease.holder === 'app' || !lease.holder))
}

export function matterStatus(c: StatusSource, r: Run | null | undefined, now: number): MatterStatus {
  const server: CardStatus | undefined = c.status
  const base = server?.phase ?? c.phase
  const noList = server?.open_items_state === 'missing'
  // A card's lease is in its status; a list row's beside its phase. Either way it says whose run holds the matter.
  const lease = server?.lease ?? c.lease ?? null
  const row = !server
  let phase = base
  let run: Run | null = null
  if (r?.status === 'running') {
    // The app's own agent is at work. The server says so too once start_run has taken the lease.
    phase = 'building'
    run = r
  } else if (r?.status === 'starting' && (base !== 'building' || startHeldByApp(lease, r))) {
    // The request waits in the chat box for the attorney's Enter. The lease the app took for it makes the server say
    // building, but that is still this start, waiting: only once the orchestrator renews the lease (its holder
    // changes) or the agent appears is Claude at work.
    phase = 'starting'
    run = r
  } else if (r?.status === 'failed' && !r.dismissed && base !== 'filed' && !(lease?.fresh && at(lease.started_at) > at(r.endedAt))
    && !(row && base === 'building')) {
    // A run of this session's stopped, and nobody has started another since (a newer lease would say so). A list row
    // the server says is building is Claude at work again (from the chat, say), never a red Stopped.
    phase = 'stopped'
    run = r
  } else if (r?.status === 'done' && r.answer && noList && base !== 'building' && base !== 'filed' && asksAttorney(r.answer)) {
    // With no list of open items (a run that wrote none), a report that ends in questions is how Claude asks. A list
    // row never reads the report: its words are the server's.
    phase = 'needs_you'
    run = r
  }
  const lastMove = run?.status === 'running' ? at(run.lastChangeAt || run.startedAt) : NaN
  const stalled = run?.status === 'running' && !run.waitingOk && Number.isFinite(lastMove) && now - lastMove > STALL_MS
  return {
    phase,
    label: (phase === base && (server?.label || c.label)) || (PHASE_LABEL[phase] ?? phase),
    fill: PHASE_FILL[phase] ?? SURFACE,
    group: GROUP[phase] ?? 'preparing',
    base,
    run,
    elsewhere: phase === 'building' && !run,
    stalled,
    lease,
  }
}

// Claude is at work on the matter, or about to be: nothing else may start, and changes wait.
export const isBusy = (s: MatterStatus) => s.phase === 'building' || s.phase === 'starting'

// A list group's title.
export const GROUP_TITLE: Record<Group, string> = {
  needs_you: 'Needs you', working: 'Claude is working', preparing: 'In preparation', ready: 'Ready to file', filed: 'Filed',
}

// What to do with files just added, said where the attorney is looking: the press that works them in on this matter now.
export function afterAdding(c: Card | null | undefined, run: Run | undefined, now: number): string {
  if (!c) return ''
  const s = matterStatus(c, run, now)
  if (isBusy(s)) {
    const next = run && REVIEW_KINDS.has(run.kind) ? 'Review the documents again' : 'Update the packet'
    return `Claude is working on this matter right now and won’t see them in this run. When it finishes, ${next} works them in.`
  }
  if (s.phase === 'stopped') return 'Press Try again to go on with them.'
  if (reviewOnly(c)) return 'Press Review the documents again to see what’s still missing, or Build packet to start the build with them.'
  if (builtPast(c)) return 'Press Update the packet to work them in.'
  return partway(c) ? 'Press Continue building to go on with them.' : ''
}
