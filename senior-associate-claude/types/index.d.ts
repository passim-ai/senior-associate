export type View = 'welcome' | 'setup' | 'home' | 'new' | 'matter' | 'documents' | 'packet' | 'memo' | 'request' | 'items' | 'profile' | 'help'
  /** Redo a step, review the documents again, or tell Claude what to change: what happens, then the press that starts it. */
  | 'redo'
  /** Change what is being filed for an existing matter. */
  | 'intake'
  /** What happened on the matter, newest first. */
  | 'timeline'

/** The New matter screen's choices so far: the client's name is kept outside state while typing. */
export type Draft = {
  name: string
  typeId: string
  posture: string
  other: string
  /** How it will be filed: on paper (the default) or online. */
  method?: 'paper' | 'online'
  /** The attorney marked the client protected under 8 U.S.C. 1367 (a VAWA, T or U case is protected by its type). */
  protect?: boolean
}

export type Stage = { id: string; label: string; status: string }

/** One row of the Matters list, in the server's words: its status, its case, and the one thing to do next. */
export type MatterRow = {
  /** The matter's folder name: how requests to Claude name it. */
  name: string
  /** The name the app shows it under: the folder's name, or for a protected matter (whose folder is "Matter 3F9A…") the name the attorney gave it. */
  title?: string
  path: string
  phase: string
  label: string
  case_line: string
  next_line: string
  /** "step 3 of 10: Forms review and Cover letter", while Claude is working. */
  running_line: string
  archived: boolean
  /** The sample matter, made from the fictional documents that ship with the plugin. */
  sample?: boolean
  updated_at: string
  filed_at?: string
  /** A matter the server can't read, or a link to a folder outside the Matters folder (phase "problem"): what to say,
   *  and the request that has Claude repair it. */
  problem?: boolean
  ask?: string
  /** A background run (the app's or an orchestrator's) holds the matter by the network gate's rule, whatever the
   *  phase says: the research gate checks the matter's terms. */
  unattended_run?: boolean
  /** The run lease, as much of it as a row needs: the app tells its own start waiting in the chat box from a run it
   *  didn't start, and never shows Stopped while another run works on the matter. */
  lease: RowLease | null
}

/** Who is working on a matter now: the run lease (CONTRACTS §3). Fresh: not released, heartbeat within 30 minutes.
 *  `origin`: who took it first (the app, the chat, an orchestrator). */
export type Lease = { run_id: string; kind: string; holder: 'app' | 'chat' | 'orchestrator' | string; origin?: string; started_at: string; heartbeat_at: string; stage?: string | null; fresh: boolean }
/** A list row's part of the lease. */
export type RowLease = Pick<Lease, 'run_id' | 'holder' | 'origin' | 'started_at' | 'fresh'>

/** The server's status for a matter, the one source of truth (CONTRACTS §4). */
export type CardStatus = {
  phase: string
  label: string
  /** Steps in progress now; more than one when steps run side by side. */
  running: { id: string; label: string }[]
  step_index: number
  step_total: number
  lease: Lease | null
  open_items_state: 'missing' | 'ok' | 'damaged'
}

/** What is needed before filing, counted by the server so the parts always add up (CONTRACTS §4). */
export type Counts = {
  needed_before_filing: number
  /** `you` is attorney decisions, attorney actions and setup problems. */
  blocking: { client: number; you: number; risks: number }
  decisions_open: number
  decisions_answered: number
  open_total: number
  resolved_total: number
}

/** An answer the attorney saved, kept in the matter until a run works it in (CONTRACTS §5). */
export type SavedAnswer = { question: string; answer: string; saved_at: string }

/** The attorney's settings for the matter (CONTRACTS §6). */
export type Meta = {
  forum?: string
  circuit?: string
  jurisdiction_basis?: string
  /** The effective value: the setting, or a case type that can only be protected (the server's one rule). */
  protected: boolean
  /** Why: catalog, attorney or docs_review for the setting; case_type when only the case type makes it so. */
  protected_reason?: string
  archived_at?: string | null
  client_language: string
  filing_method: 'paper' | 'online'
  updated_at?: string
}

/** One line of the matter's timeline; `text` is plain English (CONTRACTS §7). */
export type TimelineEvent = { at: string; kind: string; text: string; actor: 'app' | 'claude' | 'attorney' | string }

export type MatterFile = { name: string; path: string; modified: string }

/** `path` is where it was in the matter; `kept` where it waits to be put back. */
export type RemovedFile = { name: string; path: string; kept: string; removed_at?: string }

/** An open review note, in the words the server gives it (CONTRACTS §5): never a raw severity, outcome or owner. */
export type ReviewNote = {
  id: string
  title: string
  detail: string
  /** "important", "worth fixing", "minor", "check by hand" or "note". */
  severity_word: string
  /** "RFE likely", "NOID likely", "denial likely", "your call", or "". */
  outcome_word: string
  /** Who is to fix it: "you", "the client" or "Claude". */
  owner_word: string
  stage_label: string
}

export type FileRef = { name: string; path: string; modified?: string }
/** The memo or a client request: the Markdown, and in `pdf` its PDF when that is up to date. */
export type MarkdownRef = FileRef & { pdf?: string }

/** One entry of the matter's open items (output/deliverables/open-items.json). */
export type OpenItem = {
  id: string
  type: 'client_document' | 'client_question' | 'attorney_decision' | 'attorney_action' | 'risk' | string
  title: string
  detail: string
  blocks_filing: boolean
  status: 'open' | 'resolved'
  resolution: string
  /** A decision as one short question to the attorney. */
  question?: string
  /** Claude's recommended answer, starting with the answer. */
  recommendation?: string
  /** Who acts, when the type doesn't make it obvious: a setup problem is "system". */
  who?: 'attorney' | 'client' | 'system' | string
  stage?: string
}

/** An item already settled, as What's left lists it under Show resolved. */
export type ResolvedItem = { id: string; type: string; title: string; resolution: string; blocks_filing: boolean }

export type OpenItems = {
  packet_status: 'draft' | 'ready_to_file'
  updated_at: string
  open: OpenItem[]
  resolved: ResolvedItem[]
  resolved_count: number
  counts: Record<string, number>
}

/** Something only the attorney (or the client, or the attorney's Mac) can resolve. */
export type NeedItem = {
  text: string
  kind: string
  /** The answer's key, `question_key(item_id, question)`: never empty (CONTRACTS §5). */
  key: string
  blocks_filing?: boolean
  detail?: string
  id: string
  /** The plain step name, kept apart from the text. */
  stage: string
  who: 'attorney' | 'client' | 'system'
  question?: string
  recommendation?: string
  /** A setup problem's way out, as a plain sentence, and the request that has Claude do it. */
  fix?: string
  ask?: string
}

/** What the sample matter's page tells a new attorney (samples/<id>/sample.json). */
export type SampleGuide = { id: string; title?: string; intro?: string; try?: string; caught_title?: string; caught?: string[]; after?: string }

/** What the research behind the cover letter covered, in the server's words (scripts/research_summary.py): `checked`
 *  with BIA Edge, researched `without` it, or researched with no check of the law on record (`unrecorded`). */
export type Research = {
  state: 'checked' | 'without' | 'unrecorded'
  /** Why it was researched without BIA Edge: no_access, not_connected, refused, or ''. */
  reason: string
  /** "Checked November 9, 2026 with BIA Edge", "Researched without BIA Edge". */
  headline: string
  lines: string[]
  caveat: string
  checked_at: string
  /** When the receipt of the check was last written (ISO), '' when there is none. */
  receipt_at?: string
  /** Days since the law was last checked; null when it never was. */
  age_days: number | null
  /** False when the library answered but the check of the cases' later treatment wasn't finished. */
  treatment_checked?: boolean
  authorities: number
  cases: number
  /** Points left without case-law research because BIA Edge wasn't available, in the research's own words. */
  not_researched: string[]
  not_researched_count: number
  /** What the check left open (an unconfirmed circuit, say). */
  unresolved: string[]
  /** Unpublished decisions on similar facts, summarized in the memo. */
  similar: number
}

/** What Passim last answered through BIA Edge when the account behind it had no research access: its own words, when,
 *  and whether choosing a plan resolves it (`plan`) or the account needs looking at. Cleared by the next answer with results. */
export type Access = { message: string; at: string; plan: boolean; server: string }

export type Card = {
  /** Where the packet stands for the attorney's sign-off: `blockers` make approval impossible (nothing assembled); `risks` are what to weigh first, and approving with any open takes a reason. */
  filing_readiness?: { eligible: boolean; approved: boolean; digest: string; blockers: string[]; risks?: string[]; attorney: string; approved_at: string; risk_note?: string }
  /** The research behind the letter; null before the letter has been researched. */
  research?: Research | null
  /** The matter's folder name: how requests to Claude name it. */
  name: string
  /** The name the app shows it under (see MatterRow.title). */
  title?: string
  path: string
  /** new, ready, reviewed, building, paused, needs_you, waiting_client, draft, complete, filed. */
  phase: string
  phase_label: string
  intake: { matter_type: string; matter_type_label: string; filing_posture: string; filing_posture_label: string; deliverable?: string }
  /** The case as every screen names it: in a protected matter its form numbers only, as the list shows it. */
  case_line: string
  created_at?: string
  updated_at?: string
  filed_at?: string
  /** A folder made outside the app: no intake recorded yet. */
  needs_intake?: boolean
  /** The sample matter's guide: what to try, and what a good document review catches; null otherwise. */
  sample?: SampleGuide | null
  documents: {
    count: number
    recent: string[]
    files: MatterFile[]
    last_added: string
    folder: string
    /** How many of the files are in `files` (the newest, when there are many). */
    listed?: number
    /** Every folder with its full count, the matter folder itself as "". */
    folders?: { path: string; count: number }[]
    /** Client files newer than the last finished build or document review. */
    added_since_build?: string[]
    /** Files Claude had already read, since replaced with new contents. */
    changed_since_build?: string[]
    /** Documents the attorney removed, kept under output/removed documents so they can be put back. */
    removed?: RemovedFile[]
    /** Of those, the ones removed after Claude last finished a step: an update takes them out of the packet. */
    removed_since_build?: string[]
  }
  progress: {
    stages: Stage[]
    done: number
    total: number
    current: Stage | null
    /** About how many minutes the steps left take; null when there are none. */
    minutes_left: number | null
    updated_at?: string
  }
  needs_you: NeedItem[]
  review_notes: ReviewNote[]
  outputs: {
    packet: FileRef | null
    cover_letter: FileRef | null
    memo?: MarkdownRef | null
    client_request?: MarkdownRef | null
    forms?: FileRef[]
    folder?: string
    /** Where an earlier case's work was set aside after Change what is being filed. */
    earlier?: string
    /** The filing checklist the handoff writes and renders: fees, signatures, photos, where to mail. */
    filing_checklist?: FileRef | null
    /** For filing online: the folder of files to upload, one per form or exhibit. */
    upload_files?: FileRef | null
    /** A split filing: the paper packet for the forms USCIS takes only on paper, beside the online one. */
    paper_packet?: FileRef | null
  }
  open_items?: OpenItems | null
  memo_text?: string
  client_request_text?: string
  /** Every language the client request is written in, English first: {"English": text, "Spanish": text}. */
  client_request_texts: Record<string, string>
  /** What the attorney typed in Additional attorney instructions; every run's brief names the file it is saved in. */
  attorney_instructions?: string
  // What the attorney changed in chat since Claude last finished a step; the next update re-checks them.
  chat_changes?: { at: string; what: string }[]
  /** The server's status, counts, saved answers, settings and timeline (CONTRACTS §4–§7). */
  status: CardStatus
  counts: Counts
  answers: Record<string, SavedAnswer>
  meta: Meta
  timeline: TimelineEvent[]
}

/** The attorney's own details, used on the G-28, each form's preparer section, the letterhead, and the signature. */
export type Profile = Partial<Record<
  | 'attorney_name' | 'firm_name' | 'mailing_address' | 'phone' | 'email' | 'bar_number' | 'licensing_authority' | 'uscis_online_account_number'
  // 'no' when the attorney has no USCIS online account: every question about it is then not applicable.
  | 'has_uscis_online_account'
  // G-28 Part 2 item 1.c: 'no' or 'yes'; with 'yes', the explanation for the G-28's Part 6.
  | 'subject_to_discipline_order' | 'discipline_order_details',
  string
>>

/** One line of the setup check (the server's `doctor`). */
export type Check = { id: string; label: string; ok: boolean; required: boolean; level?: 'required' | 'recommended' | 'optional' | string; detail: string; fix?: string; ask?: string
  /** A web page that settles it, opened in the attorney's browser: one of the server's named links, and the press's words. */
  link?: { id: string; label: string }
}

export type Setup = {
  checks: Check[]
  version?: string
  /** A start the setup check held back, run by Continue. */
  pending?: { matter: string; kind: string; reply: string; stage?: string; note?: string } | null
}

export type Payload = {
  version?: string
  /** Matters archived: left out of `matters`; the light `list` op with include_archived sends their rows. */
  archived_count?: number
  matters_root?: string
  matters: MatterRow[]
  matter: Card | null
  profile?: Profile
  catalog: {
    /** short names the folder, so a protected (8 U.S.C. 1367) case's short is only form numbers. */
    matter_types: { id: string; label: string; matter_type: string; short?: string; hint?: string; protected?: boolean }[]
    filing_postures: { value: string; label: string }[]
  }
  /** Present when the app asked for it, or when something required is missing. */
  setup?: Setup & { ok?: boolean }
  /** The `doctor` op's answer. */
  checks?: Check[]
  warning?: string
  added?: string[]
  /** add_documents / add_folder: one to three plain sentences summing up what was added and what wasn't. */
  message?: string
  cancelled?: boolean
  /** remove_document's answer: the file that left the matter, and where it is kept. */
  removed?: { name: string; path: string; kept: string }
  restored?: { name: string; path: string }
  /** change_intake's answer: where the earlier case's work was set aside, '' when nothing had run. */
  set_aside?: string
}

/** A step the app runs as its own background agent: which, for which matter, and how it stands. */
export type Run = {
  agentId: string
  /** The run lease's id from the server's `start_run`, renewed on the app's tick and released when the agent ends. */
  runId?: string
  /** The agent's description exactly as the app asked for it, so a request sent from the chat box is matched to it alone. */
  description?: string
  /** The attorney has seen how it ended (the matter's page was open since); until then `/matters` opens that matter. */
  seen?: boolean
  kind: string
  matter: string
  /** The matter's name, for the notification when it finishes. */
  name: string
  label: string
  startedAt: string
  endedAt: string
  /** starting: the request waits in the chat box for the attorney's Enter. */
  status: 'starting' | 'running' | 'done' | 'failed'
  /** The agent's final report, markdown, once it has finished. */
  answer: string
  /** Why it ended other than by answering: aborted, error, refusal, or the agent list's word. */
  reason: string
  /** The attorney's answers it carried, so Try again carries them too. */
  reply: string
  /** "step 4 of 10: Cover letter", as last seen. */
  step: string
  /** The step's plain name, for "picks up at". */
  stepLabel: string
  /** What the matter's progress looked like at the last look, and when it last changed. */
  lastSeen: string
  lastChangeAt: string
  /** The agent asked to use a tool and waits for the attorney's OK. */
  waitingOk: boolean
  /** A redo's step id, so Try again redoes the same step. */
  stage?: string
  /** What the attorney told Claude to change, carried by Try again too. */
  note?: string
  /** A stop the attorney chose, or a stopped run they set aside with Not now: the matter shows its own state again. */
  dismissed?: boolean
}

/** What the app remembers between sessions. */
export type Prefs = {
  onboarded: boolean
  lastMatter: string
  /** The setup check was shown once. */
  setupSeen: boolean
  /** How many times /matters was drawn in the conversation, for the side-panel tip. */
  inlineUses: number
  /** The first file picker has opened (macOS asks about System Events before it). */
  pickerSeen: boolean
}

/** A message under the navigation: a warning, a wait, or a save confirmed; with a request for Claude when Claude can fix it. */
export type Note = { text: string; tone: 'warn' | 'wait' | 'ok'; ask?: string; press?: { id: string; label: string } }

/** Where Your details, Setup and Help go back to. */
export type BackTo = { view: View; matter: string }

declare module 'claude-code' {
  interface PluginState {
    'senior-associate': {
      view: View
      payload: Payload | null
      draft: Draft
      note: Note
      busy: boolean
      runs: Record<string, Run>
      prefs: Prefs
      filter: string
      answers: Record<string, string>
      setup: Setup | null
      /** The matter whose Build waits on the Your details question, the kind of run, and the answers it carries. */
      gate: { matter: string; kind: string; reply: string } | null
      origins: Partial<Record<'profile' | 'setup' | 'help' | 'request', BackTo>>
      /** Folders opened past their first files, "more-types", "filed". */
      expanded: string[]
      /** New matter: Create pressed with no case chosen. */
      caseMissing: boolean
      /** How many times the side panel was opened this session (a redraw signal for the inline rows). */
      docked: number
      /** The Redo screen's subject: a step id, 'docs_review' for a fresh document review, or '' for Tell Claude what
       *  to change; and the screen to go back to. */
      redo: { matter: string; stage: string; from: View } | null
      /** The press waiting on "Yes" before it happens: 'stop', or 'remove:<path>'. */
      confirm: string
      /** The matters list's order: 'updated' (the default), 'name', 'case' or 'status'. */
      sort: string
      /** The matters with a start on its way, from the press until the agent starts or is refused. */
      launching: string[]
      /** Passim's last answer that the account has no research access; null once research answers again. */
      access: Access | null
      /** Whether the BIA Edge connector is in this session, as last looked; null before the first look. */
      library: { connected: boolean } | null
    }
  }
}
