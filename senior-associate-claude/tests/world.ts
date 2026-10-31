// The world the app's tests stand it in: a stand-in for the server (its payloads as tests/golden.ts records the real
// server's: the status, counts, needs and review notes in words, the run lease, saved answers and settings), the
// background agent, the store, and the helpers that press the screen's main actions.
import type { AgentStatus, On } from 'claude-code'
import { mock } from 'claude-code/testing'


export const PLUGIN = 'senior-associate'
export const ROOT = '/matters'

export const CATALOG = {
  matter_types: [
    { id: 'i130_i485', label: 'I-130 / I-485 immediate relative', matter_type: 'I-130/I-485 immediate relative packet', short: 'I-130 I-485', hint: 'Petition and adjustment filed together' },
    { id: 'n400', label: 'N-400 naturalization', matter_type: 'N-400 naturalization packet', short: 'N-400', hint: 'Application for citizenship' },
    // The two VAWA cases as server/sa_server/catalog.py lists them: a short of form numbers only, and the protected flag.
    { id: 'i360_vawa', label: 'I-360 VAWA self-petition', matter_type: 'I-360 VAWA self-petition packet', short: 'I-360', hint: 'Self-petition for an abused spouse, child, or parent of a U.S. citizen or LPR; kept confidential', protected: true },
    { id: 'i360_i485_vawa', label: 'I-360 / I-485 VAWA self-petition and adjustment', matter_type: 'I-360/I-485 VAWA self-petition and adjustment packet', short: 'I-360 I-485', hint: 'Self-petition and adjustment filed together when a visa is available; kept confidential', protected: true },
  ] as { id: string; label: string; matter_type: string; short?: string; hint?: string; protected?: boolean }[],
  filing_postures: [{ value: 'new filing packet', label: 'New filing' }, { value: 'RFE response', label: 'Response to an RFE' }],
}

export const STAGES: [string, string][] = [
  ['docs_review', 'Document review'], ['forms_preparer', 'Forms'], ['forms_reviewer', 'Forms review'], ['cover_letter_writer_draft', 'Cover letter'],
  ['cover_letter_researcher', 'Research'], ['cover_letter_writer_integrate', 'Letter revision'], ['cover_letter_reviewer', 'Letter review'],
  ['packet_assembly', 'Packet'], ['final_review', 'Final review'], ['attorney_handoff', 'Your memo'],
]

export const LABELS: Record<string, string> = {
  new: 'Needs documents', ready: 'Ready to build', reviewed: 'Documents reviewed', building: 'Claude is working', paused: 'Paused',
  needs_you: 'Needs your answer', waiting_client: 'Waiting on the client', draft: 'Draft packet', complete: 'Ready to file', filed: 'Filed',
}

export type Need = { text: string; kind: string; detail?: string; id?: string; key?: string; stage?: string; who?: 'attorney' | 'client' | 'system'; question?: string; recommendation?: string; blocks_filing?: boolean; fix?: string; ask?: string }

// A review note in the server's words (readmodel.review_note).
export type Note = { id: string; title: string; detail: string; severity_word: string; outcome_word: string; owner_word: string; stage_label: string }

export const FINISHED = new Set(['draft', 'complete', 'filed', 'needs_you', 'waiting_client'])

// A matter as the stand-in keeps it. What the server works out (the status, counts, case line, the needs' keys) is
// worked out when it is sent, so a test can change the matter and the next answer follows.
export function card(name: string, phase: string, docs: string[], o: { stage?: (i: number) => string; fresh?: string[]; updated?: string } = {}) {
  const finished = FINISHED.has(phase)
  const status = o.stage ?? ((i: number) => (finished ? 'passed' : phase === 'reviewed' && i === 0 ? 'passed' : 'pending'))
  const stages = STAGES.map(([id, label], i) => ({ id, label, status: status(i) }))
  const done = stages.filter(s => s.status === 'passed').length
  const current = stages.find(s => s.status === 'in_progress' || s.status === 'blocked') ?? stages.find(s => s.status === 'pending') ?? null
  const now = o.updated ?? new Date().toISOString()
  const built = finished || phase === 'reviewed'
  return {
    name,
    path: `${ROOT}/${name}`,
    phase,
    intake: {
      matter_type: 'I-130/I-485 immediate relative packet',
      matter_type_label: 'I-130 / I-485 immediate relative',
      filing_posture: 'new filing packet',
      filing_posture_label: 'New filing',
    },
    updated_at: now,
    filed_at: phase === 'filed' ? '2026-10-20T15:00:00Z' : undefined as string | undefined,
    documents: {
      count: docs.length,
      recent: docs.map(d => d.split('/').pop()!).slice(0, 5),
      files: docs.map(d => ({ name: d.split('/').pop()!, path: d, modified: now })),
      last_added: docs.length ? now : '',
      folder: `${ROOT}/${name}`,
      listed: docs.length,
      added_since_build: o.fresh ?? [],
    } as Record<string, unknown> & { count: number; files: { name: string; path: string; modified: string }[]; folders?: { path: string; count: number }[]; listed?: number },
    progress: { stages, done, total: stages.length, current, minutes_left: phase === 'building' ? 50 : null as number | null, updated_at: now },
    needs_you: [] as Need[],
    review_notes: [
      { id: 'f-forms_reviewer-1', title: 'The marriage certificate copy is faint; a clearer scan would help.', detail: '', severity_word: 'minor', outcome_word: '', owner_word: 'you', stage_label: 'Forms review' },
      { id: 'f-final_review-2', title: 'Joint records begin two months before filing.', detail: '', severity_word: 'worth fixing', outcome_word: 'RFE likely', owner_word: 'the client', stage_label: 'Final review' },
    ] as Note[],
    outputs: built
      ? {
          packet: phase === 'reviewed' ? null : { name: phase === 'complete' || phase === 'filed' ? 'Filing Packet.pdf' : 'Filing Packet (DRAFT).pdf', path: `${ROOT}/${name}/output/deliverables/Filing Packet.pdf` },
          cover_letter: null,
          memo: { name: 'Attorney Memo.md', path: `${ROOT}/${name}/output/deliverables/Attorney Memo.md`, modified: now },
          client_request: { name: 'Client Request.md', path: `${ROOT}/${name}/output/deliverables/Client Request.md` },
          forms: phase === 'reviewed' ? [] : [{ name: 'I-130.pdf', path: `${ROOT}/${name}/output/deliverables/Forms/I-130.pdf` }],
          folder: `${ROOT}/${name}/output/deliverables`,
        }
      : { packet: null, cover_letter: null },
    open_items: (phase === 'draft' || phase === 'reviewed' || phase === 'needs_you' || phase === 'waiting_client')
      ? {
          packet_status: 'draft' as const,
          updated_at: now,
          open: [
            { id: 'doc-i94', type: 'client_document', title: 'Most recent I-94 arrival record', detail: 'Proves lawful admission.', blocks_filing: true, status: 'open' as const, resolution: '' },
            { id: 'decide-i765', type: 'attorney_decision', title: 'I-765 with the I-485', question: 'Include an I-765 work permit application with the I-485?', recommendation: 'Yes, if he wants to work while the I-485 is pending.', detail: 'He has no work authorization now.', blocks_filing: false, status: 'open' as const, resolution: '' },
            { id: 'act-sign', type: 'attorney_action', title: 'Sign the G-28', detail: '', blocks_filing: true, status: 'open' as const, resolution: '' },
          ],
          resolved: [{ id: 'act-photos', type: 'attorney_action', title: 'Passport photos', resolution: 'Done (marked by the attorney on October 28, 2026)', blocks_filing: false }],
          resolved_count: 1,
          counts: { client_document: 1, attorney_decision: 1, attorney_action: 1 },
          blocking: 2,
        }
      : null,
    memo_text: built ? '# Attorney memo\n\n## Bottom line\nThe marriage is well documented; the I-94 is missing.' : '',
    client_request_text: built ? '# Documents and information we still need\n\n## Needed before we can file:\n1. **Your most recent I-94.** Download it from [the CBP site](https://i94.cbp.dhs.gov).\n\nThank you,' : '',
    // The client request in other languages, by language, beside the English one.
    translations: {} as Record<string, string>,
    attorney_instructions: '',
    timeline: [] as { at: string; kind: string; text: string; actor: string }[],
    // The stand-in's own briefs, the ones its start_run fills in and hands back; never sent on the card.
    prompts: {
      build: `Build the packet for this matter with the Senior Associate skill.\nMatter folder: ${ROOT}/${name}`,
      update: 'Update the packet.',
      continue: 'Continue.',
      review_docs: 'Review documents.',
      review_again: 'Review the documents again.',
      redo: 'Redo {{stage_label}} ({{stage_id}}).',
      stress_test: 'Officer review.',
      closeout: 'Clean up.',
    },
  }
}

export type Matter = ReturnType<typeof card>

// The sample matter's guide, as samples/barrientos-eckhardt-i601a/sample.json gives it (shortened).
export const SAMPLE_GUIDE = {
  id: 'barrientos-eckhardt-i601a',
  title: 'This is a sample matter',
  intro: 'Everything in it is fictional: an I-601A provisional waiver with 14 scanned documents marked SPECIMEN.',
  try: 'Press Review documents first. In about 5 to 10 minutes Claude lists what’s there and what’s missing.',
  caught_title: 'What a good review catches',
  caught: ['No proof the immigrant visa fee was paid.', 'His intake gives the wedding date as March 12, 2016; the certificate says March 19, 2016.'],
  after: 'Archive this matter when you’re done with it.',
}

// The sample matter at a phase: its fictional documents, the I-601A, and its guide.
export function sampleCard(phase: string) {
  const m = card('Sample - Barrientos-Eckhardt', phase, ['NVC welcome letter.pdf', 'Marriage certificate.pdf', 'Intake questionnaire - Ezequiel.pdf'])
  m.intake = { ...m.intake, matter_type: 'I-601A provisional unlawful presence waiver packet', matter_type_label: 'I-601A provisional waiver' }
  return Object.assign(m, { sample: SAMPLE_GUIDE })
}

// A run lease as the server keeps it (CONTRACTS §3).
export type TestLease = { run_id: string; kind: string; holder: string; origin?: string; started_at: string; heartbeat_at: string; stage: string | null; fresh: boolean }

// The server's status for a card (CONTRACTS §4), as it computes it: Claude is working while a fresh lease is held; a
// step still marked running without one is a pause.
export function statusOf(m: Matter, lease?: TestLease) {
  const stages = m.progress.stages
  const phase = lease?.fresh ? 'building' : m.phase === 'building' ? 'paused' : m.phase
  const finished = stages.filter(s => s.status === 'passed' || s.status === 'skipped').length
  return {
    phase,
    label: LABELS[phase] ?? phase,
    running: stages.filter(s => s.status === 'in_progress').map(s => ({ id: s.id, label: s.label })),
    step_index: Math.min(finished + 1, stages.length),
    step_total: stages.length,
    lease: lease ?? null,
    open_items_state: (m as { open_items_state?: string }).open_items_state ?? (m.open_items ? 'ok' : 'missing'),
  }
}

const CLIENT_TYPES = ['client_document', 'client_question']

// What is needed before filing, counted as readmodel.counts_for counts it.
function countsOf(m: Matter) {
  const blocking = { client: 0, you: 0, risks: 0 }
  for (const it of m.open_items?.open ?? []) {
    if (!it.blocks_filing) continue
    if (it.type === 'risk') blocking.risks += 1
    else if (CLIENT_TYPES.includes(it.type)) blocking.client += 1
    else blocking.you += 1
  }
  if (statusOf(m).open_items_state === 'damaged') blocking.you += 1
  const questions = needsOf(m).filter(n => n.who === 'attorney')
  const answers = (m as Matter & { answers?: Record<string, unknown> }).answers ?? {}
  return {
    needed_before_filing: blocking.client + blocking.you + blocking.risks, blocking,
    decisions_open: questions.length, decisions_answered: questions.filter(n => n.key in answers).length,
    open_total: m.open_items?.open.length ?? 0, resolved_total: m.open_items?.resolved_count ?? 0,
  }
}

// The needs as the server sends them: each with its key (matter_state.question_key: the id, else its words), who
// acts and the step, never empty.
function needsOf(m: Matter) {
  return m.needs_you.map(n => ({ ...n, id: n.id ?? '', key: n.key || n.id || `q-${(n.question ?? n.text).replace(/\s+/g, ' ').trim().toLowerCase()}`, who: n.who ?? 'attorney', stage: n.stage ?? '' }))
}

// The case as the list and every header name it: in a protected matter its form numbers only (readmodel.case_line).
function caseLine(m: Matter) {
  const label = m.intake.matter_type_label
  return metaOf(m).protected ? [...new Set((label.match(/\b(?:I|N|G)-\d+[A-Z]?\b/gi) ?? []).map(f => f.toUpperCase()))].join(' ') : label
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

// The one thing to do next, as a list row says it (readmodel.next_line).
function nextLine(phase: string, m: Matter, counts: ReturnType<typeof countsOf>) {
  const needs = needsOf(m)
  const questions = needs.filter(n => n.who === 'attorney').length
  const setup = needs.filter(n => n.who === 'system').length
  const client = counts.blocking.client || needs.filter(n => n.who === 'client').length
  switch (phase) {
    case 'new': return "Add the client's documents"
    case 'ready': case 'reviewed': return 'Build the packet'
    case 'paused': return 'Continue building'
    case 'needs_you': return setup && !questions ? (setup === 1 ? 'Fix a setup problem' : `Fix ${setup} setup problems`) : `Answer ${plural(questions, 'question', 'questions')}`
    case 'waiting_client': return client ? `Waiting on ${plural(client, 'item', 'items')} from the client` : 'Waiting on the client'
    case 'draft': return counts.needed_before_filing ? `${counts.needed_before_filing} needed before filing` : 'Read the draft packet'
    case 'complete': return 'Open the packet'
    default: return ''
  }
}

// The card the server sends: its status, counts, settings, saved answers and words; never the stand-in's briefs.
function sent(m: Matter, lease?: TestLease) {
  const { prompts: _prompts, translations, ...rest } = m
  return {
    ...rest, status: statusOf(m, lease), counts: countsOf(m), case_line: caseLine(m), needs_you: needsOf(m), meta: metaOf(m),
    answers: (m as Matter & { answers?: unknown }).answers ?? {},
    client_request_texts: { ...(m.client_request_text ? { English: m.client_request_text } : {}), ...translations },
  }
}

// A row of the matters list, as readmodel.list_row sends it.
function row(m: Matter, lease?: TestLease, unattended = false) {
  const s = statusOf(m, lease)
  const counts = countsOf(m)
  const names = s.running.map(x => x.label)
  return {
    name: m.name, path: m.path, phase: s.phase, label: s.label, case_line: caseLine(m), next_line: nextLine(s.phase, m, counts),
    running_line: s.phase === 'building' ? `step ${s.step_index} of ${s.step_total}${names.length ? `: ${names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`}` : ''}` : '',
    updated_at: m.updated_at, archived: Boolean(metaOf(m).archived_at), sample: Boolean((m as Matter & { sample?: unknown }).sample),
    counts, unattended_run: unattended, lease: rowLease(lease), ...(m.filed_at ? { filed_at: m.filed_at } : {}),
  }
}

// The payload the server sends: the open matter's card, and the matters list without the archived ones, counted.
export function payload(matter: Matter | null, matters: Matter[], catalog = CATALOG, leases: Record<string, TestLease> = {}) {
  return {
    version: '0.9.1',
    matters_root: ROOT,
    catalog,
    archived_count: matters.filter(m => metaOf(m).archived_at).length,
    matters: matters.filter(m => !metaOf(m).archived_at).map(m => row(m, leases[m.path])),
    matter: matter ? sent(matter, leases[matter.path]) : null,
  }
}

// A list row's part of the lease (readmodel.lease_row).
function rowLease(l?: TestLease) {
  return l ? { run_id: l.run_id, holder: l.holder, origin: l.origin ?? l.holder, started_at: l.started_at, fresh: l.fresh } : null
}

export const answer = (value: unknown, exitCode = 0) => ({
  value: { exitCode, stdout: JSON.stringify(value), stderr: '', isStdoutTruncated: false, isStderrTruncated: false },
})

// The server's doctor rows, as it writes them.
export const GOOD_CHECKS = [
  { id: 'uv', label: 'uv', ok: true, required: true, level: 'required', detail: 'Runs Senior Associate’s tools.' },
  { id: 'ghostscript', label: 'Ghostscript', ok: true, required: true, level: 'required', detail: 'Prints the filled USCIS forms.' },
  { id: 'profile', label: 'Your details', ok: false, required: false, level: 'recommended', detail: 'Your name, firm and bar number for the G-28 and the letter.', fix: 'Add your details. It takes about 2 minutes, once.' },
  { id: 'libreoffice', label: 'LibreOffice', ok: false, required: false, level: 'optional', detail: 'Optional. Makes the cover letter’s PDF match Word exactly; without it the PDF is made another way.', fix: 'Claude can install LibreOffice for you.', ask: 'Install LibreOffice for Senior Associate.' },
]
export const NO_GS = GOOD_CHECKS.map(c => (c.id === 'ghostscript' ? { ...c, ok: false, detail: 'Prints the filled USCIS forms. A build can’t finish the forms without it.', fix: 'Claude can install Ghostscript for you.', ask: 'Install Ghostscript for Senior Associate.' } : c))

export type Options = { checks?: unknown[]; profile?: Record<string, string>; catalog?: typeof CATALOG; dropSubmit?: string; picking?: Promise<void>
  /** The private terms privacy_terms gives for every matter (asked afresh each time when a function). */
  terms?: string[] | (() => string[])
  /** privacy_terms fails, as when the matter can't be read. */
  termsFail?: boolean
  /** The server's summary when files are added; by default, how many were added. */
  addMessage?: string
  /** The setup check fails this many times (a busy disk, a slow start) before it answers. */
  doctorFails?: number
  /** A matter folder that is gone (moved or renamed in Finder): every op on it fails as the server says so. */
  gone?: string[]
  /** Matters an unattended run holds by the network gate's rule, though no fresh lease shows it (list rows say so). */
  unattended?: string[]
  /** Holds a matter's state answer, worked out when asked, until this settles: a refresh that comes back late. */
  lateState?: () => Promise<void> | undefined
  /** The server's sample matter: added on the first open of an empty Matters folder (ensure_sample), once, and by
   *  add_sample. */
  sample?: boolean
}

// The server and the host's side effects, stood in for. `seed` seeds the list.
export function world(on: On, seed: Matter[] = [], stored: Record<string, unknown> = {}, o: Options = {}) {
  const catalog = o.catalog ?? CATALOG
  const ops: string[] = []
  const requests: Record<string, unknown>[] = []
  let profile: Record<string, string> = o.profile ?? {}
  let checks = o.checks ?? GOOD_CHECKS
  const store: Record<string, unknown> = { ...stored }
  const matters: Matter[] = [...seed]
  let current: Matter | null = null
  const toasts: string[] = []
  const copied: string[] = []
  const submitted: string[] = []
  // The run leases the server keeps, by matter path.
  const leases: Record<string, TestLease> = {}
  let runs = 0
  let doctorFails = o.doctorFails ?? 0
  let sampleOffered = false
  on('prompt.submit', async (_$, e) => { submitted.push(e.text); return o.dropSubmit ? { drop: o.dropSubmit } : { text: e.text } })
  on('ui.toast', async (_$, e) => { toasts.push(e.text); return { value: undefined } })
  on('ui.copy', async (_$, e) => { copied.push(e.text); return { value: { isCopied: true } } })
  on('fs.exists', async () => ({ value: true }))
  on('tool.list', async () => ({ value: [] }))
  on('store.get', async (_$, e) => ({ value: store[e.key] }))
  on('store.set', async (_$, e) => { store[e.key] = e.value; return { value: undefined } })
  on('process.run', async (_$, e) => {
    const argv = e.argv as readonly string[]
    const request = JSON.parse(argv[argv.length - 1] ?? '{}') as Record<string, string>
    ops.push(request.op ?? '')
    requests.push(request)
    const withProfile = (p: ReturnType<typeof payload>) => ({ ...p, profile })
    if (request.matter_path && o.gone?.includes(request.matter_path)) {
      return answer({ error: `${request.matter_path.split('/').pop()} isn't in your Matters folder anymore. It may have been moved or renamed in Finder.` }, 1)
    }
    if (request.op === 'doctor') {
      if (doctorFails > 0) {
        doctorFails -= 1
        return answer({ error: 'The setup check timed out.' }, 1)
      }
      return answer({ checks: (checks as { id: string }[]).map(c => (c.id === 'profile' ? { ...c, ok: Boolean(profile.attorney_name) } : c)), version: '0.9.1' })
    }
    if (request.op === 'save_profile') {
      profile = request.profile as unknown as Record<string, string>
      return answer(withProfile(payload(null, matters, catalog, leases)))
    }
    const find = (p?: string) => matters.find(m => m.path === p || m.name === p) ?? null
    if (request.op === 'start_run') {
      const held = leases[request.matter_path!]
      if (held?.fresh) return answer({ error: 'Claude is already working on this matter. Try again when it finishes.' }, 1)
      runs += 1
      const at = new Date().toISOString()
      leases[request.matter_path!] = { run_id: `run-${runs}`, kind: request.kind ?? 'build', holder: 'app', started_at: at, heartbeat_at: at, stage: null, fresh: true }
      // The brief, filled in as the server fills it: the redo's step, the run id, every saved answer, the note.
      const m = find(request.matter_path)!
      let brief = m.prompts[request.kind as keyof typeof m.prompts] ?? (request.kind === 'update' ? m.prompts.continue : '')
      const stage = m.progress.stages.find(x => x.id === request.stage_id)
      if (request.kind === 'redo') brief = brief.split('{{stage_id}}').join(stage?.id ?? '').split('{{stage_label}}').join(stage?.label ?? '')
      const saved = Object.entries((m as Matter & { answers?: Record<string, { question: string; answer: string }> }).answers ?? {})
      const parts = [brief, `Your run id is run-${runs}.`]
      if (saved.length) parts.push(`The attorney's answers to the open questions:\n${saved.map(([key, a], i) => `${i + 1}. ${a.question}${/^(q|report)-/.test(key) ? '' : ` (open item ${key})`}\n   Answer: ${a.answer}`).join('\n')}`)
      if (request.note) parts.push(`The attorney's instructions for this run (record what they settle on the open items, and redo whatever work they change):\n${request.note}`)
      return answer({ ...withProfile(payload(m, matters, catalog, leases)), run_id: `run-${runs}`, prompt: parts.join('\n\n') })
    }
    if (request.op === 'heartbeat_run') {
      const held = leases[request.matter_path!]
      const ok = Boolean(held && held.run_id === request.run_id)
      if (ok) held!.heartbeat_at = new Date().toISOString()
      return answer({ status: 'heartbeat', ok, lease: held ?? null })
    }
    if (request.op === 'cancel_start') {
      // As the server does: taken back only while the app holds it; a run that took it up keeps it.
      const held = leases[request.matter_path!]
      const start = !held || held.run_id !== request.run_id ? 'gone' : held.holder === 'app' ? 'cancelled' : 'taken_up'
      if (start === 'cancelled') delete leases[request.matter_path!]
      return answer({ ...withProfile(payload(find(request.matter_path), matters, catalog, leases)), status: 'start_cancelled', start })
    }
    if (request.op === 'abandon_run') {
      const held = leases[request.matter_path!]
      if (held?.fresh && held.run_id !== request.run_id) return answer({ error: 'Claude has just started on this matter again, so nothing was changed. This page shows it.' }, 1)
      if (held?.run_id === request.run_id) delete leases[request.matter_path!]
      return answer({ ...withProfile(payload(find(request.matter_path), matters, catalog, leases)), status: 'run_let_go' })
    }
    if (request.op === 'release_run') {
      if (leases[request.matter_path!]?.run_id === request.run_id) delete leases[request.matter_path!]
      // As the server does: the matter as the run left it.
      return answer({ ...withProfile(payload(find(request.matter_path), matters, catalog, leases)), status: 'run_released' })
    }
    if (request.op === 'save_answer') {
      const m = find(request.matter_path)!
      const kept = { ...((m as { answers?: Record<string, unknown> }).answers ?? {}) }
      if ((request.answer ?? '').trim()) kept[request.key!] = { question: request.question, answer: request.answer, saved_at: new Date().toISOString() }
      else delete kept[request.key!]
      ;(m as { answers?: Record<string, unknown> }).answers = kept
      return answer(withProfile(payload(m, matters, catalog, leases)))
    }
    // The sample matter, as the server adds it: once, to an empty Matters folder, or again from Help.
    if (o.sample && ((request.op === 'state' && request.ensure_sample && !sampleOffered) || request.op === 'add_sample')) {
      sampleOffered = true
      const there = matters.find(m => (m as Matter & { sample?: unknown }).sample)
      if (!there && (request.op === 'add_sample' || matters.length === 0)) matters.push(sampleCard('ready'))
      if (request.op === 'add_sample') {
        current = matters.find(m => (m as Matter & { sample?: unknown }).sample) ?? null
        return answer(withProfile(payload(current, matters, catalog, leases)))
      }
    }
    if (request.op === 'create') {
      current = card(request.name ?? 'Unnamed', 'new', [])
      matters.push(current)
      return answer(withProfile(payload(current, matters, catalog, leases)))
    }
    if (request.op === 'add_documents' || request.op === 'add_folder') {
      if (o.picking) await o.picking
      const m = find(request.matter_path)
      if (!m) return answer({ error: 'no such matter' }, 1)
      const added = request.op === 'add_documents' ? ['Passport.pdf', 'Marriage certificate.pdf'] : ['Tax returns/2025 return.pdf', 'Birth certificate.pdf']
      if (m.phase === 'new' || m.phase === 'ready') {
        current = card(m.name, 'ready', [...m.documents.files.map(f => f.path), ...added])
        matters.splice(matters.indexOf(m), 1, current)
      } else current = m
      return answer({ ...withProfile(payload(current, matters, catalog, leases)), added, cancelled: false, message: o.addMessage ?? `Added ${added.length} files.` })
    }
    if (request.op === 'open_output' || request.op === 'open_folder' || request.op === 'open_document') return answer({ opened: 'x' })
    // Going back: take a document out and put it back, reopen an item, change what is being filed.
    if (request.op === 'remove_document' || request.op === 'restore_document') {
      const m = find(request.matter_path)!
      const docs = m.documents as typeof m.documents & { removed?: { name: string; path: string; kept: string }[] }
      if (request.op === 'remove_document') {
        const f = docs.files.find(x => x.path === request.path)!
        docs.files = docs.files.filter(x => x !== f)
        docs.count = docs.files.length
        const kept = `output/removed documents/${f.path}`
        docs.removed = [{ name: f.name, path: f.path, kept }, ...(docs.removed ?? [])]
        return answer({ ...withProfile(payload(m, matters, catalog, leases)), removed: { name: f.name, path: f.path, kept } })
      }
      const r = (docs.removed ?? []).find(x => x.kept === request.kept)!
      docs.removed = (docs.removed ?? []).filter(x => x !== r)
      docs.files = [...docs.files, { name: r.name, path: r.path, modified: new Date().toISOString() }]
      docs.count = docs.files.length
      return answer({ ...withProfile(payload(m, matters, catalog, leases)), restored: { name: r.name, path: r.path } })
    }
    if (request.op === 'reopen_item') {
      const m = find(request.matter_path)!
      const ledger = m.open_items!
      const it = ledger.resolved.find(x => x.id === request.id)!
      ledger.resolved = ledger.resolved.filter(x => x !== it)
      ledger.resolved_count -= 1
      ledger.open.push({ id: it.id, type: it.type, title: it.title, detail: '', blocks_filing: it.blocks_filing, status: 'open', resolution: '' } as never)
      return answer(withProfile(payload(m, matters, catalog, leases)))
    }
    if (request.op === 'change_intake') {
      const m = find(request.matter_path)!
      const t = catalog.matter_types.find(x => x.id === request.matter_type)
      const next = card(m.name, 'ready', m.documents.files.map(f => f.path))
      next.intake = { ...next.intake, matter_type: t?.matter_type ?? request.matter_type!, matter_type_label: t?.label ?? request.matter_type!, filing_posture: request.filing_posture!, filing_posture_label: request.filing_posture! }
      matters.splice(matters.indexOf(m), 1, next)
      current = next
      return answer({ ...withProfile(payload(next, matters, catalog, leases)), set_aside: 'output/earlier/Set aside 2026-10-29 09.41' })
    }
    if (request.op === 'set_instructions') {
      const m = find(request.matter_path)!
      m.attorney_instructions = (request.text ?? '').trim()
      // As the server does: once there are instructions, the brief names the file they're saved in.
      const build = m.prompts.build.split('\nAttorney instructions:')[0]!
      m.prompts = { ...m.prompts, build: m.attorney_instructions ? `${build}\nAttorney instructions: ${m.path}/output/working/workflow/attorney-instructions.md` : build }
      current = m
      return answer(withProfile(payload(m, matters, catalog, leases)))
    }
    if (request.op === 'list') {
      const rows = matters.map(m => row(m, leases[m.path], Boolean(o.unattended?.includes(m.path))))
      return answer({ status: 'list', matters: request.include_archived ? rows : rows.filter(r => !r.archived), archived_count: rows.filter(r => r.archived).length })
    }
    if (request.op === 'privacy_terms') {
      if (o.termsFail) return answer({ error: 'The privacy check could not read this matter.' }, 1)
      const terms = typeof o.terms === 'function' ? o.terms() : o.terms ?? []
      return answer({ status: 'privacy_terms', terms, names: terms.filter(t => !/\d/.test(t) && !/\s/.test(t)), full_names: terms.filter(t => /\s/.test(t) && !/\d/.test(t)), identifiers: terms.filter(t => /\d/.test(t)) })
    }
    if (request.op === 'set_meta' || request.op === 'archive' || request.op === 'unarchive') {
      const m = find(request.matter_path)!
      const meta = metaOf(m)
      const { op: _op, matter_path: _p, matter: _m, stay: _s, ...changes } = request as Record<string, unknown>
      Object.assign(meta, request.op === 'set_meta' ? changes : { archived_at: request.op === 'archive' ? new Date().toISOString() : null })
      current = m
      return answer(withProfile(payload(m, matters, catalog, leases)))
    }
    if (request.op === 'resolve_item' || request.op === 'mark_filed' || request.op === 'unmark_filed') {
      current = find(request.matter_path)
      return answer(withProfile(payload(current, matters, catalog, leases)))
    }
    if (request.matter_path) {
      current = find(request.matter_path)
      const res = answer(withProfile(payload(current, matters, catalog, leases)))
      const late = request.op === 'state' ? o.lateState?.() : undefined
      if (late) await late
      return res
    }
    return answer(withProfile(payload(null, matters, catalog, leases)))
  })
  return { ops, store, requests, toasts, copied, submitted, matters, leases, setChecks: (c: unknown[]) => { checks = c } }
}

// A matter's settings as the server keeps them (CONTRACTS §6).
export function metaOf(m: Matter): Record<string, unknown> {
  const x = m as Matter & { meta?: Record<string, unknown> }
  x.meta ??= { protected: false, client_language: 'English', filing_method: 'paper', archived_at: null }
  return x.meta
}

// An agent the app can start, and what the session's agent list says about it.
export function agents(on: On, description: string, id = 'agent-1') {
  const spawned: Record<string, unknown>[] = []
  let status: AgentStatus = 'running'
  on('agent.spawn', async (_$, e) => { spawned.push({ ...e }); return { model: 'opus', agentId: id } })
  on('agent.list', async () => ({ value: spawned.length ? [{ id, description, type: 'senior-associate:senior-associate', status }] : [] }))
  on('turn.complete', async () => ({ text: '' }))
  return { spawned, finish: (s: AgentStatus) => { status = s } }
}

export const PANE = { plugin: PLUGIN, surface: 'desktop', component: 'Pane', requestId: 'senior-associate', props: { bodyColumns: 80 } } as const
export const ROW = { plugin: PLUGIN, surface: 'desktop', component: 'CommandOutput', requestId: 'msg-1', props: { command: 'matters', args: '', text: 'Senior Associate', isErrored: false } } as const
export const SEEN = { onboarded: true, lastMatter: '', setupSeen: true, inlineUses: 5, pickerSeen: true }
export const ANA = { attorney_name: 'Ana Ruiz', bar_number: '24012345' }
export const DOCS = ['Passport.pdf', 'Marriage certificate.pdf']
export const OPTS = (extra: Record<string, unknown> = {}) => ({ timeoutMs: 20000, options: { matters_root: ROOT, exemplars_dir: `${ROOT}/Exemplar`, ...extra } })

// The screen's main actions are buttons keyed `main:<id>`, each with a line under it on what it does.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function act(ui: any, id: string) {
  return ui.press({ plugin: PLUGIN, key: `main:${id}` })
}
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const textOf = (el: any): string => (typeof el === 'string' ? el : (el?.children ?? []).map(textOf).join(''))

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function actionTexts(ui: any): Promise<string[]> {
  const bar = await ui.find({ type: 'Box', key: 'actions' })
  const out: string[] = []
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const walk = (el: any) => {
    if (!el || typeof el !== 'object') return
    if (el.type === 'Button') out.push(String(el.props?.label ?? textOf(el)))
    else if (el.type === 'Text') out.push(textOf(el))
    for (const child of el.children ?? []) walk(child)
  }
  walk(bar)
  return out
}
// What would not follow the app's light or dark theme on the desktop, which draws a Button's label alone and every
// field and Button in the app's own colours: a Text in a fixed colour, a fixed fill behind anything with words (only an
// empty bar may have one), and a Button with children or no label.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function offTheme(el: any, out: string[] = []): string[] {
  if (!el || typeof el !== 'object') return out
  const hex = (c: unknown) => typeof c === 'string' && c.startsWith('#')
  if (el.type === 'Text' && hex(el.props?.color)) out.push(`text in ${el.props.color}: ${textOf(el)}`)
  if (el.type === 'Box' && hex(el.props?.backgroundColor) && (el.children ?? []).length) out.push(`fill ${el.props.backgroundColor} behind: ${textOf(el).slice(0, 40)}`)
  if (el.type === 'Button' && ((el.children ?? []).length || !el.props?.label)) out.push(`button ${el.props?.key}`)
  for (const child of el.children ?? []) offTheme(child, out)
  return out
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function inActions(ui: any, pattern: RegExp): Promise<string | undefined> {
  return (await actionTexts(ui)).find(t => pattern.test(t))
}

// The host's clock starts at the real time, so "updated just now" and "2 hours ago" read as they would.
export async function open(_$: unknown, on: On) {
  const clock = mock.clock(on, { now: Date.now() })
  return { clock }
}

type Clock = Awaited<ReturnType<typeof open>>['clock']

// The side panel, drawn once its first load is in, and `tap`: a press and everything it sets off.
export async function mount($: unknown, clock: Clock) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ui: any = await ($ as { ui: { mount: (a: never) => Promise<unknown> } }).ui.mount({ ...PANE, props: PANE.props } as never)
  await clock.advance(10)
  await clock.settle()
  // The Overview folds More you can do, the attorney instructions and the matter's details: a press inside one opens
  // it first, as the attorney would.
  const tap = async (key: string) => {
    const section = /^do-/.test(key) ? 'sec-more' : /^(open-folder|open-deliverables|open-earlier)$/.test(key) ? 'sec-details' : ''
    if (section && !(await ui.find({ type: 'Button', key })) && (await ui.find({ type: 'Button', key: section }))) {
      await ui.press({ plugin: PLUGIN, key: section })
      await clock.settle()
    }
    await ui.press({ plugin: PLUGIN, key })
    await clock.settle()
  }
  return { ui, tap }
}

// Opens a folded section of the Overview (sec-more, sec-instructions, sec-details) unless it is open already.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export async function unfold(ui: any, tap: (key: string) => Promise<void>, section: string) {
  const button = await ui.find({ type: 'Button', key: section })
  if (button && /^▸/.test(String(button.props?.label ?? ''))) await tap(section)
}

// The app as most tests meet it: the stand-in world with these matters and the attorney's details, the welcome and
// the setup check already seen, the side panel drawn, and the first matter's page open (unless `open: false`).
// `o` is the world's own options object, so a test can change what the server does partway through.
export async function boot($: unknown, on: On, seed: Matter[] = [], o: Options & { open?: boolean } = {}, stored: Record<string, unknown> = {}) {
  const { clock } = await open($, on)
  if (!('profile' in o)) o.profile = ANA
  const w = world(on, seed, { prefs: { ...SEEN, lastMatter: seed[0]?.path ?? '' }, ...stored }, o)
  const { ui, tap } = await mount($, clock)
  if (seed[0] && o.open !== false) await tap(`open:${seed[0].path}`)
  return { ...w, clock, ui, tap }
}

