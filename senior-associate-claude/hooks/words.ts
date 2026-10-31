// Words and times as the attorney reads them: plain sentences, never a raw error.
import type { EngineInterface } from 'claude-code'

// ---------- time ----------

export const time = { now: 0 } // the host's clock at the last look
// The host's clock, so a test can move time; the machine's when the host has none.
export async function clockNow($: EngineInterface): Promise<number> {
  try {
    time.now = await $.clock.now()
  } catch {
    time.now = Date.now()
  }
  return time.now
}
export async function nowIso($: EngineInterface): Promise<string> {
  return new Date(await clockNow($)).toISOString()
}
export const nowMs = () => time.now || Date.now()

// ---------- words ----------

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`
}

// "Forms review, Cover letter and Research".
export function andList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? ''
  return `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`
}

// "maria garcia" → "Maria Garcia": the first letter of each word, the rest as typed.
// The small words of a family name stay as typed, except at the very start: "maria de la cruz" → "Maria de la Cruz",
// "ana dos santos", "jan van der berg", "omar bin laden" → "Omar bin Laden", "ana y lópez".
const PARTICLES = new Set(['de', 'del', 'della', 'der', 'den', 'des', 'di', 'da', 'das', 'do', 'dos', 'du', 'la', 'le', 'las', 'los', 'van', 'von', 'zu', 'bin', 'binti', 'ibn', 'al', 'el', 'y', 'e', 'ter', 'ten', 'op', 'af'])
export function capitalizeWords(s: string): string {
  let first = true
  return s.replace(/(^|\s)(\S+)/gu, (_m, space: string, word: string) => {
    const keep = !first && PARTICLES.has(word.toLowerCase())
    first = false
    return space + (keep ? word : word.replace(/^\p{Ll}/u, ch => ch.toUpperCase()))
  })
}

// The first sentence(s) of a text, cut at a sentence end within `max` characters, ids and paths left out.
export function brief(text: string, max = 300): string {
  const clean = text
    .replace(/\s*\((?:open item|item|finding|see)?\s*`?[\w./-]+(?:\.json|\.md|\.pdf)`?\)/gi, '')
    .replace(/`[^`]*\/[^`]*`/g, '')
    .replace(/\s+/g, ' ')
    .trim()
  if (clean.length <= max) return clean
  const cut = clean.slice(0, max)
  const end = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('? '), cut.lastIndexOf('! '))
  return end > 40 ? cut.slice(0, end + 1) : `${cut.slice(0, cut.lastIndexOf(' '))}…`
}

// A clock time: "2:14 PM".
export function clock(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

// "22 min", "1 h 15 min".
export function duration(ms: number): string {
  const minutes = Math.max(0, Math.round(ms / 60000))
  if (minutes < 1) return 'under a minute'
  if (minutes < 60) return `${minutes} min`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return m ? `${h} h ${m} min` : `${h} h`
}

// How long ago, for a list: "just now", "12 min ago", "3 h ago", "yesterday", "Oct 27".
export function when(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const now = new Date(nowMs())
  const minutes = Math.round((now.getTime() - d.getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  if (d.toDateString() === now.toDateString()) return `${Math.floor(minutes / 60)} h ago`
  const yesterday = new Date(now.getTime() - 86400000)
  if (d.toDateString() === yesterday.toDateString()) return 'yesterday'
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

// The same, inside a sentence: "2 hours ago", "yesterday", "on Oct 27".
export function whenPhrase(iso: string): string {
  const w = when(iso)
  if (!w) return 'a while ago'
  if (/^\d+ h ago$/.test(w)) return plural(Number(w.split(' ')[0]), 'hour ago', 'hours ago')
  if (/^\d+ min ago$/.test(w)) return plural(Number(w.split(' ')[0]), 'minute ago', 'minutes ago')
  if (w === 'just now' || w === 'yesterday') return w
  return `on ${w}`
}

export function dateOnly(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })
}

// The client request as plain text, for an email: headings become plain lines, bold and code marks go.
export function plainText(md: string): string {
  return md
    .replace(/\r\n/g, '\n')
    .replace(/^[ \t]{0,3}#{1,6}[ \t]+(.*?)[ \t]*#*[ \t]*$/gm, '$1')
    .replace(/^[ \t]{0,3}(?:-{3,}|\*{3,}|_{3,})[ \t]*$/gm, '')
    .replace(/^[ \t]{0,3}>[ \t]?/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/__(.+?)__/g, '$1')
    .replace(/(^|[\s(])\*(\S(?:.*?\S)?)\*(?=[\s).,;:!?]|$)/gm, '$1$2')
    .replace(/(^|[\s(])_(\S(?:.*?\S)?)_(?=[\s).,;:!?]|$)/gm, '$1$2')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!?\[([^\]]+)\]\(([^)]+)\)/g, (_m, text: string, url: string) => (text === url ? url : `${text} (${url})`))
    .replace(/^([ \t]*)[*+][ \t]+/gm, '$1- ')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

// Claude changes plugin options for the attorney (its setup skill), so a message about another Matters folder carries
// the request that has Claude do it.
export const MATTERS_ASK = 'Change my Immigration Packet Builder Matters folder.'
export const NEW_FOLDER = 'Claude can set up a different Matters folder for you.'
export const UV_ASK = 'Install uv for Immigration Packet Builder.'
export const UPDATE_ASK = 'Update Immigration Packet Builder to the newest version.'

// The server words its own errors (server/sa_server/errors.py). What can still arrive raw is the host's or a process's
// own message when the server couldn't run at all: a permission refused, a timeout.
const FRIENDLY: [RegExp, string][] = [
  [/permission ?error|permission denied|EACCES|operation not permitted|read-only file system/i, `Immigration Packet Builder can’t save in your Matters folder. ${NEW_FOLDER}`],
  [/timed? ?out|ETIMEDOUT/i, 'That took too long and was stopped. Try again.'],
]

// Anything the server didn't already phrase as a sentence becomes one.
export function friendly(raw: string): string {
  const text = raw.trim()
  if (!text) return 'That didn’t work, and nothing was changed. Try again.'
  for (const [pattern, say] of FRIENDLY) if (pattern.test(text)) return say
  // Already a sentence for a person: a capital, a space, an end, and nothing of a program's in it (an error's name, a
  // file path, a code with underscores, braces). Left as it is.
  const programmy = /Error|Traceback|errno|\bat \w+ \(|(^|[\s(“"'])(\/|~\/)[^\s]*\/|\b[a-z]+_[a-z_]+\b|[{}<>]|\.py\b/
  if (/^[A-Z“"]/.test(text) && / /.test(text) && /[.!?”"]$/.test(text) && !programmy.test(text)) return text.slice(0, 400)
  return 'That didn’t work, and nothing was changed. Try again. If it keeps happening, restart Claude and type /matters.'
}

export const STILL_WORKING = 'Still finishing your last action. Try again in a moment.'
export const ASK_LABEL = 'Ask Claude to do it'

// Everything the app does locally runs through uv; without it, say so plainly instead of failing obscurely.
export const NO_UV = 'Immigration Packet Builder needs uv, a free helper that runs its tools. Claude can install it for you; then type /matters again.'
