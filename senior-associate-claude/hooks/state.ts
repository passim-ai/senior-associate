// What the app holds for the session: its values in $.state (they outlive a hot reload), what the attorney is
// typing (kept here so a keystroke doesn't redraw the page), and the module's own bookkeeping.
import { atom, read, update } from 'claude-code'
import type { Atom } from 'claude-code'
import type { EngineInterface } from 'claude-code'
import type { Draft, Note, BackTo, Payload, Prefs, Profile, Run, Setup, View } from '../types'
import { MATTERS_ASK, NEW_FOLDER, NO_UV, STILL_WORKING, UV_ASK } from './words'

export const PANE = 'senior-associate'

// The matters folder and model letters folder come from the plugin's settings (its userConfig).
// The rest is this module's own bookkeeping; a hot reload starts it over, and session.start rebuilds what matters.
export const session = {
  config: { matters_root: '', exemplars_dir: '' } as { matters_root: string; exemplars_dir: string },
  prefsLoaded: false,
  lastRaw: '', // the last error as the server or the host said it, sent with a question asked while it shows
  inFlight: false, // one server action at a time
  waitingOn: '', // what the action in flight is waiting for, told to a click that arrives meanwhile
  uvPath: '',
  savedField: '', // the box whose save was pressed last, marked "✓ Saved" until the screen changes
  setupPassed: false, // once the setup check has passed in a session, a build doesn't ask again
  ticking: false,
  kickoff: false, // a first load scheduled from a draw; drawing itself must not write state
  askRound: 0, // bumped when a question goes, so the ask box comes back empty
  seq: 0, // bumped by every change the app makes to the payload, so an older refresh can tell it was overtaken
  refreshFails: 0, // quiet refreshes failed in a row
  poll: undefined as { cancel: () => void } | undefined, // the one 15-second timer
  flight: 0, // which load holds the page; Close the picker moves it on so the abandoned one's answer is dropped
  launching: new Set<string>(), // matters with a start in flight: set at the press, before any await, so a second press can't start a second agent
  matter: '', // the open matter's path, kept in step with the payload so a press knows it without waiting
  sampleAsked: false, // the first load of a new attorney's session has asked the server for the sample matter
}

// What the attorney is typing, until it is saved or sent.
export const typed = {
  name: '', // what the New matter field holds, for the Create button
  redo: '', // what the attorney wants changed, on the Redo screen
  savedRedo: '', // what its save last kept, for "✓ Saved" until the text changes
  other: '', // the case described in words, when it isn't in the list
  profile: {} as Profile, // Your details as typed, saved on Save
  instructions: {} as Record<string, string>, // Additional attorney instructions as typed, by matter path, until saved
  ask: {} as Record<string, string>, // a question in the matter's ask box, by matter path, until sent
  language: '', // another language for the client request, typed under Other…
  // each question's answer as typed, by answerKey(); `${path}#reply` is the one box for a report's questions
  answers: {} as Record<string, string>,
}

export const liveAgents = new Set<string>() // our running agents, so the tool hooks can skip everything else at once

const S = { plugin: 'senior-associate' } as const
const view = atom({ ...S, key: 'view' } as const, 'home' as View)
const payload = atom({ ...S, key: 'payload' } as const, null as Payload | null)
export const EMPTY_DRAFT: Draft = { name: '', typeId: '', posture: '', other: '' }
const draft = atom({ ...S, key: 'draft' } as const, EMPTY_DRAFT)
export const NO_NOTE: Note = { text: '', tone: 'warn' }
const note = atom({ ...S, key: 'note' } as const, NO_NOTE)
const busy = atom({ ...S, key: 'busy' } as const, false)
const runs = atom({ ...S, key: 'runs' } as const, {} as Record<string, Run>)
export const FRESH: Prefs = { onboarded: false, lastMatter: '', setupSeen: false, inlineUses: 0, pickerSeen: false }
const prefs = atom({ ...S, key: 'prefs' } as const, FRESH)
const filter = atom({ ...S, key: 'filter' } as const, '')
// Answers to the Needs-your-answer questions, keyed by answerKey(); a field's typing lives in typed.answers.
const answers = atom({ ...S, key: 'answers' } as const, {} as Record<string, string>)
const setup = atom({ ...S, key: 'setup' } as const, null as Setup | null)
const gate = atom({ ...S, key: 'gate' } as const, null as { matter: string; kind: string; reply: string } | null)
const origins = atom({ ...S, key: 'origins' } as const, {} as Partial<Record<'profile' | 'setup' | 'help' | 'request', BackTo>>)
const expanded = atom({ ...S, key: 'expanded' } as const, [] as string[])
const caseMissing = atom({ ...S, key: 'caseMissing' } as const, false)
// Bumped when the side panel opens, so the /matters rows in the conversation redraw and point to it.
const docked = atom({ ...S, key: 'docked' } as const, 0)
// The Redo screen's subject: a step to redo from, 'docs_review' for a fresh document review, '' for Tell Claude what to change.
const redoAt = atom({ ...S, key: 'redo' } as const, null as { matter: string; stage: string; from: View } | null)
// A press that waits on "Yes" first: stopping Claude, or taking a document out of the matter.
const confirm = atom({ ...S, key: 'confirm' } as const, '')
// A start is on its way (between the press and the agent's start): the start buttons wait.
const launching = atom({ ...S, key: 'launching' } as const, [] as string[])
// The matters list's order, kept for the session.
const sort = atom({ ...S, key: 'sort' } as const, 'updated')

type Value<A> = A extends Atom<infer T> ? T : never

// $.state is read and written in this file alone: the engine lists the values each module touches by reading
// atoms declared in the same file, so every other file reads and changes them through these.
export function readView($: EngineInterface) { return read($, view) }
export function updateView($: EngineInterface, change: Parameters<typeof update<Value<typeof view>>>[2]) { return update($, view, change) }
export function readPayload($: EngineInterface) { return read($, payload) }
export function updatePayload($: EngineInterface, change: Parameters<typeof update<Value<typeof payload>>>[2]) {
  return update($, payload, value => {
    const next = change(value)
    session.matter = next?.matter?.path ?? ''
    return next
  })
}
export function readDraft($: EngineInterface) { return read($, draft) }
export function updateDraft($: EngineInterface, change: Parameters<typeof update<Value<typeof draft>>>[2]) { return update($, draft, change) }
export function readNote($: EngineInterface) { return read($, note) }
export function readBusy($: EngineInterface) { return read($, busy) }
export function updateBusy($: EngineInterface, change: Parameters<typeof update<Value<typeof busy>>>[2]) { return update($, busy, change) }
export function readRuns($: EngineInterface) { return read($, runs) }
export function updateRuns($: EngineInterface, change: Parameters<typeof update<Value<typeof runs>>>[2]) { return update($, runs, change) }
export function readPrefs($: EngineInterface) { return read($, prefs) }
export function readFilter($: EngineInterface) { return read($, filter) }
export function updateFilter($: EngineInterface, change: Parameters<typeof update<Value<typeof filter>>>[2]) { return update($, filter, change) }
export function readAnswers($: EngineInterface) { return read($, answers) }
export function updateAnswers($: EngineInterface, change: Parameters<typeof update<Value<typeof answers>>>[2]) { return update($, answers, change) }
export function readSetup($: EngineInterface) { return read($, setup) }
export function updateSetup($: EngineInterface, change: Parameters<typeof update<Value<typeof setup>>>[2]) { return update($, setup, change) }
export function readGate($: EngineInterface) { return read($, gate) }
export function updateGate($: EngineInterface, change: Parameters<typeof update<Value<typeof gate>>>[2]) { return update($, gate, change) }
export function readOrigins($: EngineInterface) { return read($, origins) }
export function updateOrigins($: EngineInterface, change: Parameters<typeof update<Value<typeof origins>>>[2]) { return update($, origins, change) }
export function readExpanded($: EngineInterface) { return read($, expanded) }
export function updateExpanded($: EngineInterface, change: Parameters<typeof update<Value<typeof expanded>>>[2]) { return update($, expanded, change) }
export function readCaseMissing($: EngineInterface) { return read($, caseMissing) }
export function updateCaseMissing($: EngineInterface, change: Parameters<typeof update<Value<typeof caseMissing>>>[2]) { return update($, caseMissing, change) }
export function readDocked($: EngineInterface) { return read($, docked) }
export function updateDocked($: EngineInterface, change: Parameters<typeof update<Value<typeof docked>>>[2]) { return update($, docked, change) }
export function readRedoAt($: EngineInterface) { return read($, redoAt) }
export function updateRedoAt($: EngineInterface, change: Parameters<typeof update<Value<typeof redoAt>>>[2]) { return update($, redoAt, change) }
export function readLaunching($: EngineInterface) { return read($, launching) }
export function updateLaunching($: EngineInterface, change: Parameters<typeof update<Value<typeof launching>>>[2]) { return update($, launching, change) }
export function readSort($: EngineInterface) { return read($, sort) }
export function updateSort($: EngineInterface, change: Parameters<typeof update<Value<typeof sort>>>[2]) { return update($, sort, change) }
export function readConfirm($: EngineInterface) { return read($, confirm) }
export function updateConfirm($: EngineInterface, change: Parameters<typeof update<Value<typeof confirm>>>[2]) { return update($, confirm, change) }

// ---------- what the app remembers between sessions ----------


export async function loadPrefs($: EngineInterface) {
  session.prefsLoaded = true
  try {
    const raw = (await $.store.get('prefs')) as Partial<Prefs> | undefined
    if (raw && typeof raw === 'object') {
      await update($, prefs, () => ({
        onboarded: raw.onboarded === true,
        lastMatter: typeof raw.lastMatter === 'string' ? raw.lastMatter : '',
        setupSeen: raw.setupSeen === true,
        inlineUses: typeof raw.inlineUses === 'number' ? raw.inlineUses : 0,
        pickerSeen: raw.pickerSeen === true,
      }))
    }
  } catch {
    // a fresh install has nothing stored
  }
}

export async function remember($: EngineInterface, patch: Partial<Prefs>) {
  const current = await read($, prefs)
  const next = { ...current, ...patch }
  await update($, prefs, () => next)
  try {
    await $.store.set('prefs', next)
  } catch {
    // the session still has it
  }
}

// A message about something Claude can fix carries the request; the note then offers to send it.
// `press` offers one of the app's own presses beside it ("Close the picker", "Go back to Matters").
export async function setNote($: EngineInterface, text: string, tone: Note['tone'] = 'warn', given?: string, press?: Note['press']) {
  const ask = given ?? (text.includes(NEW_FOLDER) ? MATTERS_ASK : text === NO_UV ? UV_ASK : undefined)
  // A message is said in plain words; the raw error it came from is kept only while this message shows.
  if (tone !== 'warn' || !text) session.lastRaw = ''
  await update($, note, () => ({ text, tone, ...(ask ? { ask } : {}), ...(press ? { press } : {}) }))
}

// A click while an action is in flight says why nothing else can happen yet, instead of doing nothing.
export async function stillWorking($: EngineInterface) {
  await setNote($, session.waitingOn || STILL_WORKING, 'wait', undefined, session.waitingOn ? { id: 'close-picker', label: 'Close the picker' } : undefined)
}

// The screens that belong to one matter, all reached from its page.
export const MATTER_VIEWS: View[] = ['matter', 'documents', 'packet', 'items', 'memo', 'request', 'redo', 'intake', 'timeline']

// Change screens: a message about the last screen doesn't follow the attorney to the next.
export async function go($: EngineInterface, v: View) {
  session.savedField = ''
  await setNote($, '')
  await update($, confirm, () => '')
  await update($, view, () => v)
}

// A hot reload starts this module over, with the session's values kept: rebuild what the module had from them, so a
// run in progress is still ours, saved answers are still in their boxes, and a passed setup check isn't asked again.
export async function rebuildSession($: EngineInterface) {
  const [all, saved, s, p] = await Promise.all([read($, runs), read($, answers), read($, setup), read($, payload)])
  session.matter = p?.matter?.path ?? ''
  // What was in flight died with the old module (its server call, its press): nothing is busy or starting now, so the
  // page and its start buttons aren't left dimmed waiting for an answer that can't come.
  await update($, busy, () => false)
  await update($, launching, () => [])
  for (const r of Object.values(all)) if (r.status === 'running' && r.agentId) liveAgents.add(r.agentId)
  typed.answers = { ...saved, ...typed.answers }
  if (s && s.checks.length > 0 && !s.checks.some(ch => ch.required && !ch.ok)) session.setupPassed = true
}

// The attorney has the matter open: how its last run ended is seen, so /matters no longer opens it first.
export async function markSeen($: EngineInterface, path: string) {
  const r = (await read($, runs))[path]
  if (!r || r.seen !== false) return
  await update($, runs, all => (all[path] ? { ...all, [path]: { ...all[path]!, seen: true } } : all))
}
