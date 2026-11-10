// The research gate (finding 29): case-law and web research never carries the client's details. While Claude works on
// a matter, a BIA Edge call or a web search or fetch made inside its agents is refused when its words hold one of the
// matter's private terms (the server's `privacy_terms`: names, full names and identifiers), with a sentence the agent
// reads and can act on. The terms stay in this module's memory; they are never logged, drawn or written anywhere.
//
// What the host lets this do: `tool.call` and `tool.check` see every call with the loop it runs in (`agentId`), and
// either can refuse it. Four rules, each for the loops it belongs to:
//
// 1. Research, in any agent's loop. A call is tied to its matter by that loop: the app's own agent, or an agent it
//    started (`parentId` in the agent list). A loop the app can't place (an orchestrator started from the chat, another
//    session's helper) is checked against every matter the server says Claude is working on, and passes when Claude
//    is working on none: there is nothing of a client's to keep back.
// 2. A shell command that reaches the network (a URL, curl, ssh), and the app's built-in browser, in a matter run's
//    own loops: screened as research is. A command that sends a file or piped text, or writes the matter's folder
//    into an address or a request, is refused: what a file holds can't be read here. Every other shell command
//    passes: the steps run the plugin's own scripts, with variables, pipes and line breaks as the skills write them,
//    and a local command carries nothing off the machine.
// 3. Any other tool that sends what it is given somewhere else (another connector, or one of the host's tools that
//    publishes, schedules or hands off), in a matter run's own loops: refused.
// 4. Every other tool of the host's passes, whatever it is called: files, skills, tasks, agents, an agent's report
//    to the one that started it, the desktop app's own controls. The host adds tools with each release, and a matter
//    run that can't hand its report back does no work at all, so what is refused is named and the rest is let be.
//
// The attorney's own chat (no `agentId`) is never gated: there, what goes into research is the attorney's call
// (docs/EXPERIENCE.md). Nothing here touches an agent that isn't working on a matter beyond rule 1.
//
// It fails closed where a client's details could leave: when the matters at work or their terms can't be read,
// research from Claude's agents and a matter run's own outbound calls are refused with a sentence that says so. A
// matter with no name on record yet (the folder is named by a file number, and nothing has been read) is not that:
// its calls are still checked for anything shaped like an identifier. These are workflow safeguards, not a sandbox:
// only the host's own sandbox enforces a network boundary.
import type { EngineInterface } from 'claude-code'
import type { MatterRow } from '../types'
import { call } from './server'
import { liveAgents, readRuns } from './state'

export const BLOCKED = 'Immigration Packet Builder blocked this: it contained the client’s details. Phrase the research as a legal question, without names, numbers or other facts that identify the client.'
export const UNCHECKED = 'Immigration Packet Builder couldn’t check this research request against the client’s details. Try again in a moment.'
export const SHELL_BLOCKED = 'Immigration Packet Builder blocked this command: it reaches the network and carries the client’s details (a name, a number, or a file named for them). Keep client details out of anything sent off this Mac: fetch public pages by their address alone, and save downloads under a neutral file name.'
export const UPLOAD_BLOCKED = 'Immigration Packet Builder blocked this command: it sends a file or piped text off this Mac, and what is in it can’t be checked for the client’s details. Work on the client’s files with the local tools, and fetch public pages by their address alone.'
export const UNKNOWN_TOOL = 'This tool can send information off this Mac, so it isn’t used during a matter run. Use the local file tools, the plugin’s own scripts, web search or fetch, and the BIA Edge research tools. If the work needs something else, say so in your report and the attorney can do it in chat.'

// The host's own tools that publish what they are given, hand it to another service, or act outside this session:
// artifacts and designs, projects, scheduled and remote runs, feedback, control of the computer. Every other tool of
// the host's is local, whatever it is called (rule 4): this list names what is refused, never what is allowed.
const OUTBOUND_BUILTINS = new Set([
  'Artifact', 'ArtifactCheck', 'ArtifactComments', 'ArtifactData', 'AppifactRepl', 'ClaudeDesign', 'DesignSync',
  'Projects', 'SendToProject', 'SendToProjectContext', 'SendFile', 'SendFeedback', 'ShareOnboardingGuide',
  'PublishPlugin', 'RemoteTrigger', 'CronCreate', 'request_computer',
])
// The desktop app's own controls (its task list, chapters, panes): local, though named the way a connector's are.
const HOST_APP = /^mcp__ccd_/
// The app's built-in browser. It sends what it is given (an address, typed text, a script), so it is screened as
// research is. The attorney's own Chrome, with its signed-in sites, is a connector like any other.
const BROWSER = /^mcp__Claude_Browser__/
// The BIA Edge connector's read-only methods, by name: the connector's server may be named anything (an id, say).
const RESEARCH_METHODS = /__(?:search_cases|search_statutes|search_references|search_passages|search_country_conditions|search_unpublished_cases|search_district_court_decisions|get_case_by_citation|get_statute_by_citation|get_reference_by_citation|get_document|get_citations|check_validity|get_regulatory_updates|get_corpus_info|get_research_playbook|get_visa_bulletin|lookup_uscis_form|find_in_statute|find_in_reference|lookup_criminal_code|get_provision_case_law|get_district_docket_outcomes|get_eoir_profile|query_eoir_stats|fetch)$/

// Research: the web tools, and BIA Edge (a server whose name says bia or passim, or one of its methods by name).
export function isResearch(tool: string): boolean {
  if (tool === 'WebSearch' || tool === 'WebFetch') return true
  const m = /^mcp__(.+?)__/.exec(tool)
  return Boolean(m && (/bia|passim/i.test(m[1] ?? '') || RESEARCH_METHODS.test(tool)))
}

export function isBrowser(tool: string): boolean { return BROWSER.test(tool) }

// A tool that sends what it is given somewhere else: a connector that isn't research, or one of the host's outbound
// tools. A matter run's agents don't use these at all.
export function isOutbound(tool: string): boolean {
  if (isResearch(tool) || isBrowser(tool) || HOST_APP.test(tool)) return false
  return tool.startsWith('mcp__') || OUTBOUND_BUILTINS.has(tool)
}

// A call the gate looks at: the shell, research, the browser and the outbound tools. Everything else is local.
export function isScreened(tool: string): boolean {
  return tool === 'Bash' || isResearch(tool) || isBrowser(tool) || isOutbound(tool)
}

// ---------- reading a shell command ----------
// A command reaches the network when it names an address or a program that connects, or holds code that does,
// anywhere in what it runs. That is read broadly on purpose: a word that looks like a command may be one (inside
// `bash -c "…"`, `$(…)`, a here-document fed to a shell or to Python), and reading too much only means a command is
// screened that didn't need to be. One thing is left out, because it is neither run nor sent: text a command only
// writes down. A memo written with `cat > memo.md <<'EOF' … filed by mail … EOF` runs cat, and a table of sources
// written into a Python file is a list of addresses nobody is fetching.
const NETWORK_PROGRAMS = /(?:^|[\s;&|(`'"=\/])(?:curl|wget|nc|ncat|netcat|ssh|sftp|ftp|telnet|mail|mailx|sendmail|osascript|gh)(?=$|[\s;&|)`'"])/
const NETWORK_CODE = /\b(?:urllib|requests\.|httpx|http\.client|smtplib|socket\.|aiohttp|fetch\(|XMLHttpRequest|git\s+(?:push|fetch|pull|clone|remote))/
const ADDRESS = /\b(?:https?|ftp|sftp|ssh):\/\//i
// rsync and scp copy between folders on this Mac as readily as to another machine. They reach the network only when
// an endpoint names a host ("host:path", "user@host:", "rsync://") or a remote shell is asked for.
const COPIER = /(?:^|[;&|(`]\s*|\$\(\s*|\b(?:sudo|exec|time|xargs)\s+)(?:rsync|scp)\s([^;&|\n]*)/g
const REMOTE_END = /(?:^|\s)["']?(?:[A-Za-z0-9_.-]+@)?[A-Za-z0-9_.-]+:(?!\\)\S*|rsync:\/\/|(?:^|\s)(?:-e|--rsh)(?:=|\s)/
export function copiesAway(command: string): boolean {
  for (const m of command.matchAll(COPIER)) if (REMOTE_END.test(m[1] ?? '')) return true
  return false
}

// A line's pieces, each a program and its words, with what joined it to the one before: cut at `;`, `|`, `||`, `&&`,
// `&` and line ends that stand outside quotes.
type Piece = { text: string; joined: string }
export function shellPieces(text: string): Piece[] {
  const out: Piece[] = []
  let cur = ''
  let quote = ''
  let joined = ''
  const cut = (next: string) => {
    if (cur.trim()) out.push({ text: cur, joined })
    cur = ''
    joined = next
  }
  for (let i = 0; i < text.length; i++) {
    const ch = text[i] ?? ''
    if (quote) {
      cur += ch
      if (ch === '\\' && quote === '"' && i + 1 < text.length) cur += text[++i] ?? ''
      else if (ch === quote) quote = ''
    } else if (ch === '\\' && i + 1 < text.length) {
      cur += ch + (text[++i] ?? '') // an escaped character, a line that goes on
    } else if (ch === '"' || ch === "'") {
      quote = ch
      cur += ch
    } else if (ch === ';' || ch === '\n') {
      cut(ch)
    } else if (ch === '|' || ch === '&') {
      const twice = text[i + 1] === ch
      if (twice) i++
      cut(twice ? ch + ch : ch)
    } else cur += ch
  }
  cut('')
  return out
}
export const shellParts = (text: string): string[] => shellPieces(text).map(piece => piece.text)

// The program a piece runs: past any assignments (X=1 cat …), wrappers (sudo, env) and the shell's own words (then,
// do), and without its folder (/bin/cat).
const LEAD = /^(?:(?:[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S*)|sudo|exec|time|nohup|command|env|then|do|else|elif|if|while|until)\s+)*/
// One assignment after another, with space between: a value is never cut in two to find a second one, which on a
// long address full of "=" would take a very long time to give up on.
const ONLY_ASSIGNS = /^\s*(?:(?:export|local|declare|readonly)\s+)?[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S*)(?:\s+[A-Za-z_][A-Za-z0-9_]*=(?:"[^"]*"|'[^']*'|\S*))*\s*$/
export function programOf(piece: string): string {
  if (ONLY_ASSIGNS.test(piece)) return ''
  const rest = piece.trimStart().replace(LEAD, '')
  const word = /^(?:"([^"]+)"|'([^']+)'|(\S+))/.exec(rest)
  return ((word?.[1] ?? word?.[2] ?? word?.[3] ?? '').split('/').pop() ?? '')
}

// Programs that only write down or pass along the text they are given.
const WRITERS = new Set(['cat', 'tee', 'sed', 'grep', 'head', 'tail', 'wc', 'sort', 'uniq', 'cut', 'tr', 'jq', 'fold', 'fmt', 'nl', 'paste', 'column', 'tac', 'rev', 'base64', 'xxd', 'od', 'md5', 'shasum', 'pbcopy'])

// A command without the text it only writes down: the body of a here-document fed to one of those programs, with
// nothing but such programs after it in its pipeline (a pipe into Python or a shell would run it or send it on), not
// inside a group or a substitution whose output goes somewhere else, and with nothing in it for the shell to run: its
// tag is quoted, or it holds no `$(…)` and no backtick. Every other here-document stays in the command as written:
// one fed to a shell is commands, one fed to Python is code, one fed to curl is what curl sends.
const HEREDOC = /<<-?[ \t]*(["']?)([A-Za-z_][A-Za-z0-9_]*)\1([^\n]*)\n([\s\S]*?)\n[ \t]*\2[ \t]*(?=\n|$)/g
export function withoutWrittenText(command: string): string {
  return command.replace(HEREDOC, (all: string, quoted: string, _tag: string, rest: string, body: string, at: number) => {
    const line = command.slice(command.lastIndexOf('\n', at - 1) + 1, at)
    const fed = shellParts(line).pop() ?? ''
    if (!WRITERS.has(programOf(fed)) || /[({`]|\$\(|\/dev\/(?:tcp|udp)\//.test(fed + rest)) return all
    if (!quoted && /\$\(|`/.test(body)) return all
    // What the text is piped into, up to the end of its pipeline.
    const after = shellPieces(rest)
    const consumers: string[] = []
    for (let i = 0; i < after.length; i++) {
      const piece = after[i]
      if (!piece) continue
      const own = i === 0 && !/^\s*[;|&]/.test(rest) // the rest of the fed program's own words ("> memo.md")
      if (own) continue
      if (piece.joined !== '|') break
      consumers.push(piece.text)
    }
    return consumers.every(piece => WRITERS.has(programOf(piece))) ? ` ${rest}` : all
  })
}

export function reachesNetwork(command: string): boolean {
  const read = withoutWrittenText(command)
  return ADDRESS.test(read) || NETWORK_PROGRAMS.test(read) || NETWORK_CODE.test(read) || copiesAway(read)
}
const commandOf = (input: unknown): string => String((input as { command?: unknown })?.command ?? '')

// A command with its own simple assignments written out (M="/matters/Garcia"; … "$M/passport.pdf"), so a path kept in
// a variable is read where it is used. Only for reading the command: nothing is run, and what the shell would work
// out for itself ($PWD, a command's output) stays as written.
export function spelledOut(command: string): string {
  const values = new Map<string, string>()
  const assign = /(?:^|[;&\n]\s*|\bexport\s+)([A-Za-z_][A-Za-z0-9_]*)=(?:"([^"\n]*)"|'([^'\n]*)'|([^\s;&|]*))/g
  for (let m = assign.exec(command); m; m = assign.exec(command)) values.set(m[1] ?? '', m[2] ?? m[3] ?? m[4] ?? '')
  if (!values.size) return command
  let out = command
  for (let pass = 0; pass < 3; pass++) {
    out = out.replace(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)/g, (all: string, a?: string, b?: string) => values.get(a ?? b ?? '') ?? all)
  }
  return out
}

// A command that sends a file or piped text: a copy program, a transfer program's upload option or a file given as
// its request's data, a pipe or a file fed into a program that connects. What the file holds can't be read here.
// The options are read only in a transfer program's own part of the command: `awk -F '@'` and `unzip -d` are local.
const COPY_OUT = /(?:^|[;&|(`]\s*|\$\(\s*|\b(?:sudo|exec|time|xargs)\s+)(?:sftp|ftp|nc|ncat|netcat|telnet|mail|mailx|sendmail)(?=$|[\s;&|)`])/
const TRANSFERS = /^[\s'"(]*(?:(?:bash|sh|zsh)\s+-[a-z]*c\s+['"]?\s*)?(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:(?:sudo|exec|time|env)\s+)?(?:curl|wget|http|https|xh)(?=\s|$)/
const UPLOAD_OPTION = /\s(?:-T|--upload-file|--post-file|--body-file)(?:=|\s)/
const FILE_AS_DATA = /\s(?:-d|--data(?:-binary|-ascii|-urlencode)?|--json|-F|--form)(?:=|\s+)["']?(?:[^\s"'@<=]*=)?[@<]/
// One pipe, not the "or" of two: `[ -f page.html ] || curl …` pipes nothing into curl.
const PIPED_OUT = /(?<!\|)\|(?!\|)\s*(?:sudo\s+)?(?:curl|wget|nc|ncat|netcat|ssh|mail|mailx|sendmail)(?=$|[\s;&|)`])/
const FED_A_FILE = /(?:^|[\s;&|(`])(?:curl|wget|ssh)\s[^|;&\n]*(?<!<)<(?!<)\s*[^\s<(&]/
// Read every way a part could begin: a quoted argument is not kept whole, so `bash -c 'cd /tmp; curl -T x …'` is
// seen for the upload it is.
const parts = (command: string): string[] => command.split(/[;|&\n]+|\$\(|`|[<>]\(/)
export function sendsFile(command: string): boolean {
  const read = withoutWrittenText(command)
  if (COPY_OUT.test(read) || copiesAway(read) || PIPED_OUT.test(read) || FED_A_FILE.test(read)) return true
  return parts(read).some(part => TRANSFERS.test(part) && (UPLOAD_OPTION.test(part) || FILE_AS_DATA.test(part)))
}

// The matter's own folder written where it is sent, not where a download is saved: inside an address, or in what a
// transfer program's request carries (its data, a header). The folder's name is the client's.
const IN_ADDRESS = /(?:https?|ftp|sftp):\/\/[^\s"']*$/i
const IN_REQUEST = /\s(?:-d|--data(?:-[a-z]+)?|--json|-F|--form(?:-string)?|--url-query|--post-data|--body-data|-H|--header|-A|--user-agent|-e|--referer|-b|--cookie)(?:=|\s+)(?:"[^"]*|'[^']*|[^"'\s]*)$/
export function carriesFolder(command: string, folders: string[]): boolean {
  for (const folder of folders) {
    if (!folder) continue
    for (let at = command.indexOf(folder); at >= 0; at = command.indexOf(folder, at + folder.length)) {
      const before = command.slice(0, at)
      if (IN_ADDRESS.test(before)) return true
      const part = parts(before).pop() ?? ''
      if (TRANSFERS.test(part) && IN_REQUEST.test(part)) return true
    }
  }
  return false
}

// What the built-in browser is given to send: an address, typed text, a value, a script. A tab's id or a place on
// the screen is not that, and a long number among them is no identifier.
const BROWSER_SENDS = new Set(['url', 'text', 'value', 'query', 'prompt'])
export function browserSends(input: unknown): string[] {
  const out: string[] = []
  const walk = (value: unknown, key: string, depth: number) => {
    if (depth > 6 || value == null) return
    if (typeof value === 'string') {
      if (BROWSER_SENDS.has(key)) out.push(value)
    } else if (Array.isArray(value)) {
      for (const item of value) walk(item, key, depth + 1)
    } else if (typeof value === 'object') {
      for (const [k, v] of Object.entries(value as Record<string, unknown>)) walk(v, k, depth + 1)
    }
  }
  walk(input, '', 0)
  return out
}

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

// Read current facts for every request; a newly imported identity must not wait for a cache expiry. A matter with no
// name on record yet (its folder is named by a file number, and nothing has been read) gives no names: its calls are
// still checked for anything shaped like an identifier, and by name as soon as one is recorded. Throws only when the
// server can't be asked.
async function termsFor($: EngineInterface, matter: string): Promise<Terms> {
  return readTerms(await call($, { op: 'privacy_terms', matter_path: matter, matter }))
}
const NO_TERMS: Terms = { names: [], full_names: [], identifiers: [] }

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
// agents however they were started); null when the host can't say what the agent is. `matter`: the matter it works
// on, when the app knows.
type Whose = { ours: boolean | null; matter?: string }
// The plugin's own agents, by the type they were started as ("senior-associate:docs-review").
const OUR_AGENT = /senior.?associate/i

async function whose($: EngineInterface, agentId: string): Promise<Whose> {
  const runs = await readRuns($)
  const byAgent = (id: string) => Object.values(runs).find(r => r.agentId === id && (r.status === 'running' || r.status === 'starting'))?.matter
  const own = byAgent(agentId)
  if (own) return { ours: true, matter: own }
  let agents: Awaited<ReturnType<typeof $.agent.list>>
  try {
    agents = await $.agent.list()
  } catch {
    return { ours: null }
  }
  let ours = false
  let at = agents.find(a => a.id === agentId)
  for (let hops = 0; at && hops < 8; hops++) {
    if (OUR_AGENT.test(at.type)) ours = true
    const parent = at.parentId
    if (!parent) break
    const matter = liveAgents.has(parent) ? byAgent(parent) : undefined
    if (matter) return { ours: true, matter }
    at = agents.find(a => a.id === parent)
  }
  return { ours }
}

// Every matter Claude is working on right now: the app's own runs, and what the server reports. Throws when the
// server can't be asked.
async function mattersAtWork($: EngineInterface): Promise<string[]> {
  const runs = await readRuns($)
  const res = (await call($, { op: 'list', include_archived: true })) as unknown as { matters?: MatterRow[] }
  const working = new Set(Object.values(runs).filter(r => r.status === 'running' || r.status === 'starting').map(r => r.matter))
  // A matter Claude is working on, or one an unattended run still holds by the network gate's rule (an orchestrator
  // however it started, quiet for a while, or one the app lost track of): its terms are checked either way.
  for (const m of res.matters ?? []) if (m.phase === 'building' || m.unattended_run) working.add(m.path)
  return [...working]
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
  const browser = isBrowser(tool)
  const command = shell ? spelledOut(commandOf(input)) : ''
  // A local shell command carries nothing off the machine, whoever runs it.
  if (shell && !reachesNetwork(command)) return ''
  let who: Whose
  try {
    who = await whose($, agentId)
  } catch {
    who = { ours: null }
  }
  // Everything but research is a matter run's own concern: another agent's tools and commands are let be.
  if (!research && who.ours === false) return ''
  // An outbound tool has no place in a matter run, and a file's contents can't be read on their way out.
  if (who.ours && !shell && !research && !browser) return UNKNOWN_TOOL
  if (who.ours && shell && sendsFile(command)) return UPLOAD_BLOCKED
  const refusal = shell ? SHELL_BLOCKED : research || browser ? BLOCKED : UNKNOWN_TOOL
  try {
    const matters = who.matter ? [who.matter] : await mattersAtWork($)
    // What a command may send: all of it but the text it only writes down.
    const read = shell ? withoutWrittenText(command) : ''
    if (shell && carriesFolder(read, matters)) return SHELL_BLOCKED
    const sent = shell ? withoutFolders(read, matters) : browser ? browserSends(input) : input
    // No matter at work that anyone knows of. One of the plugin's own agents may still hold a client's file (started
    // by hand, outside a run), so what it sends is checked for anything shaped like an identifier; anyone else has
    // nothing of a client's to keep back.
    if (!matters.length) return who.ours && holdsTerm(sent, NO_TERMS) ? refusal : ''
    for (const matter of matters) {
      if (holdsTerm(sent, await termsFor($, matter))) return refusal
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
