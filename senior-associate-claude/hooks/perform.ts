// What each press does.
import type { EngineInterface } from 'claude-code'
import type { BackTo, Card, Payload, Profile, View } from '../types'
import { PROFILE_FIELDS, REVIEW_KINDS, STEP_KINDS, asksAttorney, builtPast, carried, chosenCase, folderName, metaChanged, needsOf, profileIsEmpty, reportQuestions, requestTranslations, requiredMissing, retryKind, reviewOnly, shownName } from './matter'
import { clearAnswers, composeAnswers, saveAnswer, startRun, stopRun, toChat, withdrawStart } from './runs'
import { act, call, closePicker, doctor, load, ownMatters, refresh, setPayload } from './server'
import { EMPTY_DRAFT, MATTER_VIEWS, PANE, go, readConfirm, readDraft, readGate, readNote, readOrigins, readPayload, readPrefs, readRedoAt, readRuns, readSetup, readView, remember, session, setNote, typed, updateCaseMissing, updateConfirm, updateDocked, updateDraft, updateExpanded, updateFilter, updateGate, updateLaunching, updateOrigins, updateRedoAt, updateRuns, updateSetup, updateSort, updateView } from './state'
import { ASK_LABEL, brief, friendly, nowMs, plainText } from './words'
import { afterAdding, isBusy, matterStatus } from './status'

export async function createMatter($: EngineInterface, raw: string) {
  const entered = raw.trim()
  if (!entered) {
    await setNote($, 'Type the client’s name first, then press Enter or Create matter.')
    return
  }
  const [p, d] = await Promise.all([readPayload($), readDraft($)])
  const chosen = chosenCase(p, d)
  if (!chosen) {
    await updateCaseMissing($, () => true)
    if (d.typeId === 'other') await setNote($, 'Describe what is being filed, then press Create matter.')
    return
  }
  const folder = folderName(entered, chosen.short)
  const created = await load($, { op: 'create', name: folder, matter_type: chosen.matterType, filing_posture: d.posture || 'new filing packet', filing_method: d.method ?? 'paper', protected: Boolean(d.protect) })
  if (created) {
    $.ui.toast(`${created.matter ? shownName(created.matter) : folder} created. Add the client’s documents next.`)
    typed.name = ''
    typed.other = ''
    await updateDraft($, () => EMPTY_DRAFT)
    await updateCaseMissing($, () => false)
  }
}

// Open one of the three side screens, remembering where to come back to.
export async function goTo($: EngineInterface, target: 'profile' | 'setup' | 'help') {
  const [v, p] = await Promise.all([readView($), readPayload($)])
  if (v !== target) {
    const from: BackTo = { view: v === 'profile' || v === 'setup' || v === 'help' ? 'home' : v, matter: p?.matter?.path ?? '' }
    // Help → Setup → Your details still comes back the way it went.
    const chain = await readOrigins($)
    const origin = v === 'profile' || v === 'setup' || v === 'help' ? { view: v, matter: chain[v]?.matter ?? '' } : from
    await updateOrigins($, o => ({ ...(o ?? {}), [target]: origin }))
  }
  if (target === 'profile') typed.profile = {}
  await go($, target)
}

export async function goBack($: EngineInterface, from: 'profile' | 'setup' | 'help') {
  const [o, p, pr] = await Promise.all([readOrigins($), readPayload($), readPrefs($)])
  const origin = o[from]
  const fallback: View = !pr.onboarded && ownMatters(p).length === 0 ? 'welcome' : 'home'
  const target = origin?.view ?? fallback
  if (MATTER_VIEWS.includes(target) && origin?.matter) {
    if (p?.matter?.path === origin.matter) return go($, target)
    const loaded = await load($, { op: 'state', matter_path: origin.matter })
    if (loaded && target !== 'matter') await updateView($, () => target)
    return
  }
  return go($, target === 'new' ? 'new' : target)
}

// The Your details fields typed but not saved, by their names on screen.
export function unsavedProfile(p: Payload | null): string[] {
  const saved = p?.profile ?? {}
  return PROFILE_FIELDS.filter(f => typed.profile[f.key] !== undefined && (typed.profile[f.key] ?? '').trim() !== (saved[f.key] ?? '').trim()).map(f => f.label)
    .concat(typed.profile.discipline_order_details !== undefined && typed.profile.discipline_order_details.trim() !== (saved.discipline_order_details ?? '').trim() ? ['Explanation'] : [])
}

// Enter (or a field's save) keeps Your details open and marks that field "✓ Saved"; Save goes back to where the
// attorney came from. Either way the confirmation is drawn on the page, not left to a toast the panel may hold.
export async function saveProfile($: EngineInterface, leave: boolean, field = '') {
  const p = await readPayload($)
  const merged: Profile = { ...(p?.profile ?? {}), ...typed.profile }
  const saved = await load($, { op: 'save_profile', profile: merged, stay: true })
  if (!saved) return
  typed.profile = {}
  if (!leave) {
    session.savedField = field
    await setNote($, 'Saved. Every build from now on uses your details.', 'ok')
    return
  }
  const g = await readGate($)
  await goBack($, 'profile')
  await updateGate($, () => null)
  await setNote($, g && !profileIsEmpty(saved) ? 'Your details are saved. Press Build packet to start.' : 'Your details are saved. Every build from now on uses them.', 'ok')
}

export const COPY_FAILED = 'Couldn’t copy the client request. Select its text under Show the client request and copy it from there.'

// The matter's settings (CONTRACTS §6): how it is filed, protection, the client request's language.
export async function setMeta($: EngineInterface, c: Card, changes: Record<string, unknown>): Promise<boolean> {
  try {
    const res = await call($, { op: 'set_meta', matter_path: c.path, matter: c.path, ...changes })
    if ((await readPayload($))?.matter?.path === c.path) await setPayload($, res)
    return true
  } catch (err) {
    await setNote($, err instanceof Error ? err.message : String(err))
    return false
  }
}

// The federal circuits, as the attorney names them; the matter keeps each by its short code.
export const CIRCUITS: { id: string; label: string }[] = [
  ...['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh', 'Eighth', 'Ninth', 'Tenth', 'Eleventh'].map((label, i) => ({ id: `ca${i + 1}`, label })),
  { id: 'dc', label: 'D.C.' }, { id: 'federal', label: 'Federal' }, { id: 'none', label: 'None applies' },
]

// Where the case is decided (who decides it, the circuit, why): saved as each is chosen, and said on the page.
export async function saveJurisdiction($: EngineInterface, c: Card, changes: { forum?: string; circuit?: string; jurisdiction_basis?: string }) {
  if (await setMeta($, c, changes)) await setNote($, 'Saved. Claude uses it from its next step on.', 'ok')
}

// The client request's language: English always, and this one too from the next run that writes it.
export async function setLanguage($: EngineInterface, c: Card, language: string) {
  const lang = language.trim() || 'English'
  if (!(await setMeta($, c, { client_language: lang }))) return
  typed.language = ''
  await setNote($, lang === 'English'
    ? 'The client request is written in English only.'
    : `Claude also writes the client request in ${lang}, from the next document review or update on. It stays in English too, for you.`, 'ok')
}

// The client request goes on the clipboard as plain text, ready to paste into an email to the client.
// `language`: one of the languages it was also written in; left out, the English request.
export async function copyRequest($: EngineInterface, surface?: string, language = '') {
  const c = (await readPayload($))?.matter
  const text = (language ? requestTranslations(c).find(t => t.language === language)?.text : c?.client_request_text) ?? ''
  if (!text.trim()) {
    await setNote($, 'There’s no client request yet. Claude writes it when it finishes a build or a document review.')
    return
  }
  try {
    const plain = plainText(text)
    const res = await $.ui.copy(surface ? { text: plain, surface: surface as never } : { text: plain })
    if (res.isCopied) await setNote($, `Client request${language ? ` in ${language}` : ''} copied. Paste it into your email to the client.`, 'ok')
    else await setNote($, COPY_FAILED)
  } catch (err) {
    session.lastRaw = err instanceof Error ? err.message : String(err)
    await setNote($, COPY_FAILED)
  }
}

// The attorney memo as plain text, for an email or a note to the file.
export async function copyMemo($: EngineInterface, surface?: string) {
  const text = (await readPayload($))?.matter?.memo_text ?? ''
  if (!text.trim()) {
    await setNote($, 'There’s no memo yet. Claude writes it at the end of every build or document review.')
    return
  }
  try {
    const res = await $.ui.copy(surface ? { text: plainText(text), surface: surface as never } : { text: plainText(text) })
    if (res.isCopied) await setNote($, 'Attorney memo copied.', 'ok')
    else await setNote($, COPY_FAILED)
  } catch (err) {
    session.lastRaw = err instanceof Error ? err.message : String(err)
    await setNote($, COPY_FAILED)
  }
}

// A setup task goes to Claude in the chat, as if the attorney had typed it. Claude's setup skill does it there, asking
// before each command, so nobody opens Terminal. If the chat won't take it, the request waits in the chat box.
export async function askClaude($: EngineInterface, ask: string) {
  const went = await toChat($, `${ask}\n\n(Sent from Immigration Packet Builder when I pressed “${ASK_LABEL}”.)`, true)
  if (went === 'sent') {
    await setNote($, '')
    $.ui.toast('Claude is on it in the chat. It asks before each step: choose Allow.')
  } else if (went === 'filled') await setNote($, 'The request is in your chat box. Press Enter to send it to Claude.', 'wait', '')
  else await setNote($, `In the chat box below, type “${ask}” and press Enter.`, 'warn', '')
}

// ---------- asking Claude about a matter ----------

// The opening the matter-chat skill answers to. It names the matter, so Claude finds its folder and where it stands.
export const askOpening = (c: Card) => `Ask Immigration Packet Builder about ${c.name}`

// A question from the matter's ask box, or a suggestion pressed, goes to Claude in the chat as the attorney's own words.
// If the chat won't take it, it waits in the chat box for Enter.
export async function sendQuestion($: EngineInterface, c: Card, question: string) {
  const asked = question.trim()
  if (!asked) {
    await setNote($, 'Type your question first, then press Ask.')
    return
  }
  // Asked while an error shows, the question carries the error as the app got it, so Claude can see what went wrong.
  const n = await readNote($)
  const said = n.text && n.tone === 'warn' && session.lastRaw ? ` (the app said: “${session.lastRaw.slice(0, 300)}”)` : ''
  const text = `${askOpening(c)}${said}: ${asked}`
  const went = await toChat($, text, true)
  // Once the question has gone, or waits in the chat box, the ask box is drawn afresh and empty.
  if (went) {
    delete typed.ask[c.path]
    session.askRound++
  }
  if (went === 'sent') await setNote($, 'Claude is answering in the chat.', 'ok')
  else if (went === 'filled') await setNote($, 'Your question is in the chat box. Press Enter to send it to Claude.', 'wait')
  else {
    typed.ask[c.path] = question
    await setNote($, `In the chat box below, type: ${text}`)
  }
}

// "Ask Claude about this", beside an open item or a review note: the chat box gets the matter, the item and a first
// question, for the attorney to change or send. Nothing is sent for them.
export async function askAboutThis($: EngineInterface, c: Card, subject: string, question: string) {
  const text = `${askOpening(c)}, about “${brief(subject, 200)}”: ${question}`
  if (await toChat($, text, false)) await setNote($, 'Your question is in the chat box below. Change it if you like, then press Enter.', 'wait')
  else await setNote($, `In the chat box below, type your question about “${brief(subject, 80)}”.`)
}

// Back to the list, as it is now: the light list (with what's archived) follows the full load.
export async function goHome($: EngineInterface) {
  typed.name = ''
  typed.other = ''
  await updateDraft($, () => EMPTY_DRAFT)
  await updateFilter($, () => '')
  await updateCaseMissing($, () => false)
  const p = await load($, { op: 'state', auto_select: false })
  // The full state leaves archived matters out: the light list brings their rows for Archived, at the foot.
  if (p?.archived_count) await refresh($)
}

export async function openPane($: EngineInterface) {
  const opened = await $.ui.open({ id: PANE, title: 'Immigration Packet Builder', focus: true })
  if (!opened.isPlaced) await setNote($, 'The side panel couldn’t open here. Make the Claude window wider, then press Open as side panel again.')
  else await updateDocked($, k => (k ?? 0) + 1)
}

export async function toggle($: EngineInterface, key: string) {
  await updateExpanded($, list => ((list ?? []).includes(key) ? (list ?? []).filter(k => k !== key) : [...(list ?? []), key]))
}

export async function watch($: EngineInterface, agentId: string) {
  if (!agentId) return
  try {
    const shown = await $.ui.view({ agentId })
    if (shown.deny) await setNote($, 'Claude couldn’t show its work from here. Open the tasks list in Claude to watch it.')
  } catch {
    await setNote($, 'Claude couldn’t show its work from here. Open the tasks list in Claude to watch it.')
  }
}

// The presses that open one of the matter's finished files: what the server opens, and the toast that says so.
const OPENS: Record<string, [which: string, toast: string]> = {
  'open-packet': ['packet', 'Opening the packet.'],
  'open-paper-packet': ['paper_packet', 'Opening the paper part of the filing.'],
  'open-letter': ['cover_letter', 'Opening the cover letter.'],
  'open-memo': ['memo', 'Opening the attorney memo.'],
  'print-checklist': ['filing_checklist', 'Opening the filing checklist. Print it from there.'],
  'upload-files': ['upload_files', 'Opening the files to upload in Finder.'],
  'open-deliverables': ['deliverables', 'Opening your files in Finder.'],
  'open-earlier': ['earlier', 'Opening the earlier work in Finder.'],
}

// The presses that start Claude. One start at a time: the guard is taken at the press, before anything is awaited, so a
// second press (a double click, the other placement of the app) says so instead of starting a second agent. The
// matter page dims its start buttons while it is held.
const STARTS = new Set(['build', 'gate-build', 'review', 'review-again', 'continue', 'update', 'redo-start', 'stress', 'closeout-yes', 'retry-run', 'stop-retry', 'setup-continue'])

export async function perform($: EngineInterface, id: string): Promise<void> {
  if (STARTS.has(id)) {
    // One start in flight per matter, taken at the press, before anything is awaited.
    const matter = session.matter
    if (session.launching.has(matter)) {
      await setNote($, 'Claude is starting on this matter. This page switches over in a moment.', 'wait')
      return
    }
    session.launching.add(matter)
    await updateLaunching($, list => [...list.filter(m => m !== matter), matter])
    try {
      return await press($, id)
    } finally {
      session.launching.delete(matter)
      await updateLaunching($, list => list.filter(m => m !== matter))
    }
  }
  return press($, id)
}

async function press($: EngineInterface, id: string): Promise<void> {
  const p = await readPayload($)
  const c = p?.matter ?? null
  switch (id) {
    case 'start': // the welcome's button
    case 'new':
      typed.name = ''
      typed.other = ''
      await updateDraft($, () => EMPTY_DRAFT)
      await updateCaseMissing($, () => false)
      await remember($, { onboarded: true })
      return go($, 'new')
    case 'sample': // the welcome's Open the sample matter, and Help's Add the sample matter
    case 'add-sample': {
      const row = p?.matters.find(m => m.sample)
      if (row) await load($, { op: 'state', matter_path: row.path })
      else await load($, { op: 'add_sample' })
      return
    }
    case 'create':
      return createMatter($, typed.name)
    case 'profile':
      return goTo($, 'profile')
    case 'save-profile':
      return saveProfile($, true)
    case 'help':
      return goTo($, 'help')
    case 'setup':
      await goTo($, 'setup')
      await doctor($)
      return
    case 'setup-check': {
      const s = await doctor($)
      if (!s) return setNote($, 'This version can’t check the setup. Restart Claude and type /matters.')
      const missing = requiredMissing(s)
      if (missing.length) return setNote($, `Still missing: ${missing.map(m => m.label).join(', ')}. If you just installed it, quit Claude with ⌘Q, open it again, and press Check again.`)
      session.setupPassed = true
      await setNote($, '')
      $.ui.toast(s.pending ? 'Everything Claude needs is ready. Press Continue to build.' : 'Everything Claude needs is ready.')
      return
    }
    case 'setup-continue': {
      await remember($, { setupSeen: true })
      const pending = (await readSetup($))?.pending ?? null
      if (pending) {
        const card = c?.path === pending.matter ? c : (await load($, { op: 'state', matter_path: pending.matter }))?.matter ?? null
        await updateView($, () => 'matter')
        if (card) await startRun($, card, pending.kind, pending.reply, { skipSetup: true, stage: pending.stage, note: pending.note })
        return
      }
      return goBack($, 'setup')
    }
    case 'back-profile': {
      // Leaving with changes typed but not saved asks first, on the page, and says what would be lost.
      if (unsavedProfile(p).length && (await readConfirm($)) !== 'profile-back') {
        await updateConfirm($, () => 'profile-back')
        return
      }
      typed.profile = {}
      return goBack($, 'profile')
    }
    case 'profile-save-back':
      await updateConfirm($, () => '')
      return saveProfile($, true)
    case 'profile-discard':
      typed.profile = {}
      await updateConfirm($, () => '')
      return goBack($, 'profile')
    case 'back-setup':
      await remember($, { setupSeen: true })
      // Walking away from the check sets aside the build it held, so it never starts later unasked.
      await updateSetup($, cur => (cur ? { ...cur, pending: null } : cur))
      return goBack($, 'setup')
    case 'back-help':
      return goBack($, 'help')
    case 'memo':
    case 'items':
    case 'matter':
      if (c) await go($, id)
      return
    case 'request': {
      // Back from the client request goes wherever it was opened from.
      const from = await readView($)
      if (!c) return
      await updateOrigins($, o => ({ ...(o ?? {}), request: { view: MATTER_VIEWS.includes(from) && from !== 'request' ? from : 'matter', matter: c.path } }))
      return go($, 'request')
    }
    case 'back-request': {
      const back = (await readOrigins($)).request?.view ?? 'matter'
      return go($, MATTER_VIEWS.includes(back) ? back : 'matter')
    }
    case 'docs':
      if (c) await go($, 'documents')
      return
    case 'packet':
      if (c) await go($, 'packet')
      return
    case 'copy-request':
      return copyRequest($)
    case 'all':
      return goHome($)
    case 'retry':
      await setNote($, '')
      await load($, { op: 'state' })
      return
    case 'dock':
      return openPane($)
    case 'close-picker':
      return closePicker($)
    case 'lang-other':
    case 'sec-instructions':
    case 'sec-more':
    case 'sec-details':
    case 'more-types':
    case 'filed-group':
    case 'archived-group':
    case 'resolved-group':
      return toggle($, id)
  }
  if (id.startsWith('copy-request-lang:')) return copyRequest($, undefined, id.slice(18))
  if (id.startsWith('ask-row:')) {
    const row = p?.matters.find(m => m.path === id.slice(8))
    if (row?.ask) await askClaude($, row.ask)
    return
  }
  if (id.startsWith('open:')) {
    await load($, { op: 'state', matter_path: id.slice(5) })
    return
  }
  if (id.startsWith('sort:')) {
    const order = id.slice(5)
    await updateSort($, () => order)
    return
  }
  if (id.startsWith('type:')) {
    const typeId = id.slice(5)
    await updateDraft($, d => ({ ...d, typeId }))
    await updateCaseMissing($, () => false)
    return
  }
  if (id.startsWith('method:')) {
    const method = id.slice(7) === 'online' ? 'online' as const : 'paper' as const
    await updateDraft($, d => ({ ...d, method }))
    return
  }
  if (id === 'protect:toggle') {
    await updateDraft($, d => ({ ...d, protect: !d.protect }))
    return
  }
  if (id.startsWith('lang:')) {
    if (!c) return
    return setLanguage($, c, id.slice(5))
  }
  if (id.startsWith('circuit:')) {
    if (c) await saveJurisdiction($, c, { circuit: id.slice(8) })
    return
  }
  if (id.startsWith('posture:')) {
    const posture = id.slice(8)
    await updateDraft($, d => ({ ...d, posture }))
    return
  }
  if (id.startsWith('account:')) {
    // "I don't have a USCIS online account": saved on the spot; every question about the account is then not asked.
    const none = id.slice(8) === 'none'
    typed.profile = { ...typed.profile, has_uscis_online_account: none ? 'no' : 'yes', ...(none ? { uscis_online_account_number: '' } : {}) }
    return saveProfile($, false)
  }
  if (id.startsWith('discipline:')) {
    // Saved on the spot, so the page redraws with the choice (and the explanation field for "yes").
    const answer = id.slice(11)
    typed.profile = { ...typed.profile, subject_to_discipline_order: answer, ...(answer === 'no' ? { discipline_order_details: '' } : {}) }
    return saveProfile($, false)
  }
  if (id.startsWith('more:')) return toggle($, id)
  if (!c) return
  if (id.startsWith('rec:')) {
    // By the question's key, not its place: a refresh may have reordered the questions since the page was drawn.
    const need = needsOf(c).find(n => n.qkey === id.slice(4))
    if (need?.recommendation) return saveAnswer($, c, need.qkey, need.question, `Go with your recommendation: ${need.recommendation}`, 'Update the packet')
    // A decision on the open items list that Claude didn't also ask: its own recommendation.
    const item = c.open_items?.open.find(it => it.id === id.slice(4) && it.type === 'attorney_decision')
    if (!item?.recommendation) return
    return saveAnswer($, c, item.id, item.question || item.title, `Go with your recommendation: ${brief(item.recommendation, 160)}`, 'Update the packet')
  }
  if (id.startsWith('done:')) {
    const itemId = id.slice(5)
    const working = isBusy(matterStatus(c, (await readRuns($))[c.path], nowMs()))
    const res = await load($, { op: 'resolve_item', matter_path: c.path, id: itemId, note: 'Done', stay: true })
    if (res && !res.warning) await setNote($, `Marked done.${working ? ' Claude takes this into account when it finishes.' : ''} Changed your mind? Resolved, at the foot of this page, has Reopen.`, 'ok')
    return
  }
  if (id.startsWith('reopen:')) {
    const working = isBusy(matterStatus(c, (await readRuns($))[c.path], nowMs()))
    const res = await load($, { op: 'reopen_item', matter_path: c.path, id: id.slice(7), stay: true })
    if (res && !res.warning) await setNote($, working ? 'Back on the list. Claude takes this into account when it finishes.' : 'Back on the list. Claude takes it up again on the next update.', 'ok')
    return
  }
  if (id.startsWith('open-doc:')) {
    const rel = id.slice(9)
    await act($, { op: 'open_document', matter_path: c.path, path: rel }, `Opening ${rel.split('/').pop()}.`)
    return
  }
  if (id.startsWith('remove:')) {
    await updateConfirm($, () => id)
    return
  }
  if (id.startsWith('remove-yes:')) {
    await updateConfirm($, () => '')
    const res = await load($, { op: 'remove_document', matter_path: c.path, path: id.slice(11), stay: true })
    if (res?.removed && !res.warning) await setNote($, `Removed ${res.removed.name} from the matter. It’s kept with the matter’s files: Put back, under Removed, returns it.${builtPast(res.matter ?? c) || reviewOnly(res.matter ?? c) ? ' Claude leaves it out from the next review or update on.' : ''}`, 'ok')
    return
  }
  if (id.startsWith('restore:')) {
    const res = await load($, { op: 'restore_document', matter_path: c.path, kept: id.slice(8), stay: true })
    if (res?.restored && !res.warning) await setNote($, `${res.restored.name} is back in the matter.`, 'ok')
    return
  }
  if (id.startsWith('redo:')) {
    // The Redo screen first: what redoing this step means, and room to say what should change.
    const from = await readView($)
    typed.redo = ''
    await updateRedoAt($, () => ({ matter: c.path, stage: id.slice(5), from: MATTER_VIEWS.includes(from) && from !== 'redo' ? from : 'matter' }))
    return go($, 'redo')
  }
  if (id.startsWith('answer:') || id.startsWith('view:')) {
    // A question's own box on the Questions tab (its key is the item's id, CONTRACTS §5), or an open item there,
    // brought into view; a box gets the cursor too. Where the app isn't the side panel there is nothing of its own to
    // scroll: the tab opens at the top.
    const answer = id.startsWith('answer:')
    const target = answer ? `answer-${id.slice(7)}` : `item-${id.slice(5)}`
    await go($, 'items')
    await $.ui.scroll({ to: { key: target }, in: PANE, block: 'center' }).catch(() => undefined)
    if (answer) await $.ui.focus({ requestId: PANE, key: target }).catch(() => undefined)
    return
  }
  if (id.startsWith('recv:')) {
    // Added from Questions: the Overview is where the press that works them in is.
    await perform($, 'add-files')
    const n = await readNote($)
    if (n.tone === 'ok') {
      await go($, 'matter')
      await setNote($, n.text, 'ok')
    }
    return
  }
  if (id.startsWith('client-said:')) {
    // What the client told the attorney goes to Claude the way a change does, starting with the question it answers.
    const it = c.open_items?.open.find(x => x.id === id.slice(12))
    typed.redo = it ? `The client answered “${it.title}”: ` : ''
    typed.savedRedo = ''
    await updateRedoAt($, () => ({ matter: c.path, stage: '', from: 'items' as View }))
    return go($, 'redo')
  }
  if (id.startsWith('accept:')) {
    const working = isBusy(matterStatus(c, (await readRuns($))[c.path], nowMs()))
    const res = await load($, { op: 'accept_risk', matter_path: c.path, matter: c.path, id: id.slice(7), note: 'Risk accepted by the attorney', stay: true })
    if (res && !res.warning) await setNote($, `Accepted.${working ? ' Claude takes this into account when it finishes.' : ''} It’s under Resolved, at the foot of this page, if you change your mind.`, 'ok')
    return
  }
  const opens = OPENS[id]
  if (opens) {
    await act($, { op: 'open_output', matter_path: c.path, which: opens[0] }, opens[1])
    return
  }
  if (id.startsWith('open-form:')) {
    const name = id.slice(10)
    const ok = await act($, { op: 'open_output', matter_path: c.path, which: 'form', name }, `Opening ${name}.`)
    if (!ok) await act($, { op: 'open_output', matter_path: c.path, which: 'deliverables' }, 'Opening your files in Finder.')
    return
  }
  const run = (await readRuns($))[c.path]
  switch (id) {
    case 'add-files':
    case 'add-folder': {
      const res = await load($, { op: id === 'add-files' ? 'add_documents' : 'add_folder', matter_path: c.path })
      if (!res) return
      if (res.cancelled) {
        await setNote($, '')
        $.ui.toast(id === 'add-files' ? 'No files added.' : 'No folder added.')
        return
      }
      await remember($, { pickerSeen: true })
      // The server sums it up (added, already in the matter, not added and why): said as it is, with the press that
      // works them in. Said on the page, where it stays until the next screen.
      const n = res.added?.length ?? 0
      const after = n ? afterAdding(res.matter, run, nowMs()) : ''
      await setNote($, `${res.message ?? ''}${after ? ` ${after}` : ''}`, n ? 'ok' : 'warn')
      return
    }
    case 'open-folder':
      await act($, { op: 'open_folder', matter_path: c.path }, 'Opening the matter folder in Finder.')
      return
    case 'build': {
      // Answers to the document review's questions ride along with the build.
      const reply = await composeAnswers($, needsOf(c), [], c)
      return startRun($, c, 'build', reply)
    }
    case 'gate-build':
      return startRun($, c, 'build', (await readGate($))?.reply ?? '', { skipGate: true })
    case 'set-intake': {
      const d = await readDraft($)
      const chosen = chosenCase(p, d)
      if (!chosen) {
        await updateCaseMissing($, () => true)
        return
      }
      const saved = await load($, { op: 'set_intake', matter_path: c.path, matter_type: chosen.matterType, filing_posture: d.posture || 'new filing packet' })
      if (saved) {
        typed.other = ''
        await updateDraft($, () => EMPTY_DRAFT)
        await updateCaseMissing($, () => false)
        if (!saved.warning) await setNote($, 'Saved. Claude knows what is being filed now.', 'ok')
      }
      return
    }
    case 'gate-details':
      return goTo($, 'profile')
    case 'gate-cancel':
      await updateGate($, () => null)
      return
    case 'review': {
      const from = carried(run)
      return startRun($, c, 'review_docs', (await composeAnswers($, needsOf(c), [], c)) || from.reply, { note: from.note })
    }
    case 'review-again':
      // Before a build, a fresh review redoes the review alone; after one, it's a redo from the review onward.
      if (!reviewOnly(c)) return perform($, 'redo:docs_review')
      return startRun($, c, 'review_again', await composeAnswers($, needsOf(c), [], c))
    case 'change':
      typed.redo = ''
      await updateRedoAt($, () => ({ matter: c.path, stage: '', from: 'matter' as View }))
      return go($, 'redo')
    case 'redo-start': {
      const r = await readRedoAt($)
      const note = typed.redo.trim()
      const reply = await composeAnswers($, needsOf(c), [], c)
      const fresh = (c.documents.added_since_build ?? []).length + (c.documents.changed_since_build ?? []).length + (c.documents.removed_since_build ?? []).length
      if (!r || r.matter !== c.path) return go($, 'matter')
      if (r.stage === '' && !note && !reply && !fresh) {
        await setNote($, 'Type what Claude should change first. Or go back and add documents or answer a question, then press Update the packet.')
        return
      }
      await go($, 'matter')
      if (r.stage === '') return startRun($, c, 'update', reply, { note })
      if (r.stage === 'docs_review' && reviewOnly(c)) return startRun($, c, 'review_again', reply, { note })
      return startRun($, c, 'redo', reply, { stage: r.stage, note })
    }
    case 'redo-cancel': {
      const r = await readRedoAt($)
      typed.redo = ''
      return go($, r?.from && r.from !== 'redo' ? r.from : 'matter')
    }
    case 'steps':
      return go($, 'packet')
    case 'intake': {
      // The case chooser starts on what the matter is now.
      const now = p?.catalog.matter_types.find(t => t.matter_type.toLowerCase() === c.intake.matter_type.toLowerCase())
      typed.other = now ? '' : c.intake.matter_type
      await updateDraft($, () => ({ ...EMPTY_DRAFT, typeId: now ? now.id : c.intake.matter_type ? 'other' : '', posture: c.intake.filing_posture || 'new filing packet', other: now ? '' : c.intake.matter_type, method: c.meta.filing_method, protect: c.meta.protected }))
      await updateCaseMissing($, () => false)
      return go($, 'intake')
    }
    case 'intake-save': {
      const d = await readDraft($)
      const chosen = chosenCase(p, d)
      if (!chosen) {
        await updateCaseMissing($, () => true)
        return
      }
      const posture = d.posture || 'new filing packet'
      const asNow = p?.catalog.matter_types.find(t => t.id === chosen.matterType)?.matter_type ?? chosen.matterType
      const sameCase = asNow.toLowerCase() === c.intake.matter_type.toLowerCase() && posture === (c.intake.filing_posture || 'new filing packet')
      if (sameCase && !metaChanged(c, d)) {
        await setNote($, 'That’s what is being filed now. Choose a different case, posture or way of filing, or press Cancel.')
        return
      }
      // How it is filed and whether the client is protected are the matter's settings: they change without starting over.
      if (metaChanged(c, d)) {
        const saved = await setMeta($, c, { filing_method: d.method ?? 'paper', protected: Boolean(d.protect), ...(d.protect ? { protected_reason: 'attorney' } : {}) })
        if (!saved) return
      }
      if (sameCase) {
        typed.other = ''
        await updateDraft($, () => EMPTY_DRAFT)
        await go($, 'matter')
        await setNote($, `Saved. ${(d.method ?? 'paper') === 'online' ? 'Claude prepares it for filing online' : 'Claude prepares it for filing on paper'}${d.protect ? ', and treats the client as protected' : ''}, from its next step on.`, 'ok')
        return
      }
      const started = c.progress.stages.some(s => s.status !== 'pending') || Boolean(c.outputs.memo || c.open_items)
      const res = await load($, { op: 'change_intake', matter_path: c.path, matter_type: chosen.matterType, filing_posture: posture, stay: true })
      if (!res) return
      typed.other = ''
      typed.redo = ''
      await updateDraft($, () => EMPTY_DRAFT)
      // The earlier case's report and answers belong to the earlier case.
      if (run?.status !== 'running') await updateRuns($, all => Object.fromEntries(Object.entries(all ?? {}).filter(([path]) => path !== c.path)))
      await clearAnswers($, c)
      await go($, 'matter')
      if (!res.warning) {
        await setNote($, started
          ? 'Changed. The steps start over for the new case, and your documents are all still here. The earlier packet, memo and open items are kept in the matter folder, not deleted: Show the earlier work in Finder, at the foot of this page.'
          : 'Changed. Claude knows what is being filed now.', 'ok')
      } else await setNote($, friendly(res.warning))
      return
    }
    case 'intake-cancel':
      typed.other = ''
      await updateDraft($, () => EMPTY_DRAFT)
      await updateCaseMissing($, () => false)
      return go($, 'matter')
    case 'continue': {
      const from = carried(run)
      return startRun($, c, 'continue', (await composeAnswers($, needsOf(c), [], c)) || from.reply, { note: from.note })
    }
    case 'update': {
      const needs = needsOf(c)
      const questions = !c.open_items && run?.status === 'done' && run.answer && asksAttorney(run.answer) ? reportQuestions(run.answer) : []
      const reply = await composeAnswers($, needs, questions, c)
      const asking = needs.some(n => n.who === 'attorney') || questions.length > 0 || (!c.open_items && run?.status === 'done' && asksAttorney(run?.answer ?? ''))
      if (asking && !reply && !(c.documents.added_since_build ?? []).length && !(c.documents.changed_since_build ?? []).length && !(c.documents.removed_since_build ?? []).length && !(c.chat_changes ?? []).length) {
        await setNote($, 'Answer at least one question first, add what the client sent, or use Tell Claude what to change. Then press Update the packet.')
        return
      }
      return startRun($, c, 'update', reply)
    }
    case 'stress':
      return startRun($, c, 'stress_test')
    case 'closeout':
      await updateConfirm($, () => 'closeout')
      return
    case 'closeout-yes':
      await updateConfirm($, () => '')
      return startRun($, c, 'closeout')
    case 'retry-run':
      return startRun($, c, retryKind(run, c), run?.reply ?? '', { stage: run?.stage, note: run?.note })
    case 'dismiss-run':
      // Not now: the stop is set aside and the matter shows where it stands, with every way forward.
      if (run) await updateRuns($, all => ({ ...(all ?? {}), [c.path]: { ...run, dismissed: true } }))
      await setNote($, '')
      return
    case 'stop':
      await updateConfirm($, () => 'stop')
      return
    case 'not-working':
      await updateConfirm($, () => 'not-working')
      return
    case 'not-working-yes': {
      // The attorney says the run holding the matter (one this session didn't start) isn't working anymore: the server
      // lets its lease go, and a run that was still going stops at its next step.
      await updateConfirm($, () => '')
      const lease = c.status.lease
      if (!lease?.run_id) return
      const res = await load($, { op: 'abandon_run', matter_path: c.path, matter: c.path, run_id: lease.run_id, stay: true })
      if (res && !res.warning) await setNote($, 'The matter is free again. It shows where Claude left off.', 'ok')
      return
    }
    case 'confirm-no':
      await updateConfirm($, () => '')
      return
    case 'stop-yes': {
      await updateConfirm($, () => '')
      if (run?.status !== 'running' || !run.agentId) return
      const stopped = await stopRun($, c, run, true)
      if (!stopped) return
      await setNote($, !stopped.changed
        ? 'Stopped before Claude changed anything. Try again starts it again; Not now leaves the matter as it was.'
        : `Stopped. Everything Claude finished is saved.${STEP_KINDS.has(run.kind) ? ' Continue building picks up where it stopped.' : REVIEW_KINDS.has(run.kind) ? ' Finish the document review picks up where it stopped.' : ''}`, 'ok')
      return
    }
    case 'watch':
      return watch($, run?.agentId ?? '')
    case 'stop-retry': {
      if (run?.status === 'running' && run.agentId && !(await stopRun($, c, run, false))) return
      return startRun($, c, retryKind(run, c), run?.reply ?? '', { stage: run?.stage, note: run?.note })
    }
    case 'cancel-start':
      // The request is taken back: the lease it held goes (unless it was sent and Claude took it up meanwhile), and
      // the chat box lets go of it, so the matter is free for whoever starts next.
      if (run?.status === 'starting') return withdrawStart($, run, true)
      await updateRuns($, all => Object.fromEntries(Object.entries(all ?? {}).filter(([path]) => path !== c.path)))
      await setNote($, '')
      return
    case 'timeline':
      return go($, 'timeline')
    case 'archive':
    case 'unarchive': {
      const res = await load($, { op: id, matter_path: c.path, matter: c.path, stay: true })
      if (!res || res.warning) return
      if (id === 'archive') {
        await goHome($)
        await setNote($, `${shownName(c)} is archived. It’s under Archived, at the foot of the list; Unarchive there puts it back.`, 'ok')
      } else await setNote($, `${shownName(c)} is back on the main list.`, 'ok')
      return
    }
    case 'open-approved-packet':
      await act($, { op: 'open_output', matter_path: c.path, which: 'approved_packet' }, 'Opening the approved copies in Finder.')
      return
    case 'approve': {
      // From the Overview: the Packet tab is where the open points, the reason and the approval are.
      await go($, 'packet')
      await $.ui.scroll({ to: { key: 'sec-approval' }, in: PANE, block: 'start' }).catch(() => undefined)
      return
    }
    case 'approve-filing': {
      const key = `${c.path}#filing-risk`
      if ((c.filing_readiness?.risks ?? []).length && !(typed.answers[key] ?? '').trim()) {
        await setNote($, 'Say in a line why you’re filing with these points open, then press Approve. Your reason is kept with the approval.')
        return
      }
      if (await load($, { op: 'approve_filing', matter_path: c.path, digest: c.filing_readiness?.digest ?? '', risk_note: typed.answers[key] ?? '', stay: true })) {
        delete typed.answers[key]
        await setNote($, 'You approved this version for filing. The clean copies, without the DRAFT marking, are ready: Show the approved copies opens them. If the packet or the documents change, the new version needs approving again.', 'ok')
      }
      return
    }
    case 'mark-filed':
      if (await load($, { op: 'mark_filed', matter_path: c.path })) await setNote($, `${shownName(c)} is marked as filed. Undo, below, puts it back.`, 'ok')
      return
    case 'unmark-filed':
      if (await load($, { op: 'unmark_filed', matter_path: c.path })) await setNote($, `${shownName(c)} is no longer marked as filed.`, 'ok')
      return
    case 'check-again': {
      const s = await doctor($)
      const res = await load($, { op: 'state', matter_path: c.path })
      if (!res || !s) return
      const missing = requiredMissing(s)
      await setNote($, missing.length
        ? `Still missing on this Mac: ${missing.map(m => m.label).join(', ')}. If Claude just installed it, quit Claude with ⌘Q, open it again, and check again.`
        : 'Everything Claude needs is on this Mac now. Press Update the packet so Claude finishes what it couldn’t.', missing.length ? 'warn' : 'ok')
      return
    }
  }
}
