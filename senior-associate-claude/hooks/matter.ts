// Reading a matter's card: where the build stands, what Claude needs, and the words for each state.
import type { Card, Draft, MatterFile, MatterRow, Payload, Profile, ReviewNote, Run, Setup } from '../types'
import { typed } from './state'
import { ERROR, MUTED, STAGE_FILL, WARN } from './theme'
import { andList, brief, capitalizeWords, duration, plural } from './words'

export const MANY = 6 // matters before a search field appears
export const FEW = 3 // matters at or under which "Pick up where you left off" is left out
export const COMMON_TYPES = 6 // case types shown before "More case types"
export const FOLDER_FIRST = 8 // files shown per folder before "Show all"
export const STALL_MS = 20 * 60000 // no change for this long: say so

export const AGENT = 'senior-associate:senior-associate' // the orchestrator the plugin ships in agents/

// Each kind of run the app starts: what it is doing ("Building the packet"), what it is ("the build stopped"), its name
// once done ("Packet build"), the button that starts it ("press … again"), and the plain request a person would type,
// the first line of what goes in the chat box.
type RunKind = { doing: string; noun: string; done: string; button: string; ask: (name: string) => string }
const KINDS: Record<string, RunKind> = {
  build: { doing: 'Building the packet', noun: 'build', done: 'Packet build', button: 'Build packet', ask: n => `Build the packet for ${n} with Immigration Packet Builder, in the background.` },
  update: { doing: 'Updating the packet', noun: 'update', done: 'Packet update', button: 'Update the packet', ask: n => `Update the packet for ${n} with Immigration Packet Builder, in the background.` },
  continue: { doing: 'Building the packet', noun: 'build', done: 'Packet build', button: 'Continue building', ask: n => `Continue building the packet for ${n} with Immigration Packet Builder, in the background.` },
  review_docs: { doing: 'Reviewing the documents', noun: 'document review', done: 'Document review', button: 'Review documents first', ask: n => `Review ${n}’s documents with Immigration Packet Builder, in the background. Don’t build the packet yet.` },
  review_again: { doing: 'Reviewing the documents again', noun: 'document review', done: 'Document review', button: 'Review the documents again', ask: n => `Review ${n}’s documents again with Immigration Packet Builder, in the background. Don’t build the packet.` },
  redo: { doing: 'Redoing steps', noun: 'redo', done: 'Redo', button: 'Redo from here', ask: n => `Redo part of the packet for ${n} with Immigration Packet Builder, in the background.` },
  stress_test: { doing: 'Running the officer’s review', noun: 'officer’s review', done: 'Officer’s review', button: 'Re-check as a USCIS officer would', ask: n => `Give the ${n} packet the officer’s review with Immigration Packet Builder, in the background.` },
  recheck: { doing: 'Checking the law again', noun: 'check of the law', done: 'Check of the law', button: 'Check the law again', ask: n => `Check the law the ${n} cover letter cites again with Immigration Packet Builder, in the background.` },
  closeout: { doing: 'Cleaning up working files', noun: 'clean-up', done: 'Clean-up', button: 'Clean up working files', ask: n => `Clean up Claude’s working files for ${n} with Immigration Packet Builder, in the background.` },
}
export const runKind = (kind: string): RunKind => KINDS[kind] ?? KINDS.build!
// The steps that review another's work; redone, they review afresh and in full.
// The review steps a redo reads afresh. A matter not yet migrated still lists the two reviews the final review replaced.
export const REVIEW_STEPS = new Set(['docs_review', 'forms_reviewer', 'cover_letter_reviewer', 'final_review', 'packet_review', 'uscis_adjudicator'])
export const STEP_KINDS = new Set(['build', 'update', 'continue', 'redo'])
export const REVIEW_KINDS = new Set(['review_docs', 'review_again'])

// Rough minutes per step, for how long redoing from a step takes (server/sa_server/catalog.py's STAGE_MINUTES).
export const STAGE_MINUTES: Record<string, number> = {
  docs_review: 6, forms_preparer: 15, forms_reviewer: 10, cover_letter_writer_draft: 10, cover_letter_researcher: 10,
  cover_letter_writer_integrate: 8, cover_letter_reviewer: 8, packet_assembly: 5, final_review: 15, attorney_handoff: 3,
}

export type Step = { index: number; total: number; label: string }

// Where the build stands: step 4 of 10, Cover letter. The server counts finished steps plus one, and names every step
// running now (steps can run side by side).
export function stepOf(c: Card): Step | null {
  const st = c.status
  if (!st.step_total || !st.step_index || st.step_index > st.step_total) return null // every step done
  const names = st.running.map(r => r.label).filter(Boolean)
  return { index: st.step_index, total: st.step_total, label: names.length ? andList(names) : c.progress.current?.label ?? '' }
}

export const stepText = (s: Step | null) => (s ? `step ${s.index} of ${s.total}${s.label ? `: ${s.label}` : ''}` : '')

export function minutesWords(m: number): string {
  if (m <= 2) return 'almost done'
  return `about ${duration(m * 60000)} left`
}

// What the matter's progress looks like, to notice when it last moved.
export function progressSig(c: Card): string {
  const prg = c.progress
  return `${prg.updated_at ?? c.updated_at ?? ''}|${prg.done}|${prg.current?.id ?? ''}:${prg.current?.status ?? ''}`
}


// The name a matter goes by on screen. A protected matter's folder has a neutral name; the app shows the name the
// attorney gave it. What goes to Claude (a question, a run's description) still names the folder.
export const shownName = (m: { name: string; title?: string }): string => m.title || m.name

export const replyKey = (c: Card) => `${c.path}#reply` // one answer box for every question, when a report's questions couldn't be told apart

export type Need = {
  i: number
  /** Where the app keeps this question's answer: the matter's path and the question's key. */
  key: string
  /** The question's key, as the server gives it (CONTRACTS §5). */
  qkey: string
  /** Its open item is needed before filing. */
  blocks: boolean
  id: string
  who: 'attorney' | 'client' | 'system'
  question: string
  detail: string
  recommendation: string
  stage: string
  fix: string
  ask: string
}

// The server's needs, as the screens read them: who acts, the question, and the step apart from it.
export function needsOf(c: Card): Need[] {
  return c.needs_you.map((item, i) => ({
    i,
    key: `${c.path}#${item.key}`,
    qkey: item.key,
    blocks: Boolean(item.blocks_filing),
    id: item.id,
    who: item.who,
    question: (item.question || item.text).trim(),
    detail: item.detail ? brief(item.detail) : '',
    recommendation: item.recommendation ? brief(item.recommendation, 160) : '',
    stage: item.stage,
    fix: item.fix ?? '',
    ask: item.ask ?? '',
  }))
}

// The last numbered list in a report: the questions it ends with, one per answer box.
export function reportQuestions(answer: string): string[] {
  const lines = answer.replace(/\r\n/g, '\n').split('\n')
  const items: string[] = []
  let tail: string[] = []
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i] ?? ''
    const numbered = line.match(/^\s*\d+[.)]\s+(.+)$/)
    if (numbered?.[1]) {
      items.unshift([numbered[1].trim(), ...tail].join(' '))
      tail = []
    } else if (!line.trim()) {
      if (items.length && tail.length) break
    } else if (/^\s{2,}\S/.test(line)) {
      tail.unshift(line.trim())
    } else if (items.length) {
      break
    } else {
      return []
    }
  }
  return items.filter(q => q.length > 3)
}

// Does the report end by asking the attorney something?
export function asksAttorney(answer: string): boolean {
  const tail = answer.trim().split(/\n\s*\n/).pop() ?? ''
  return /\?\s*$/.test(tail) || /\b(your decision|please (confirm|decide|advise)|needs? (the )?attorney|attorney('s)? (input|decision|confirmation))\b/i.test(answer)
}

export const BUILDS = new Set(['build', 'update', 'continue', 'redo']) // the runs that print forms, so setup must be done first

export const ENDED = new Set(['completed', 'failed', 'killed'])

// ---------- reading a matter ----------

export const STAGE_WORD: Record<string, string> = { passed: 'done', skipped: 'skipped', in_progress: 'in progress', blocked: 'on hold', failed: 'stopped', pending: 'not started' }

// A review note's colour, by its severity word.
const NOTE_TONE: Record<string, string> = { important: ERROR, 'worth fixing': WARN, 'check by hand': WARN }
export const noteTone = (n: ReviewNote) => NOTE_TONE[n.severity_word] ?? MUTED

// "Important · RFE likely · found in Final review · to fix: the client"
export function noteLine(n: ReviewNote): string {
  const first = n.severity_word.charAt(0).toUpperCase() + n.severity_word.slice(1)
  return [first, n.outcome_word, n.stage_label ? `found in ${n.stage_label}` : '', n.owner_word ? `to fix: ${n.owner_word}` : ''].filter(Boolean).join(' · ')
}

// The Questions tab's groups, by who acts. The open items' types, in the order an attorney works through them.
export const ITEM_GROUPS: { title: string; types: string[] }[] = [
  { title: 'Your decisions', types: ['attorney_decision'] },
  { title: 'From the client', types: ['client_document', 'client_question'] },
  { title: 'For you to do', types: ['attorney_action'] },
  { title: 'Risks to weigh', types: ['risk'] },
]
export const CLIENT_TYPES = ['client_document', 'client_question']

export const PROFILE_FIELDS: { key: keyof Profile; label: string; placeholder: string }[] = [
  { key: 'attorney_name', label: 'Attorney name', placeholder: 'e.g. Ana Ruiz' },
  { key: 'firm_name', label: 'Firm', placeholder: 'e.g. Example Immigration Law PLLC' },
  { key: 'mailing_address', label: 'Mailing address', placeholder: 'Street, city, state, ZIP' },
  { key: 'phone', label: 'Phone', placeholder: 'e.g. (555) 555-0100' },
  { key: 'email', label: 'Email', placeholder: 'e.g. ana@example.com' },
  { key: 'bar_number', label: 'Bar number', placeholder: 'e.g. 24012345' },
  { key: 'licensing_authority', label: 'Licensing authority', placeholder: 'e.g. Supreme Court of Texas' },
  { key: 'uscis_online_account_number', label: 'USCIS online account number', placeholder: 'Optional' },
]

export function profileIsEmpty(p: Payload | null): boolean {
  return !p?.profile || !p.profile.attorney_name
}

export function clientCount(c: Card, needs: Need[]): number {
  const ledger = c.open_items
  const fromLedger = ledger ? CLIENT_TYPES.reduce((sum, t) => sum + (ledger.counts[t] ?? 0), 0) : 0
  return Math.max(fromLedger, needs.filter(n => n.who === 'client').length)
}

// What the document review found missing: the client's items on the open items list.
export function missingCount(c: Card): number {
  const ledger = c.open_items
  return ledger ? CLIENT_TYPES.reduce((sum, t) => sum + (ledger.counts[t] ?? 0), 0) : 0
}

// Only the document review has run: a fresh review redoes it alone, and new documents go into that.
export function reviewOnly(c: Card): boolean {
  const st = c.progress.stages
  return st.some(s => s.id === 'docs_review' && s.status === 'passed') && st.every(s => s.id === 'docs_review' || s.status === 'pending')
}

// Something after the document review has run, so changes go in through Update the packet or a redo.
export function builtPast(c: Card): boolean {
  return c.progress.stages.some(s => s.id !== 'docs_review' && s.status === 'passed')
}

// Started past the review but no step after it has finished: Continue building is the way on.
export function partway(c: Card): boolean {
  return !builtPast(c) && c.progress.stages.some(s => s.id !== 'docs_review' && s.status !== 'pending')
}

// What each step does, in a line, for the Packet screen and the Redo screen.
export const STAGE_ABOUT: Record<string, string> = {
  docs_review: 'Reads every document, lists what’s present, what’s missing, and what would strengthen the case.',
  forms_preparer: 'Fills the current USCIS forms from the documents, leaving blank anything the record doesn’t support.',
  forms_reviewer: 'A second, independent check of every form answer against the documents.',
  cover_letter_writer_draft: 'Drafts the cover letter: the relief, the legal basis, and the exhibit that proves each element.',
  cover_letter_researcher: 'Finds and checks the case law and policy the letter relies on.',
  cover_letter_writer_integrate: 'Works the research into the letter.',
  cover_letter_reviewer: 'An independent check of the letter’s facts, law, exhibits and format.',
  packet_assembly: 'Puts the letter, forms and exhibits into one ordered PDF, with placeholders for what’s still to come.',
  final_review: 'Pre-filing checks and the officer’s review: the strongest reason USCIS might question or deny it, and the cure.',
  attorney_handoff: 'Writes your memo, the client request, and the list of what’s left.',
}

// About how long redoing from a step takes: that step and every one after it.
export function minutesFrom(c: Card, stageId: string): number | null {
  const st = c.progress.stages
  const at = st.findIndex(s => s.id === stageId)
  if (at < 0) return null
  const rest = st.slice(at)
  if (rest.some(s => STAGE_MINUTES[s.id] === undefined)) return null
  return rest.reduce((sum, s) => sum + (STAGE_MINUTES[s.id] ?? 0), 0)
}

// What changed among the client's documents since Claude last took the matter in (finding 8): files that arrived,
// files replaced with new contents, files taken out. Each is offered the same way. In a protected matter no file
// name is said, as the server's briefs say none: only how many.
export type DocChanges = { added: string[]; changed: string[]; removed: string[]; masked: boolean }
export function docChanges(c: Card): DocChanges {
  return {
    added: c.documents.added_since_build ?? [],
    changed: c.documents.changed_since_build ?? [],
    removed: c.documents.removed_since_build ?? [],
    masked: c.meta.protected,
  }
}
const fileName = (p: string) => p.split('/').pop() ?? p
const one = (d: DocChanges, list: string[]) => (list.length === 1 && !d.masked ? fileName(list[0]!) : '')
// "2 new files arrived" · "Passport.pdf changed" / "2 files changed" · "you took out Passport.pdf" / "you took out 2 files"
export function addedWords(d: DocChanges): string {
  return d.added.length ? `${plural(d.added.length, 'new file', 'new files')} arrived` : ''
}
export function changedWords(d: DocChanges): string {
  return one(d, d.changed) ? `${one(d, d.changed)} changed` : d.changed.length ? `${plural(d.changed.length, 'file', 'files')} changed` : ''
}
export function removedWords(d: DocChanges): string {
  return one(d, d.removed) ? `you took out ${one(d, d.removed)}` : d.removed.length ? `you took out ${plural(d.removed.length, 'file', 'files')}` : ''
}
// "the 2 new files and the new version of Passport.pdf": what a run works in.
export function worksIn(d: DocChanges): string {
  return andList([
    d.added.length ? `the ${plural(d.added.length, 'new file', 'new files')}` : '',
    one(d, d.changed) ? `the new version of ${one(d, d.changed)}` : d.changed.length === 1 ? 'the new version of 1 file' : d.changed.length ? `the new versions of ${d.changed.length} files` : '',
  ].filter(Boolean))
}
// The card's headline about them, since the build or the document review. One kind alone is said its own way;
// several are said together in one sentence. `inChat` is the chat changes' words, when there are any.
export function changesLine(d: DocChanges, since: string, inChat = ''): string {
  const parts = [addedWords(d), changedWords(d), removedWords(d), inChat].filter(Boolean)
  if (!parts.length) return ''
  const review = since === 'Claude reviewed the documents'
  if (parts.length === 1 && d.added.length) return review ? `${parts[0]} since ${since}.` : `${parts[0]} since ${since}. Update the packet to work ${d.added.length === 1 ? 'it' : 'them'} in and re-check it.`
  if (parts.length === 1 && d.changed.length) {
    const head = `${parts[0]!.charAt(0).toUpperCase()}${parts[0]!.slice(1)} since ${since}.`
    return review ? head : `${head} Update the packet to work in the new ${d.changed.length === 1 ? 'version' : 'versions'}.`
  }
  const then = d.added.length || d.changed.length || d.removed.length ? 'Update the packet to bring it up to date and re-check it.' : 'Update the packet to have the reviews check it.'
  return `Since ${since}, ${andList(parts)}.${review ? '' : ` ${then}`}`
}

// What is needed before filing, by who owes it, as the server counts it (CONTRACTS §4). The total is always the sum of
// its parts, so the sentence never says "3 things" and then lists two.
export type Needed = { total: number; client: number; you: number; risks: number }
export function neededBeforeFiling(c: Pick<Card, 'counts'>): Needed {
  const { client, you, risks } = c.counts.blocking
  return { total: client + you + risks, client, you, risks }
}
// "1 from the client, 1 for you and 1 risk to weigh"
export function neededParts(n: Needed): string {
  return andList([
    n.client ? `${n.client} from the client` : '',
    n.you ? `${n.you} for you` : '',
    n.risks ? plural(n.risks, 'risk to weigh', 'risks to weigh') : '',
  ].filter(Boolean))
}

// "3 from the client · 1 decision · 2 for you to do", for the matter's details.
export function itemsLine(counts: Record<string, number>): string {
  const n = (types: string[]) => types.reduce((sum, t) => sum + (counts[t] ?? 0), 0)
  return [
    n(CLIENT_TYPES) ? `${n(CLIENT_TYPES)} from the client` : '',
    n(['attorney_decision']) ? plural(n(['attorney_decision']), 'decision', 'decisions') : '',
    n(['attorney_action']) ? `${n(['attorney_action'])} for you to do` : '',
    n(['risk']) ? plural(n(['risk']), 'risk', 'risks') : '',
  ].filter(Boolean).join(' · ')
}

// The step track, drawn as graphics: one rounded segment per step. A step not started is the app's text colour, faint;
// a done one is that colour in full (currentColor, which the desktop sets to the app's text colour).
export function trackSvg(stages: { status: string }[]): string {
  const n = Math.max(1, stages.length)
  const width = 1000
  const gap = 10
  const seg = (width - gap * (n - 1)) / n
  const rects = stages
    .map((s, i) => `<rect x="${(i * (seg + gap)).toFixed(1)}" y="0" width="${seg.toFixed(1)}" height="14" rx="7" fill="${STAGE_FILL[s.status] ?? 'currentColor'}"${STAGE_FILL[s.status] ? '' : ' fill-opacity="0.16"'}/>`)
    .join('')
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="14" viewBox="0 0 ${width} 14" role="img" aria-label="build progress">${rects}</svg>`
}

// Files grouped by the folder they sit in, the matter folder itself first, each with its full count.
export function groupFiles(files: MatterFile[], folders?: { path: string; count: number }[]): { folder: string; files: MatterFile[]; count: number }[] {
  const groups = new Map<string, MatterFile[]>()
  for (const f of files) {
    const slash = f.path.lastIndexOf('/')
    const folder = slash === -1 ? '' : f.path.slice(0, slash)
    const list = groups.get(folder)
    if (list) list.push(f)
    else groups.set(folder, [f])
  }
  const totals = new Map((folders ?? []).map(f => [f.path.replace(/^\.\/?|\/$/g, ''), f.count]))
  return [...groups.entries()]
    .sort((a, b) => (a[0] === '' ? -1 : b[0] === '' ? 1 : a[0].localeCompare(b[0])))
    .map(([folder, list]) => ({ folder, files: list, count: Math.max(list.length, totals.get(folder) ?? 0) }))
}

export const requiredMissing = (s: Setup | null) => (s ? s.checks.filter(ch => ch.required && !ch.ok) : [])

// The case chosen on the New matter screen: a catalog entry, or the attorney's own words for anything else.
// The short goes into the folder name, which shows in Finder, so a protected case never falls back to its label.
export function chosenCase(p: Payload | null, d: Draft): { matterType: string; short: string } | null {
  if (d.typeId === 'other') {
    const words = typed.other.trim() || d.other.trim()
    return words ? { matterType: words, short: '' } : null
  }
  const t = p?.catalog.matter_types.find(m => m.id === d.typeId)
  return t ? { matterType: t.id, short: t.short ?? (t.protected ? '' : t.label) } : null
}

// The choices on New matter and Change what is being filed that are the matter's settings, not its case.
export function metaChanged(c: Pick<Card, 'meta'>, d: Draft): boolean {
  return (d.method ?? 'paper') !== c.meta.filing_method || Boolean(d.protect) !== c.meta.protected
}

// The client request in each language Claude wrote it in besides English (CONTRACTS §6: "Client Request (<Language>).md").
export function requestTranslations(c: Card | null | undefined): { language: string; text: string }[] {
  return Object.entries(c?.client_request_texts ?? {}).filter(([language, text]) => language !== 'English' && text.trim()).map(([language, text]) => ({ language, text }))
}

export function folderName(name: string, short: string): string {
  const n = capitalizeWords(name.trim())
  return short ? `${n} ${short}` : n
}

// The name the server gives a matter whose folder name is taken: "Garcia I-130 I-485 (2)".
export function freeName(p: Payload | null, name: string): { taken: MatterRow | null; next: string } {
  const rows = p?.matters ?? []
  const lower = (s: string) => s.toLowerCase()
  const taken = rows.find(m => lower(shownName(m)) === lower(name)) ?? null
  if (!taken) return { taken: null, next: name }
  let k = 2
  while (rows.some(m => lower(shownName(m)) === lower(`${name} (${k})`))) k++
  return { taken, next: `${name} (${k})` }
}

// The first question to ask about an open item, by what kind of item it is.
export const ASK_ITEM: Record<string, string> = {
  client_document: 'Why is this needed, and what could stand in for it if the client can’t get it?',
  client_question: 'Why do we need this, and how should I ask the client?',
  attorney_decision: 'Help me decide. What are the options, and the risk of each?',
  attorney_action: 'What exactly do I need to do here?',
  risk: 'How serious is this, and how do we answer it?',
}
export const ASK_NOTE = 'Is this right, and how should we fix it?'

// Up to three questions worth asking about the matter now, from where it stands: what to file, whether the client
// qualifies, the officer's strongest objection, a decision waiting on the attorney.
export function suggestedQuestions(c: Card): string[] {
  const out: string[] = []
  const add = (q: string) => { if (out.length < 3 && !out.includes(q)) out.push(q) }
  if (!c.documents.count) return out
  if (c.needs_intake) {
    add('Based on the documents, what should we file for this client?')
    return out
  }
  const built = builtPast(c)
  const merits = c.review_notes.find(n => /likely$/.test(n.outcome_word))
  if (merits) add(`How do we answer this: “${brief(merits.title, 120)}”`)
  const decision = (c.open_items?.open ?? []).find(it => it.type === 'attorney_decision' && it.question)
  if (decision?.question) add(`Help me decide: ${decision.question}`)
  if (!built) {
    add('Does the client qualify, on the documents we have?')
    if (missingCount(c)) add('What could stand in for the documents still missing?')
    add('What would an officer question first in this case?')
  } else {
    add('What would an officer question first in this packet?')
    if (c.outputs.cover_letter || c.outputs.packet) add('What’s the weakest point in the cover letter, and how do we shore it up?')
  }
  return out
}

// After a failed run: the same kind again, carrying the same answers. A build picks up where it stopped.
export function retryKind(r: Run | undefined, c: Card): string {
  const kind = r?.kind ?? 'continue'
  if (kind === 'build' && c.progress.done > 0) return 'continue'
  // A redo that got as far as resetting its step only has to carry on from there.
  if (kind === 'redo' && c.progress.stages.find(s => s.id === r?.stage)?.status !== 'passed') return 'continue'
  return kind
}

// The answers and instructions a stopped run carried, so going on from the stop doesn't lose what the attorney typed.
export function carried(run: Run | undefined): { reply: string; note: string } {
  return run?.status === 'failed' ? { reply: run.reply, note: run.note ?? '' } : { reply: '', note: '' }
}
