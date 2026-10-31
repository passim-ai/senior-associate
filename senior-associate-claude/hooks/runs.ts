// Starting Claude on a matter and following it: the app's own background agent, its report, its notification.
import type { EngineInterface } from 'claude-code'
import type { Card, Lease, Run, View } from '../types'
import { AGENT, BUILDS, ENDED, REVIEW_KINDS, STEP_KINDS, clientCount, missingCount, neededBeforeFiling, needsOf, profileIsEmpty, progressSig, replyKey, requiredMissing, runKind, stepOf, stepText } from './matter'
import type { Need } from './matter'
import { call, doctor, refresh, setPayload } from './server'
import { MATTER_VIEWS, go, liveAgents, readAnswers, readPayload, readRuns, readView, session, setNote, stillWorking, typed, updateAnswers, updateGate, updateOrigins, updateRuns, updateSetup } from './state'
import { nowIso, nowMs, plural } from './words'
import { matterStatus } from './status'

// The save beside an answer box keeps the answer in the matter (the server's save_answer), so it survives quitting
// Claude, and says so where the attorney is looking: "✓ Saved" under the box and a line at the top that names the
// button that sends it.
export async function saveAnswer($: EngineInterface, c: Card, qkey: string, question: string, value: string, sendWith: string) {
  const key = `${c.path}#${qkey}`
  typed.answers[key] = value
  session.savedField = key
  await updateAnswers($, all => ({ ...(all ?? {}), [key]: value }))
  try {
    const res = await call($, { op: 'save_answer', matter_path: c.path, matter: c.path, key: qkey, question, answer: value.trim() })
    if ((await readPayload($))?.matter?.path === c.path) await setPayload($, res)
  } catch (err) {
    await setNote($, err instanceof Error ? err.message : String(err))
    return
  }
  await setNote($, value.trim() ? `Answer saved. Claude gets it when you press ${sendWith}.` : 'Answer cleared.', 'ok')
}

// Every answer typed on this matter that differs from what the matter keeps goes to the server's save_answer, so it
// survives a quit and the next brief carries it.
async function keepTypedAnswers($: EngineInterface, c: Card) {
  const prefix = `${c.path}#`
  const needs = needsOf(c)
  for (const [key, value] of Object.entries(typed.answers)) {
    if (!key.startsWith(prefix)) continue
    const qkey = key.slice(prefix.length)
    if ((c.answers[qkey]?.answer ?? '') === value.trim()) continue
    const question = needs.find(n => n.qkey === qkey)?.question
    if (!question) continue
    try {
      await call($, { op: 'save_answer', matter_path: c.path, matter: c.path, key: qkey, question, answer: value.trim() })
    } catch {
      // the brief carries it anyway
    }
  }
}

// The answer a question shows: what is typed, else what this session saved, else what the matter keeps.
export function answerFor(c: Card, qkey: string, saved: Record<string, string>): string {
  const key = `${c.path}#${qkey}`
  return typed.answers[key] ?? saved[key] ?? c.answers[qkey]?.answer ?? ''
}
export function savedAnswerFor(c: Card, qkey: string, saved: Record<string, string>): string | undefined {
  return saved[`${c.path}#${qkey}`] ?? c.answers[qkey]?.answer
}

// Additional attorney instructions go into the matter folder, where every run's brief points and every step reads them.
// The matter as saved comes back, so a run started right after has the brief that names them.
export async function saveInstructions($: EngineInterface, c: Card, text: string): Promise<Card | null> {
  if (session.inFlight) {
    await stillWorking($)
    return null
  }
  session.inFlight = true
  try {
    const next = await call($, { op: 'set_instructions', matter_path: c.path, text })
    await setPayload($, next)
    delete typed.instructions[c.path]
    return next.matter
  } catch (err) {
    await setNote($, err instanceof Error ? err.message : String(err))
    return null
  } finally {
    session.inFlight = false
  }
}

export async function composeAnswers($: EngineInterface, needs: Need[], questions: string[], c: Card): Promise<string> {
  const saved = await readAnswers($)
  const lines: string[] = []
  for (const n of needs) {
    if (n.who !== 'attorney') continue
    const answer = answerFor(c, n.qkey, saved).trim()
    if (answer) lines.push(`${lines.length + 1}. ${n.question}${n.id ? ` (open item ${n.id})` : ''}\n   Answer: ${answer}`)
  }
  questions.forEach((q, i) => {
    const key = `${c.path}#report-${i}`
    const answer = (typed.answers[key] ?? saved[key] ?? '').trim()
    if (answer) lines.push(`${lines.length + 1}. ${q}\n   Answer: ${answer}`)
  })
  const reply = (typed.answers[replyKey(c)] ?? saved[replyKey(c)] ?? '').trim()
  if (!lines.length && reply) lines.push(reply)
  return lines.join('\n')
}

// The answers the brief still needs: the server writes every saved answer into the brief itself, so an answer it
// already carries isn't repeated; the rest (typed but not saved) are numbered again.
export function notInBrief(reply: string, brief: string): string {
  const items = reply.trim() ? reply.trim().split(/\n(?=\d+\. )/) : []
  if (items.length <= 1 && !/^\d+\. /.test(items[0] ?? '')) return reply.trim()
  const left = items.filter(it => {
    const answer = it.match(/\n\s*Answer: ([\s\S]*)$/)?.[1]?.trim()
    return !answer || !brief.includes(answer)
  })
  return left.map((it, k) => it.replace(/^\d+\. /, `${k + 1}. `)).join('\n')
}

// The matter's answers are let go once a run has them. With `brief`, only the ones it carries: an answer the run
// didn't receive stays in its box.
export async function clearAnswers($: EngineInterface, c: Card, brief?: string) {
  const sent = (key: string, value: string | undefined) => key.startsWith(`${c.path}#`) && (brief === undefined || (value ?? '').trim() === '' || brief.includes((value ?? '').trim()))
  for (const [key, value] of Object.entries(typed.answers)) if (sent(key, value)) delete typed.answers[key]
  await updateAnswers($, all => Object.fromEntries(Object.entries(all ?? {}).filter(([key, value]) => !sent(key, value))))
}

export type RunOpts = { skipSetup?: boolean; skipGate?: boolean; stage?: string; note?: string }

// A redo says which step it starts from; every other kind has one name.
export function runLabel(kind: string, card: Card, stage = ''): string {
  const from = kind === 'redo' ? card.progress.stages.find(s => s.id === stage)?.label : ''
  return from ? `Redoing ${from} and the steps after it` : runKind(kind).doing
}

export function blankRun(card: Card, kind: string, reply: string, now: string, opts: RunOpts = {}): Run {
  return {
    agentId: '', kind, matter: card.path, name: card.name, label: runLabel(kind, card, opts.stage), startedAt: now, endedAt: '', status: 'running',
    answer: '', reason: '', reply, step: '', stepLabel: '', lastSeen: progressSig(card), lastChangeAt: now, waitingOk: false,
    ...(opts.stage ? { stage: opts.stage } : {}), ...(opts.note?.trim() ? { note: opts.note.trim() } : {}),
  }
}

// ---------- the run lease (CONTRACTS §3) ----------

// Taking the lease before anything starts: the server refuses when Claude already works on the matter (from the
// chat, another window, an orchestrator started by hand), so a second agent never starts on the same matter. The
// brief comes back with it, filled in: the run's id, the redo's step, every saved answer, and the note for this run.
type Taken = { runId: string; prompt: string } | { refused: string }

async function takeLease($: EngineInterface, card: Card, kind: string, opts: RunOpts): Promise<Taken> {
  try {
    const res = (await call($, {
      op: 'start_run', matter_path: card.path, matter: card.path, kind,
      ...(kind === 'redo' && opts.stage ? { stage_id: opts.stage } : {}), ...(opts.note?.trim() ? { note: opts.note.trim() } : {}),
    })) as unknown as { run_id: string; prompt: string }
    return { runId: res.run_id, prompt: res.prompt }
  } catch (err) {
    return { refused: err instanceof Error ? err.message : String(err) }
  }
}

// Renewed on the app's tick while its agent lives (or its request waits in the chat box); released when it ends.
// A start that waits in the chat box is held for 10 minutes; unsent by then, it is taken back (so the matter is
// free again) and the page says so. The server lets go of a lease the app stops renewing within 3 minutes anyway,
// so quitting Claude mid-run frees the matter too.
export const START_WAIT_MS = 10 * 60000

export async function heartbeatRuns($: EngineInterface) {
  const now = nowMs()
  const live = Object.values(await readRuns($)).filter(x => (x.status === 'running' || x.status === 'starting') && x.runId)
  for (const r of live) {
    let lease: Lease | null | undefined
    try {
      lease = ((await call($, { op: 'heartbeat_run', matter_path: r.matter, matter: r.matter, run_id: r.runId })) as unknown as { lease?: Lease | null }).lease
    } catch {
      // the next tick tries again; a lease nobody renews for 30 minutes ends by itself
    }
    if (r.status !== 'starting') continue
    // The request was sent after all: the orchestrator renewed the app's run under its own name. Unless its agent
    // turned up (it would be running by now), the app can't follow it, so it hands the run over rather than hold it.
    const takenUp = Boolean(lease && lease.run_id === r.runId && lease.holder && lease.holder !== 'app')
    if (takenUp || now - Date.parse(r.startedAt) > START_WAIT_MS) await withdrawStart($, r)
  }
}

// The app gives up a start it never saw begin: unsent after the wait, or taken back with Cancel. The server takes the
// lease back only while the app still holds it; a run that took it up keeps the matter. A request still in the chat
// box is cleared from it, so it isn't sent later by mistake; where the box can't be cleared, the page says so.
export async function withdrawStart($: EngineInterface, r: Run, byYou = false): Promise<void> {
  let start = 'cancelled'
  if (r.runId) {
    try {
      start = ((await call($, { op: 'cancel_start', matter_path: r.matter, matter: r.matter, run_id: r.runId })) as unknown as { start: string }).start
    } catch (err) {
      // Cancel pressed and the server couldn't do it (the matter busy, say): said where the attorney is looking. The
      // start keeps waiting, and the 15-second tick tries again on its own.
      if (byYou) await setNote($, `The start wasn’t cancelled: ${err instanceof Error ? err.message : String(err)}`)
      return
    }
  }
  // Another look at the runs: the agent may have turned up while the server answered, and then it is being followed
  // (its orchestrator takes the run id up again), so nothing is said about a start that wasn't sent.
  const now = (await readRuns($))[r.matter]
  if (now && now.status === 'starting' && now.runId === r.runId) {
    await updateRuns($, cur => Object.fromEntries(Object.entries(cur ?? {}).filter(([path, x]) => !(path === r.matter && x.status === 'starting' && x.runId === r.runId))))
  } else if (now?.runId === r.runId) {
    await refresh($)
    return
  }
  if (start === 'taken_up') {
    // Claude is at work on it: the matter says so from the server's side.
    await refresh($)
    return
  }
  const still = start === 'cancelled' ? !(await clearChatBox($, r)) : false
  const here = (await readPayload($))?.matter?.path === r.matter
  const again = `Press ${runKind(r.kind).button} to try again.`
  if (byYou) await setNote($, still ? 'Cancelled. The request is still in your chat box: delete it there rather than send it.' : '')
  else if (still) await setNote($, `${here ? 'The start' : `The start for ${r.name}`} in your chat box wasn’t sent, so it was cancelled. It’s still in your chat box: delete it there rather than send it. ${again}`)
  else await setNote($, `${here ? 'The start' : `The start for ${r.name}`} in your chat box wasn’t sent. ${again}`)
  await refresh($)
}

// Clears the chat box when it still holds this run's request. True when it no longer holds it.
async function clearChatBox($: EngineInterface, r: Run): Promise<boolean> {
  let box = ''
  try {
    box = (await $.prompt.read()).text
  } catch {
    box = ''
  }
  const mine = (r.runId && box.includes(r.runId)) || (r.description && box.includes(r.description))
  if (!mine) return true
  try {
    return (await $.prompt.fill({ text: '', mode: 'replace' })).isFilled
  } catch {
    return false
  }
}

// An agent started from the chat box: matched to the start waiting for it by the run id its brief carries (the
// description the chat gave it may differ), else by the description the app asked for. It is then the app's run.
export async function adoptSpawn($: EngineInterface, prompt: string, description: string, agentId: string): Promise<boolean> {
  const waiting = Object.values(await readRuns($)).filter(r => r.status === 'starting')
  const r = waiting.find(x => x.runId && prompt.includes(x.runId)) ?? waiting.find(x => x.description && description.trim() === x.description)
  if (!r) return false
  await adopt($, r, agentId)
  return true
}

async function adopt($: EngineInterface, r: Run, agentId: string) {
  liveAgents.add(agentId)
  const now = await nowIso($)
  await updateRuns($, cur => ({ ...(cur ?? {}), [r.matter]: { ...r, agentId, status: 'running' as const, startedAt: now, lastChangeAt: now } }))
  await setNote($, '')
}

// A start that never began (the agent didn't start, the request couldn't go into the chat box): its lease goes back
// through cancel_start, so the timeline says Claude didn't start, not that it ran into a problem. A lease the app stops
// renewing ends by itself within minutes, so a failure here is let go.
async function giveBackStart($: EngineInterface, matter: string, runId: string) {
  if (!runId) return
  await call($, { op: 'cancel_start', matter_path: matter, matter, run_id: runId, why: 'not_started' }).catch(() => undefined)
}

// Lets go of the run's lease and answers the matter as the server now has it (the card release_run sends back).
export async function releaseLease($: EngineInterface, r: Pick<Run, 'matter' | 'runId'>, outcome: 'done' | 'stopped' | 'failed'): Promise<Card | null> {
  if (!r.runId) return null
  try {
    const res = await call($, { op: 'release_run', matter_path: r.matter, matter: r.matter, run_id: r.runId, outcome })
    return res.matter?.path === r.matter ? res.matter : null
  } catch {
    // a lease the app stops renewing ends by itself within minutes
    return null
  }
}

// One timer for the whole app, every 15 seconds: it finds runs that started or ended out of sight, keeps the app's
// own agents' leases alive, and refreshes what the screen shows. A hot reload drops it; the next draw or session start
// makes it again.
export function ensurePoll($: EngineInterface) {
  if (session.poll) return
  session.poll = $.clock.every(15000, async () => {
    try {
      await reconcileRuns($)
      await heartbeatRuns($)
    } finally {
      await refresh($)
    }
  })
}

// Words into the chat as the attorney's own: sent, when `send` asks for it and the chat takes them, else left in the
// chat box for the attorney's Enter. Says which, or null when the chat box couldn't take them either.
export async function toChat($: EngineInterface, text: string, send: boolean): Promise<'sent' | 'filled' | null> {
  if (send) {
    try {
      if (!(await $.prompt.submit({ text })).drop) return 'sent'
    } catch {
      // the chat box below is the way in
    }
  }
  try {
    return (await $.prompt.fill({ text, mode: 'replace' })).isFilled ? 'filled' : null
  } catch {
    return null
  }
}

// When the app can't start the agent itself (auto mode ties a start to something typed in the chat, and a press isn't
// that), the same request goes into the chat box for the attorney to send. It opens with the plain request; the brief
// below it is what makes the run correct.
export async function askInChat($: EngineInterface, card: Card, kind: string, prompt: string, reply: string, opts: RunOpts = {}, runId = '') {
  const label = runLabel(kind, card, opts.stage)
  const description = `${label}: ${card.name}`
  const text = `${runKind(kind).ask(card.name)}\n\n(For Claude) Start the ${AGENT} agent in the background, described as “${description}”, with this brief:\n\n${prompt}`
  if (!(await toChat($, text, false))) {
    await giveBackStart($, card.path, runId)
    await setNote($, `Claude couldn’t start the ${runKind(kind).noun} from here. In the chat box below, type: ${runKind(kind).ask(card.name).replace(/ with Senior Associate, in the background\./, '')}, then press Enter.`)
    return
  }
  const pending: Run = { ...blankRun(card, kind, reply, await nowIso($), opts), status: 'starting', description, ...(runId ? { runId } : {}) }
  await updateRuns($, all => ({ ...(all ?? {}), [card.path]: pending }))
  ensurePoll($)
  await setNote($, '')
}

// A step, run as the app's own background agent on the matter. The attorney's answers ride along when there are any.
export async function startRun($: EngineInterface, card: Card, kind: string, reply = '', opts: RunOpts = {}) {
  // Instructions typed but not saved go with the run all the same: saved first, so the brief names them.
  const unsaved = typed.instructions[card.path]
  if (unsaved !== undefined && unsaved.trim() !== (card.attorney_instructions ?? '').trim()) {
    const saved = await saveInstructions($, card, unsaved)
    if (!saved) return
    card = saved
  }
  if (kind === 'redo' && !card.progress.stages.some(s => s.id === opts.stage)) {
    await setNote($, 'That step isn’t on this matter anymore. Open Packet and choose the step again.')
    return
  }
  const existing = (await readRuns($))[card.path]
  if (existing?.status === 'running') {
    await setNote($, 'Claude is already working on this matter. This page updates as it goes.', 'wait')
    return
  }
  // Something a build needs (Ghostscript prints the forms) is found now, not ten minutes in.
  if (BUILDS.has(kind) && !opts.skipSetup && !session.setupPassed) {
    const s = await doctor($)
    if (s && requiredMissing(s).length) {
      await updateSetup($, cur => ({ ...(cur ?? s), pending: { matter: card.path, kind, reply, ...(opts.stage ? { stage: opts.stage } : {}), ...(opts.note ? { note: opts.note } : {}) } }))
      await updateOrigins($, o => ({ ...(o ?? {}), setup: { view: 'matter' as View, matter: card.path } }))
      await go($, 'setup')
      await setNote($, `Before Claude builds, ${plural(requiredMissing(s).length, 'thing needs', 'things need')} setting up on this Mac. Fix what’s marked ✗, then press Check again.`)
      return
    }
    if (s) session.setupPassed = true
  }
  // A build without Your details leaves the G-28 and the signature blank: say so first.
  if (kind === 'build' && !opts.skipGate && profileIsEmpty(await readPayload($))) {
    await updateGate($, () => ({ matter: card.path, kind, reply }))
    await setNote($, '')
    return
  }
  await updateGate($, () => null)
  await updateSetup($, s => (s ? { ...s, pending: null } : s))
  // Started from one of the matter's other screens (Documents, Redo): the matter page is where the run is followed.
  const here = await readView($)
  if (MATTER_VIEWS.includes(here) && here !== 'matter') await go($, 'matter')
  // Answers typed but not saved are kept in the matter first, as save would keep them.
  await keepTypedAnswers($, card)
  // The lease first: nothing starts while someone else works on the matter.
  const lease = await takeLease($, card, kind, opts)
  if ('refused' in lease) {
    await setNote($, lease.refused, 'wait')
    await refresh($)
    return
  }
  const { runId } = lease
  // Every answer the brief doesn't already carry goes with it: the server writes the saved ones in, and the app adds
  // the rest (typed and not saved, a report's questions).
  const answers = notInBrief(reply, lease.prompt)
  const prompt = answers ? `${lease.prompt}\n\nThe attorney's answers to the open questions:\n${answers}` : lease.prompt
  const label = runLabel(kind, card, opts.stage)
  const description = `${label}: ${card.name}`
  let res: Awaited<ReturnType<typeof $.agent.spawn>>
  try {
    res = await $.agent.spawn({ prompt, subagentType: AGENT, description })
  } catch {
    return askInChat($, card, kind, prompt, reply, opts, runId)
  }
  if (res.deny) return askInChat($, card, kind, prompt, reply, opts, runId)
  // Core stamps the id; when a hook answered the spawn without it, the agent list still has it.
  let agentId = res.agentId ?? ''
  if (!agentId) {
    try {
      const mine = (await $.agent.list()).filter(a => a.description === description && !ENDED.has(a.status))
      agentId = mine[mine.length - 1]?.id ?? ''
    } catch {
      agentId = ''
    }
  }
  if (!agentId) {
    await giveBackStart($, card.path, runId)
    await setNote($, `The ${runKind(kind).noun} didn’t start. Press ${runKind(kind).button} again.`)
    return
  }
  const s = stepOf(card)
  const run: Run = { ...blankRun(card, kind, reply, await nowIso($), opts), agentId, description, step: stepText(s), stepLabel: s?.label ?? '', runId }
  await updateRuns($, all => ({ ...(all ?? {}), [card.path]: run }))
  liveAgents.add(agentId)
  ensurePoll($)
  await clearAnswers($, card, prompt)
  typed.redo = ''
  await setNote($, '')
  $.ui.toast(`${label} in the background. You’ll get a notification when it’s done.`)
}

// Mark a run finished with the agent's report (from turn.complete) or the agent list's word, then say so.
export async function finishRun($: EngineInterface, agentId: string, status: 'done' | 'failed', answer: string, reason: string) {
  let finished: Run | null = null
  const ended = await nowIso($)
  // Seen at once when the attorney is on the matter's page; otherwise /matters opens it first.
  const [v, p] = await Promise.all([readView($), readPayload($)])
  await updateRuns($, all => {
    const next = { ...(all ?? {}) }
    for (const [path, r] of Object.entries(next)) {
      if (r.agentId === agentId && r.status === 'running') {
        const seen = MATTER_VIEWS.includes(v) && p?.matter?.path === path
        finished = { ...r, status, answer: answer || r.answer, reason, endedAt: ended, waitingOk: false, seen }
        next[path] = finished
      }
    }
    return next
  })
  liveAgents.delete(agentId)
  // The notification is said from the matter as the run left it: the card release_run answers with.
  const after = finished ? await releaseLease($, finished, status === 'done' ? 'done' : 'failed') : null
  await refresh($)
  if (finished) await announce($, finished, after)
}

// A notification where the attorney will see it, even with Claude in the background; a toast when there's none.
export async function announce($: EngineInterface, r: Run, after: Card | null = null) {
  let c: Card | null = after ?? (await readPayload($))?.matter ?? null
  if (!c || c.path !== r.matter) {
    try {
      c = (await call($, { op: 'state', matter_path: r.matter })).matter ?? null
    } catch {
      c = null
    }
  }
  const text = finishedText(r, c)
  try {
    const sent = await $.ui.notify(text, { title: 'Senior Associate' })
    if (!sent.isSent) $.ui.toast(text, { timeoutMs: 8000 })
  } catch {
    $.ui.toast(text, { timeoutMs: 8000 })
  }
}

export function finishedText(r: Run, c: Card | null): string {
  const name = r.name || c?.name || 'The matter'
  if (r.status === 'failed') {
    return `${name}: the ${runKind(r.kind).noun} stopped${STEP_KINDS.has(r.kind) && r.stepLabel ? ` at ${r.stepLabel}` : ''}. Open it to try again.`
  }
  if (r.kind === 'closeout') return `${name}: Claude’s working files are cleaned up.`
  if (!c) return `${name}: Claude has finished.`
  const needs = needsOf(c)
  const questions = needs.filter(n => n.who === 'attorney').length
  const phase = matterStatus(c, null, nowMs()).phase
  if (phase === 'needs_you' && questions) return `${name}: Claude needs your answer on ${plural(questions, 'question', 'questions')}.`
  if (phase === 'complete') return `${name} is ready to file.`
  const needed = neededBeforeFiling(c).total
  if (phase === 'draft') return needed ? `${name}: draft packet ready. ${plural(needed, 'item is', 'items are')} needed before filing.` : `${name}: draft packet ready.`
  if (phase === 'waiting_client') return `${name}: waiting on the client for ${plural(clientCount(c, needs), 'item', 'items')}.`
  if (phase === 'reviewed' || REVIEW_KINDS.has(r.kind)) {
    const k = missingCount(c)
    return k ? `${name}: document review done. ${plural(k, 'thing is', 'things are')} missing.` : `${name}: document review done. Nothing is missing.`
  }
  if (r.kind === 'stress_test') return `${name}: the officer’s review is done.`
  return `${name}: Claude has finished for now.`
}

// The agent list is the fallback when no turn.complete reached us (a reload in between), and how a request sent from
// the chat box is found once it starts.
export async function reconcileRuns($: EngineInterface) {
  const all = await readRuns($)
  const open = Object.values(all).filter(r => r.status === 'running' || r.status === 'starting')
  if (open.length === 0) return
  let agents: Awaited<ReturnType<typeof $.agent.list>>
  try {
    agents = await $.agent.list()
  } catch {
    return
  }
  const known = new Set(Object.values(all).map(r => r.agentId).filter(Boolean))
  for (const r of open) {
    if (r.status === 'starting') {
      // The request named the agent's description exactly; another matter whose name contains this one's isn't it.
      const wanted = r.description ?? `${r.label}: ${r.name}`
      const mine = agents.filter(a => !known.has(a.id) && !ENDED.has(a.status) && (a.type === AGENT || /senior.?associate/i.test(a.type)) && a.description.trim() === wanted)
      const a = mine[mine.length - 1]
      if (a) {
        known.add(a.id)
        await adopt($, r, a.id)
      }
      continue
    }
    const a = agents.find(x => x.id === r.agentId)
    if (!a) continue
    if (a.status === 'completed') await finishRun($, r.agentId, 'done', '', 'completed')
    else if (a.status === 'failed' || a.status === 'killed') await finishRun($, r.agentId, 'failed', '', a.status)
  }
}

// Whether an agent of ours waits for the attorney's OK on a tool, as the permission check says.
export async function markWaiting($: EngineInterface, agentId: string, waiting: boolean) {
  const all = await readRuns($)
  const hit = Object.entries(all).find(([, r]) => r.agentId === agentId && r.status === 'running')
  if (!hit || hit[1].waitingOk === waiting) return
  await updateRuns($, cur => ({ ...(cur ?? {}), [hit[0]]: { ...hit[1], waitingOk: waiting } }))
}

// Stop a run the attorney gave up on. TaskStop is the host's own way to stop a background agent.
export async function stopAgent($: EngineInterface, agentId: string): Promise<boolean> {
  try {
    const res = (await $.tool.call({ tool: 'TaskStop', task_id: agentId } as never)) as { isError?: boolean } | undefined
    return !res?.isError
  } catch {
    return false
  }
}

// Stop our agent on this matter. A stop the attorney chose, once Claude had changed something, is set aside at once,
// so the matter shows where it stands (paused at a step, with Continue building) rather than a red Stopped. One that
// changed nothing keeps Try again, which carries the same answers and instructions. Returns what changed, or null.
export async function stopRun($: EngineInterface, c: Card, run: Run, byYou: boolean): Promise<{ changed: boolean } | null> {
  const stopped = await stopAgent($, run.agentId)
  if (!stopped) {
    await setNote($, `Claude couldn’t stop the ${runKind(run.kind).noun} from here. Open the tasks list in Claude and stop it there.`)
    return null
  }
  liveAgents.delete(run.agentId)
  const ended = await nowIso($)
  const changed = run.lastChangeAt !== run.startedAt
  await updateRuns($, all => ({ ...(all ?? {}), [c.path]: { ...run, status: 'failed' as const, reason: byYou ? 'by_you' : 'killed', endedAt: ended, waitingOk: false, ...(byYou && changed ? { dismissed: true } : {}) } }))
  await releaseLease($, run, 'stopped')
  // The server's word on the matter now that the lease is gone: paused where it stopped, not Claude at work.
  await refresh($)
  return { changed }
}
