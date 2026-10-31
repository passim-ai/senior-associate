// The research gate (finding 29): case-law and web research never carries the client's details. While Claude works on
// a matter, a BIA Edge call or a web search or fetch made inside its agents is refused when its words hold one of the
// matter's private terms (the server's `privacy_terms`: names, full names and identifiers), with a sentence the agent
// reads and can act on. The terms stay in this module's memory; they are never logged, drawn or written anywhere.
//
// What the host lets this do: `tool.call` and `tool.check` see every call with the loop it runs in (`agentId`), and
// either can refuse it. A call is tied to its matter by that loop: the app's own agent, or an agent it started
// (`parentId` in the agent list). A loop the app can't place (an orchestrator started from the chat, before /matters
// was ever opened) is checked against every matter the server says Claude is working on. The attorney's own chat (no
// `agentId`) is never gated: there, what goes into research is the attorney's call (docs/EXPERIENCE.md).
//
// It fails closed: when the terms (or the list of matters at work) can't be had, research from Claude's agents is
// refused with a sentence that says so, rather than let a client's details out unchecked.
import type { EngineInterface } from 'claude-code'
import type { MatterRow } from '../types'
import { call } from './server'
import { liveAgents, readRuns } from './state'
import { nowMs } from './words'

export const BLOCKED = 'Senior Associate blocked this: it contained the client’s details. Phrase the research as a legal question, without names, numbers or other facts that identify the client.'
export const UNCHECKED = 'Senior Associate couldn’t check this research request against the client’s details. Try again in a moment.'

// BIA Edge (any MCP server whose name says bia or passim) and the web tools.
export function isResearch(tool: string): boolean {
  if (tool === 'WebSearch' || tool === 'WebFetch') return true
  const m = /^mcp__(.+?)__/.exec(tool)
  return Boolean(m && /bia|passim/i.test(m[1] ?? ''))
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

// Only terms that were actually had are kept, for five minutes: a failure or an empty answer is asked again next time.
const TERMS_MS = 5 * 60000
const cache = new Map<string, { at: number; terms: Terms }>()

async function termsFor($: EngineInterface, matter: string): Promise<Terms> {
  const hit = cache.get(matter)
  if (hit && nowMs() - hit.at < TERMS_MS) return hit.terms
  const terms = readTerms(await call($, { op: 'privacy_terms', matter_path: matter, matter }))
  if (terms.names.length || terms.full_names.length || terms.identifiers.length) cache.set(matter, { at: nowMs(), terms })
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

function textHolds(text: string, terms: Terms): boolean {
  if (terms.identifiers.some(t => holdsIdentifier(text, t))) return true
  const phrase = (t: string) => new RegExp(`(^|[^\\p{L}\\p{N}])${plain(t).trim().split(/[\s-]+/).map(escape).join('[\\s,.-]+')}($|[^\\p{L}\\p{N}])`, 'iu')
  if (terms.full_names.some(t => phrase(t).test(text))) return true
  const named = withoutCitations(text)
  return terms.names.some(t => phrase(t).test(named))
}

// The matters a loop's calls belong to: its own run's, an ancestor's run's, or every matter Claude is working on as
// the server reports it right now. Throws when it can't tell.
async function mattersFor($: EngineInterface, agentId: string): Promise<string[]> {
  const runs = await readRuns($)
  const byAgent = (id: string) => Object.values(runs).find(r => r.agentId === id && (r.status === 'running' || r.status === 'starting'))?.matter
  const own = byAgent(agentId)
  if (own) return [own]
  try {
    const agents = await $.agent.list()
    let at = agents.find(a => a.id === agentId)
    for (let hops = 0; at?.parentId && hops < 8; hops++) {
      const matter = liveAgents.has(at.parentId) ? byAgent(at.parentId) : undefined
      if (matter) return [matter]
      const parent = at.parentId
      at = agents.find(a => a.id === parent)
    }
  } catch {
    // the list isn't available: check against every matter at work
  }
  const res = (await call($, { op: 'list', include_archived: true })) as unknown as { matters?: MatterRow[] }
  const working = new Set(Object.values(runs).filter(r => r.status === 'running' || r.status === 'starting').map(r => r.matter))
  // A matter Claude is working on, or one an unattended run still holds by the network gate's rule (an orchestrator
  // however it started, quiet for a while, or one the app lost track of): its terms are checked either way.
  for (const m of res.matters ?? []) if (m.phase === 'building' || m.unattended_run) working.add(m.path)
  return [...working]
}

// The refusal for this call, or '' to let it go on.
export async function researchGate($: EngineInterface, tool: string, input: unknown, agentId: string | undefined): Promise<string> {
  if (!agentId || !isResearch(tool)) return ''
  if (/citation|validity/i.test(tool) && onlyCitations(input)) return ''
  try {
    for (const matter of await mattersFor($, agentId)) {
      if (holdsTerm(input, await termsFor($, matter))) return BLOCKED
    }
  } catch {
    return UNCHECKED
  }
  return ''
}

// A hot reload, or a new session: the terms are asked for again.
export function forgetTerms() {
  cache.clear()
}
