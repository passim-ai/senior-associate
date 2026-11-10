// The research gate (finding 29): case-law and web research never carries the client's details. While Claude works on
// a matter, a BIA Edge call or a web search or fetch made inside its agents is refused when its words hold one of the
// matter's private terms (the server's `privacy_terms`: names, full names and identifiers), with a sentence the agent
// reads and can act on. The terms stay in this module's memory; they are never logged, drawn or written anywhere.
//
// What the host lets this do: `tool.call` and `tool.check` see every call with the loop it runs in (`agentId`), and
// either can refuse it. Three rules, each for the loops it belongs to:
//
// 1. Research, in any agent's loop. A call is tied to its matter by that loop: the app's own agent, or an agent it
//    started (`parentId` in the agent list). A loop the app can't place (an orchestrator started from the chat, another
//    session's helper) is checked against every matter the server says Claude is working on, and passes when Claude
//    is working on none: there is nothing of a client's to keep back.
// 2. A shell command that reaches the network (a URL, curl, ssh), in a matter run's own loops: screened as research
//    is. Every other shell command passes: the steps run the plugin's own scripts, with variables, pipes and line
//    breaks as the skills write them, and a local command carries nothing off the machine.
// 3. Any other tool that could carry words off the machine (another connector, a publishing or messaging tool), in a
//    matter run's own loops: refused. The host's local tools, skills included, always pass.
//
// The attorney's own chat (no `agentId`) is never gated: there, what goes into research is the attorney's call
// (docs/EXPERIENCE.md). Nothing here touches an agent that isn't working on a matter beyond rule 1.
//
// It fails closed where a client's details could leave: when the terms (or the list of matters at work) can't be had,
// research from Claude's agents is refused with a sentence that says so. These are workflow safeguards, not a sandbox:
// only the host's own sandbox enforces a network boundary.
import type { EngineInterface } from 'claude-code'
import type { MatterRow } from '../types'
import { call } from './server'
import { liveAgents, readRuns } from './state'

export const BLOCKED = 'Immigration Packet Builder blocked this: it contained the client’s details. Phrase the research as a legal question, without names, numbers or other facts that identify the client.'
export const UNCHECKED = 'Immigration Packet Builder couldn’t check this research request against the client’s details. Try again in a moment.'
export const SHELL_BLOCKED = 'Immigration Packet Builder blocked this command: it reaches the network and carries the client’s details (a name, a number, or a file named for them). Keep client details out of anything sent off this Mac: fetch public pages by their address alone, and save downloads under a neutral file name.'
export const UNKNOWN_TOOL = 'This tool can send information off this Mac, so it isn’t used during a matter run. Use the local file tools, the plugin’s own scripts, web search or fetch, and the BIA Edge research tools. If the work needs something else, say so in your report and the attorney can do it in chat.'

// The host's own local tools: files, skills, tasks and agents. None of them carries words off the machine.
const LOCAL_TOOLS = new Set([
  'Read', 'Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'Glob', 'Grep', 'LS', 'LSP',
  'TodoWrite', 'Task', 'Agent', 'AskUserQuestion', 'ExitPlanMode', 'EnterPlanMode',
  'Skill', 'ToolSearch', 'ListSkills', 'SearchSkills', 'WaitForMcpServers',
  'TaskCreate', 'TaskGet', 'TaskUpdate', 'TaskList', 'TaskOutput', 'TaskStop', 'GetTask', 'ListAgents', 'SendMessage',
  'BashOutput', 'KillShell', 'KillBash', 'Monitor', 'ScheduleWakeup', 'WrapUp', 'ReportFindings',
])
// The BIA Edge connector's read-only methods, by name: the connector's server may be named anything (an id, say).
const RESEARCH_METHODS = /__(?:search_cases|search_statutes|search_references|search_passages|search_country_conditions|search_unpublished_cases|search_district_court_decisions|get_case_by_citation|get_statute_by_citation|get_reference_by_citation|get_document|get_citations|check_validity|get_regulatory_updates|get_corpus_info|get_research_playbook|get_visa_bulletin|lookup_uscis_form|find_in_statute|find_in_reference|lookup_criminal_code|get_provision_case_law|get_district_docket_outcomes|get_eoir_profile|query_eoir_stats|fetch)$/

// Research: the web tools, and BIA Edge (a server whose name says bia or passim, or one of its methods by name).
export function isResearch(tool: string): boolean {
  if (tool === 'WebSearch' || tool === 'WebFetch') return true
  const m = /^mcp__(.+?)__/.exec(tool)
  return Boolean(m && (/bia|passim/i.test(m[1] ?? '') || RESEARCH_METHODS.test(tool)))
}

// A call the gate looks at: everything but the host's local tools.
export function isScreened(tool: string): boolean { return !LOCAL_TOOLS.has(tool) }

// A shell command that reaches the network: it names an address, or runs a program that connects somewhere. Words
// inside a longer name (a file called "curl-notes.txt") don't count.
const NETWORK_PROGRAMS = /(?:^|[\s;&|(`'"=\/])(?:curl|wget|nc|ncat|netcat|ssh|scp|sftp|ftp|telnet|rsync|mail|mailx|sendmail|osascript|gh)(?=$|[\s;&|)`'"])/
const NETWORK_CODE = /\b(?:urllib|requests\.|httpx|http\.client|smtplib|socket\.|aiohttp|fetch\(|XMLHttpRequest|git\s+(?:push|fetch|pull|clone|remote))/
export function reachesNetwork(command: string): boolean {
  return /\b(?:https?|ftp|sftp|ssh):\/\//i.test(command) || NETWORK_PROGRAMS.test(command) || NETWORK_CODE.test(command)
}
const commandOf = (input: unknown): string => String((input as { command?: unknown })?.command ?? '')

// A matter's private terms, as the server gives them (PAYLOAD.md, privacy_terms): `names` match as whole words in any
// case, `full_names` as whole phrases, `identifiers` with spaces and dashes removed. An older shape (`terms` alone)
// is read the same way: a term with a digit is an identifier, the rest names.
export type Terms = { names: string[]; full_names: string[]; identifiers: string[] }

export function readTerms(res: unknown): Terms {
  const r = (res ?? {}) as Record<string, unknown>
  const list = (x: unknown) => (Array.isArray(x) ? x.filter((t): t is string => typeof t === 'string' && t.trim().length >= 2).map(t => t.trim()) : [])
  const names = list(r.names)
  const full = list(r.full_names)
  const ids = list(r.identifiers)
  if (names.length || full.length || ids.length) return { names, full_names: full, identifiers: ids }
  const all = list(r.terms)
  return { names: all.filter(t => !/\d/.test(t) && !/\s/.test(t)), full_names: all.filter(t => !/\d/.test(t) && /\s/.test(t)), identifiers: all.filter(t => /\d/.test(t)) }
}

// Read current facts for every request; a newly imported identity must not wait for a cache expiry.
async function termsFor($: EngineInterface, matter: string): Promise<Terms> {
  const terms = readTerms(await call($, { op: 'privacy_terms', matter_path: matter, matter }))
  if (!terms.names.length && !terms.full_names.length) throw new Error('No party names available for privacy screening')
  return terms
}

// Accents off, so "García" and "Garcia" are the same word either way round.
const plain = (s: string) => s.normalize('NFD').replace(/\p{M}+/gu, '')
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// Text as a web address carries it ("…/search?q=Jos%C3%A9+N%C3%BA%C3%B1ez"), read as the words it encodes: each run of
// escapes decoded on its own (a stray % never keeps the rest from being read), and + as the space a query means.
export function decoded(text: string): string {
  return text.replace(/\+/g, ' ').replace(/(?:%[0-9A-Fa-f]{2})+/g, run => {
    try {
      return decodeURIComponent(run)
    } catch {
      return run
    }
  })
}

// An identifier as the server's own check compares it (scripts/privacy_terms.py): written with its spaces and dashes
// left out, or digits to digits, digit runs joined across spaces, dots, slashes and dashes. Either way a digit may not
// run on before or after it, so a date of birth "1/2/2020" isn't found in "December 12, 2020".
const MIN_ID_DIGITS = 6
function holdsIdentifier(text: string, id: string): boolean {
  const compact = plain(id).toLowerCase().replace(/[\s-]+/g, '')
  if (compact.length >= 4) {
    const before = /^\d/.test(compact) ? '(?<!\\d)' : ''
    const after = /\d$/.test(compact) ? '(?!\\d)' : ''
    if (new RegExp(`${before}${escape(compact)}${after}`).test(text.toLowerCase().replace(/[\s-]+/g, ''))) return true
  }
  const digits = id.replace(/\D/g, '')
  return digits.length >= MIN_ID_DIGITS && new RegExp(`(?<!\\d)${digits}(?!\\d)`).test(text.replace(/(?<=\d)[\s./-]+(?=\d)/g, ''))
}

// A precedent that happens to share a common surname is a citation, not the client: "Matter of Garcia", "Garcia,
// 16 I&N Dec. 653", "Garcia v. Holder", "Matter of de la Cruz". Those spans are set aside before names are matched. A
// name's words are capitalized, but its small words ("de la", "van der", "y") may not be.
const PARTICLE = "(?:d[aeiou]s?|del|della|la|las|los|le|van|von|der|den|ter|ten|y|e|bin|ibn|al|el) "
const WORD = "\\p{Lu}[\\p{L}'’.-]*"
const NAME = `(?:${PARTICLE})*${WORD}(?:[ -](?:${PARTICLE})*${WORD}){0,3}`
const CITATIONS = [
  new RegExp(`Matter of ${NAME}`, 'gu'),
  new RegExp(`${NAME},? \\d+ I&N Dec\\.`, 'gu'),
  new RegExp(`${NAME} v\\. ${NAME}`, 'gu'),
  new RegExp(`${NAME} v\\.(?= )`, 'gu'),
]
const withoutCitations = (text: string) => CITATIONS.reduce((t, re) => t.replace(re, ' '), text)

// What a tool call carries for the tool itself: tool.call's event holds the tool's arguments beside the call's own
// envelope (the tool's name, the call's id, the loop it runs in), and only the arguments are what goes out.
const ENVELOPE = new Set(['tool', 'tool_use_id', 'agentId', 'consent', 'requestMeta'])
export function toolInput(e: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(e).filter(([key]) => !ENVELOPE.has(key)))
}

// An input that is nothing but citations ("Matter of Garcia, 16 I&N Dec. 653 (BIA 1978)"): what the connector's
// citation lookups are given.
export function onlyCitations(input: unknown): boolean {
  const values = typeof input === 'string' ? [input] : Object.values((input ?? {}) as Record<string, unknown>).filter((v): v is string => typeof v === 'string')
  if (!values.length) return false
  return values.every(v => {
    if (!/\d+\s+(?:I&N Dec\.|F\.\s?(?:2d|3d|4th)|U\.S\.|S\. ?Ct\.)\s*\d+/.test(v)) return false
    const rest = withoutCitations(plain(v)).replace(/\d+\s*(?:I&N Dec\.|F\.\s?\d?d|U\.S\.|S\. ?Ct\.)\s*\d*/g, ' ').replace(/\((?:BIA|AG|A\.G\.|[\w. ]*Cir\.)?[^)]*\d{4}\)/g, ' ')
    return !/\p{L}{3,}/u.test(rest.replace(/\b(?:at|n|id|see|cf)\b/gi, ''))
  })
}

// Does the call's input hold one of the terms, as written or as a web address encodes it?
export function holdsTerm(input: unknown, raw: Terms | string[]): boolean {
  const terms = Array.isArray(raw) ? readTerms({ terms: raw }) : raw
  const written = typeof input === 'string' ? input : JSON.stringify(input ?? '')
  return [...new Set([written, decoded(written)])].some(text => textHolds(plain(text), terms))
}

// A name that is also an everyday word ("May", "Will", "Long", "An", "Do"). Matched whole-word in any case, it would
// refuse nearly every legal question ("the applicant may file", "as long as"). So it counts only as a name is
// written: with a capital, and not as the first word of a sentence. The full name is matched in any case as before.
const EVERYDAY = new Set(`
  a an as at be by do go he hi ho if in is it la le me my no of oh on or so to up us we
  the and for not are but can had has her him his how its may new now old one our out own she too two use was way who why yes you all any day did get got let man men off per put say see set ten try
  will grace hope faith joy rose mark bill frank grant case bond price young king rich long little love page ward hall field lane park court law
  best bell bush cook dean ford hill hunt lord moon moss pope reed rice ross wood wolf west east north south
  able back bear bird blue born boys came come deal dear deep done down each even ever fair fall fast find fine fire fish five four free from full gave give glad gold gone good gray green grew hand hard have head hear held help here high hold home hour hung into iron just keen keep kept kind knew know land last late lead left less life like line live look lord lose loss lost made main make many mean meet mild mind miss more most move much must name near need next nice none noon note once only open over paid part pass past path plan play poor post pure rain read real rest ride ring rise road rock room rule safe said same sand save seal seat seem seen self sell send sent ship shop shot show shut side sign sing size snow soft some song soon sort star stay step stop such sure take talk tall tell term test than that them then they thin this thus time told took town tree true turn upon used very view vote wait walk wall want warm wash wear week well went were what when wide wife wild wind wine wing wise wish with word work year your
`.trim().split(/\s+/))
function holdsEverydayName(text: string, name: string): boolean {
  const written = plain(name).trim()
  const capital = written.charAt(0).toUpperCase() + written.slice(1).toLowerCase()
  const re = new RegExp(`(?<![\\p{L}\\p{N}])${escape(capital)}(?![\\p{L}\\p{N}])`, 'gu')
  for (let m = re.exec(text); m; m = re.exec(text)) {
    const before = text.slice(0, m.index).trimEnd()
    // The first word of the text, of a sentence or of a quoted value takes a capital whatever it is.
    if (before && !/[.!?:;"“”'‘(\[{]$/.test(before)) return true
  }
  return false
}

function textHolds(text: string, terms: Terms): boolean {
  if (hasIdentifier(text)) return true
  if (terms.identifiers.some(t => dateVariants(t).some(v => holdsIdentifier(text, v) || text.toLowerCase().includes(v.toLowerCase())))) return true
  const phrase = (t: string) => new RegExp(`(^|[^\\p{L}\\p{N}])${plain(t).trim().split(/[\s-]+/).map(escape).join('[\\s,.-]+')}($|[^\\p{L}\\p{N}])`, 'iu')
  if (terms.full_names.some(t => phrase(t).test(text))) return true
  const named = withoutCitations(text)
  return terms.names.some(t => (EVERYDAY.has(plain(t).trim().toLowerCase()) ? holdsEverydayName(named, t) : phrase(t).test(named)))
}

export function hasIdentifier(text: string): boolean {
  const plainText = decoded(plain(text))
  return /\bA\s*[-#.]?\s*(?:\d[\s.-]*){7,9}\b/i.test(plainText)
    || /\b(?:EAC|WAC|LIN|SRC|MSC|IOE|NBC|YSC)[\s-]*(?:\d[\s-]*){10}\b/i.test(plainText)
    || /\b\d{3}[- ]\d{2}[- ]\d{4}\b/.test(plainText)
    || /\b\d{9,16}\b/.test(plainText)
    || /\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b/.test(plainText)
    || /\b(?:\d{3}[-. ]|\(\d{3}\)\s*)\d{3}[-. ]\d{4}\b/.test(plainText)
    || /\b(?:date of birth|dob|born)\b.{0,20}\d/i.test(plainText)
    || /\b\d{1,6}\s+[\p{L}0-9 .'-]{1,60}\s+(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Boulevard|Blvd)\b/iu.test(plainText)
}

function dateVariants(id: string): string[] {
  let m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(id)
  let y: string, month: number, day: number
  if (m) { y = m[1]; month = Number(m[2]); day = Number(m[3]) }
  else {
    m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(id)
    if (!m) return [id]
    y = m[3]; month = Number(m[1]); day = Number(m[2])
  }
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December']
  if (month < 1 || month > 12 || day < 1 || day > 31) return [id]
  return [id, `${y}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`, `${month}/${day}/${y}`, `${months[month-1]} ${day}, ${y}`, `${months[month-1]} ${day} ${y}`]
}

// Whose loop a call runs in. `ours`: a matter run's own (the app's agent, one it started, or any of the plugin's own
// agents however they were started); `matters`: the matter it works on when the app knows, else every matter Claude is
// working on right now, as the server reports it. Throws when it can't tell.
type Placed = { ours: boolean; matters: string[] }
// The plugin's own agents, by the type they were started as ("senior-associate:docs-review").
const OUR_AGENT = /senior.?associate/i

async function placeOf($: EngineInterface, agentId: string, needMatters: boolean): Promise<Placed> {
  const runs = await readRuns($)
  const byAgent = (id: string) => Object.values(runs).find(r => r.agentId === id && (r.status === 'running' || r.status === 'starting'))?.matter
  const own = byAgent(agentId)
  if (own) return { ours: true, matters: [own] }
  let ours = false
  try {
    const agents = await $.agent.list()
    let at = agents.find(a => a.id === agentId)
    for (let hops = 0; at && hops < 8; hops++) {
      if (OUR_AGENT.test(at.type)) ours = true
      const parent = at.parentId
      if (!parent) break
      const matter = liveAgents.has(parent) ? byAgent(parent) : undefined
      if (matter) return { ours: true, matters: [matter] }
      at = agents.find(a => a.id === parent)
    }
  } catch {
    // the list isn't available: research is still checked against every matter at work
  }
  if (!needMatters) return { ours, matters: [] }
  const res = (await call($, { op: 'list', include_archived: true })) as unknown as { matters?: MatterRow[] }
  const working = new Set(Object.values(runs).filter(r => r.status === 'running' || r.status === 'starting').map(r => r.matter))
  // A matter Claude is working on, or one an unattended run still holds by the network gate's rule (an orchestrator
  // however it started, quiet for a while, or one the app lost track of): its terms are checked either way.
  for (const m of res.matters ?? []) if (m.phase === 'building' || m.unattended_run) working.add(m.path)
  return { ours, matters: [...working] }
}

// A command with the matters' own folders taken out: where a download is saved isn't sent anywhere.
function withoutFolders(command: string, matters: string[]): string {
  return matters.reduce((text, folder) => (folder ? text.split(folder).join(' ') : text), command)
}

// The refusal for this call, or '' to let it go on.
export async function researchGate($: EngineInterface, tool: string, input: unknown, agentId: string | undefined): Promise<string> {
  if (!agentId || !isScreened(tool)) return ''
  const shell = tool === 'Bash'
  const research = isResearch(tool)
  // A local shell command carries nothing off the machine, whoever runs it.
  if (shell && !reachesNetwork(commandOf(input))) return ''
  let place: Placed
  try {
    // Research is checked whoever asks, so it needs the matters at work; the rest first needs to know whose loop it is.
    place = await placeOf($, agentId, research)
    if (!shell && !research) return place.ours ? UNKNOWN_TOOL : ''
    // A shell command that reaches the network matters only in a matter run's own loops.
    if (shell && !place.ours) return ''
    if (shell && !place.matters.length) place = await placeOf($, agentId, true)
  } catch {
    return UNCHECKED
  }
  if (!place.matters.length) return place.ours ? UNCHECKED : ''
  try {
    const sent = shell ? withoutFolders(commandOf(input), place.matters) : input
    for (const matter of place.matters) {
      if (holdsTerm(sent, await termsFor($, matter))) return shell ? SHELL_BLOCKED : BLOCKED
    }
  } catch {
    return UNCHECKED
  }
  return ''
}

// A hot reload, or a new session: the terms are asked for again.
export function forgetTerms() {
  // Terms are not retained between calls.
}
