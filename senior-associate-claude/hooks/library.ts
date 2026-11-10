// BIA Edge and the Passim account behind it: what the connector said when the account had no research access.
//
// Passim answers a research call from an account without access with an error, in its own words: what happened (a
// free trial that ended, no plan chosen, a payment that failed), the sentence "No Passim research results were
// returned for this request.", and a link to the account. A build that meets it goes on without case-law research,
// so the app keeps Passim's words and says them on the Setup screen and the matter's page, with the way to the
// account. The next call that comes back with results clears it. Nothing here reads a result with research in it.
import type { EngineInterface } from 'claude-code'
import { readAccess, setAccess } from './state'
import { nowIso } from './words'

const NO_RESULTS = 'No Passim research results were returned for this request.'
const LISTING = /\s*In Claude, Passim is listed as BIA Edge\./
const LEAD = /^(?:Error|MCP error[^:]*|Tool error):\s*/i
const MESSAGE_MAX = 400

// Passim's answer, read: its own words, and whether choosing a plan resolves it (its link opens the plans) or the
// account needs looking at. Null for anything else, and for "could not verify account access", which carries no link:
// that is a moment's fault, not the account's state.
export function denialOf(text: string): { message: string; plan: boolean } | null {
  const at = text.indexOf(NO_RESULTS)
  if (at < 0) return null
  const link = /\]\((https:\/\/[^)\s]+)\)/.exec(text.slice(at))
  if (!link) return null
  const message = text.slice(0, at).replace(LISTING, '').replace(/\s+/g, ' ').trim().replace(LEAD, '')
  if (!message) return null
  return { message: message.length > MESSAGE_MAX ? `${message.slice(0, MESSAGE_MAX - 1)}…` : message, plan: /\/billing\/start\b/.test(link[1] ?? '') }
}

// The connector a tool belongs to: "mcp__<server>".
const serverOf = (tool: string) => tool.split('__').slice(0, 2).join('__')
// BIA Edge by its own methods, whatever its connector's server is named now (it may have been added again).
const ITS_METHODS = /__(?:check_validity|get_case_by_citation|search_cases|get_regulatory_updates|search_unpublished_cases)$/

// After a connector's tool has answered: keep Passim's no-access answer, or clear it once research answers again.
export async function noteAccess($: EngineInterface, tool: string, result: unknown): Promise<void> {
  if (!tool.startsWith('mcp__')) return
  const r = (result ?? {}) as { isError?: unknown; text?: unknown; deny?: unknown }
  if (r.deny !== undefined) return
  if (r.isError === true) {
    const denied = typeof r.text === 'string' ? denialOf(r.text) : null
    if (denied) await setAccess($, { ...denied, at: await nowIso($), server: serverOf(tool) })
    return
  }
  const kept = await readAccess($)
  if (kept && (kept.server === serverOf(tool) || ITS_METHODS.test(tool))) await setAccess($, null)
}
