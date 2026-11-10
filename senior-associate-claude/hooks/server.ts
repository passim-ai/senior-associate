// The server, one action at a time: every load, refresh and local action goes through here.
import type { EngineInterface } from 'claude-code'
import type { Access, Card, Check, MatterRow, Payload, Setup, View } from '../types'
import { progressSig, stepOf, stepText } from './matter'
import { MATTER_VIEWS, loadPrefs, markSeen, readAccess, readLibrary, readPayload, readPrefs, readRuns, readSetup, readView, remember, session, setNote, stillWorking, updateBusy, updateLibrary, updatePayload, updateRuns, updateSetup, updateView } from './state'
import { ACCOUNT_LABEL, LIBRARY_ABOUT, LIBRARY_PRICE, NO_UV, TRIAL_LABEL, dateOnly, friendly, nowIso } from './words'

// The pickers are macOS windows that can open behind Claude; while one is open the app can only wait.
export const WAITING: Record<string, string> = {
  add_documents: 'Choose the files in the Finder window that just opened. If you don’t see it, it may be behind this window.',
  add_folder: 'Choose the folder in the Finder window that just opened. If you don’t see it, it may be behind this window.',
}

// uv lives in different places depending on how it was installed; the desktop app's PATH may not include any.
export async function findUv($: EngineInterface): Promise<string> {
  if (session.uvPath) return session.uvPath
  let home = ''
  try {
    home = (await $.env.get('HOME')) ?? ''
  } catch {
    home = ''
  }
  const candidates = ['/opt/homebrew/bin/uv', '/usr/local/bin/uv', ...(home ? [`${home}/.local/bin/uv`, `${home}/.cargo/bin/uv`] : [])]
  for (const path of candidates) {
    const ok = await $.fs.exists(path).then(yes => yes, () => false)
    if (ok) {
      session.uvPath = path
      return path
    }
  }
  return 'uv'
}

// The plugin's settings for the server, the empty ones left out so its defaults (~/Matters) apply.
export function settings(): Record<string, string> {
  return Object.fromEntries(Object.entries(session.config).filter(([, value]) => value.trim() !== ''))
}

export async function call($: EngineInterface, request: Record<string, unknown>): Promise<Payload> {
  // cli.py: the standard library only, so the 15-second refresh never resolves a package and works offline.
  const server = `${$.plugin.root}/server/cli.py`
  const uv = await findUv($)
  let result: Awaited<ReturnType<typeof $.process.run>>
  try {
    result = await $.process.run(
      [uv, 'run', '--script', server, JSON.stringify({ ...settings(), ...request })],
      { timeoutMs: 600000 },
    )
  } catch (err) {
    const text = err instanceof Error ? err.message : String(err)
    session.lastRaw = text
    throw new Error(/ENOENT|not found|no such file/i.test(text) ? NO_UV : friendly(text))
  }
  const { exitCode, stdout, stderr } = result
  if (exitCode === 127 || /command not found: uv|uv: (command )?not found/i.test(stderr)) throw new Error(NO_UV)
  let data: Partial<Payload> & { error?: string } = {}
  try {
    data = JSON.parse(stdout.trim().split('\n').pop() || '{}')
  } catch {
    data = {}
  }
  if (exitCode !== 0 || data.error) {
    session.lastRaw = data.error || stderr.trim().split('\n').pop() || ''
    throw new Error(friendly(session.lastRaw))
  }
  return data as Payload
}

// Where a fresh load lands: the matter it carries, else the welcome the first time, else the list.
export async function landing($: EngineInterface, p: Payload, request: Record<string, unknown>): Promise<View> {
  const v = await readView($)
  if (request.stay === true) return v
  if (p.matter) {
    const stay = MATTER_VIEWS.includes(v) && v !== 'matter' && p.matter.path === request.matter_path
    return stay ? v : 'matter'
  }
  const pr = await readPrefs($)
  return !pr.onboarded && ownMatters(p).length === 0 ? 'welcome' : 'home'
}

// The attorney's own matters: the sample doesn't count, so a new attorney still sees the welcome.
export function ownMatters(p: Payload | null): MatterRow[] {
  return (p?.matters ?? []).filter(m => !m.sample)
}

// The setup check; null when it didn't answer this time (the next check tries again).
export async function doctor($: EngineInterface): Promise<Setup | null> {
  try {
    const res = await call($, { op: 'doctor' })
    const s: Setup = { checks: await withResearch($, res.checks ?? []), version: res.version, pending: (await readSetup($))?.pending ?? null }
    await updateSetup($, () => s)
    return s
  } catch {
    return null
  }
}

// Case-law research isn't the server's to see: it is whether the BIA Edge connector is in this session.
export async function withResearch($: EngineInterface, checks: Check[]): Promise<Check[]> {
  return [...checks, await lookForLibrary($)]
}

// Look for BIA Edge among the session's tools now, keep the answer for the page, and say where research stands.
export async function lookForLibrary($: EngineInterface): Promise<Check> {
  let connected = false
  try {
    const tools = await $.tool.list()
    connected = tools.some(t => /biaedge|bia_edge|passim/i.test(t.name) || /__(check_validity|get_case_by_citation)$/.test(t.name))
  } catch {
    connected = false
  }
  try {
    if ((await readLibrary($))?.connected !== connected) await updateLibrary($, () => ({ connected }))
  } catch {
    // the page keeps its last look
  }
  // Connected is not the same as usable: Passim may have answered that the account has no research access.
  const access = connected ? await readAccess($).then(a => a, () => null) : null
  return researchCheck(connected, access)
}

// The Setup screen's line on case-law research, and what the matter's page reads to know whether Claude can research.
export function researchCheck(connected: boolean, access: Access | null): Check {
  const base = { id: 'research', label: 'Case-law research', required: false, level: 'optional' }
  if (!connected) {
    return { ...base, ok: false, detail: `${LIBRARY_ABOUT} ${LIBRARY_PRICE}`, fix: 'Once you have an account, connect BIA Edge in Claude’s Connectors so letters can cite case law.', link: { id: 'passim_trial', label: TRIAL_LABEL } }
  }
  if (access) {
    return { ...base, ok: false, detail: `BIA Edge is connected, but Passim returned no research on ${dateOnly(access.at)}: “${access.message}”`, fix: 'Until research answers again, letters are written without case-law research.', link: access.plan ? { id: 'passim_account', label: ACCOUNT_LABEL } : { id: 'passim_review', label: 'Review your Passim account' } }
  }
  return { ...base, ok: true, detail: 'BIA Edge is connected, so letters can cite case law.' }
}

// Every change the app makes to the page's payload is numbered, so a quiet refresh that set out before an action
// can see the action's result arrived meanwhile and drop its own, older answer.
export async function setPayload($: EngineInterface, p: Payload) {
  session.seq += 1
  await updatePayload($, () => p)
}

// Load state (optionally one matter) and show it, with the app marked busy meanwhile.
export async function load($: EngineInterface, request: Record<string, unknown>, toast?: string) {
  if (session.inFlight) {
    await stillWorking($)
    return null
  }
  session.inFlight = true
  session.seq += 1
  // This action's turn: Close the picker can give the page back before the server answers, and then this load's
  // answer, when it comes, is dropped rather than shown.
  const token = ++session.flight
  session.waitingOn = WAITING[String(request.op)] ?? ''
  await updateBusy($, () => true)
  if (session.waitingOn) await setNote($, session.waitingOn, 'wait', undefined, { id: 'close-picker', label: 'Close the picker' })
  try {
    if (!session.prefsLoaded) await loadPrefs($)
    // A new attorney's first load asks for the sample matter; the server adds it once, to an empty Matters folder.
    if (request.op === 'state' && !session.sampleAsked && !(await readPrefs($)).onboarded) {
      session.sampleAsked = true
      request = { ...request, ensure_sample: true }
    }
    const p = await call($, request)
    if (session.flight !== token) return null
    let next = await landing($, p, request)
    // The very first time, the setup check comes before the welcome.
    if (next === 'welcome' && !(await readPrefs($)).setupSeen && (await doctor($))) next = 'setup'
    if (p.setup?.checks) await updateSetup($, s => ({ ...p.setup!, pending: s?.pending ?? null }))
    await setPayload($, p)
    await updateView($, () => next)
    session.refreshFails = 0
    if (p.matter) await remember($, { onboarded: true, lastMatter: p.matter.path })
    if (p.matter) await follow($, p.matter)
    // Opening a matter looks for BIA Edge again (the first load of a session always does), so its page knows
    // whether research is there without the setup check having run.
    if (p.matter && (request.op === 'state' || (await readLibrary($)) === null)) await lookForLibrary($)
    if (p.matter && MATTER_VIEWS.includes(next)) await markSeen($, p.matter.path)
    if (p.warning) await setNote($, friendly(p.warning))
    else {
      await setNote($, '')
      if (toast) $.ui.toast(toast)
    }
    return p
  } catch (err) {
    if (session.flight !== token) return null
    await setNote($, err instanceof Error ? err.message : String(err))
    return null
  } finally {
    if (session.flight === token) {
      session.inFlight = false
      session.waitingOn = ''
      await updateBusy($, () => false)
    }
  }
}

// What closes a picker's dialog (server/sa_server/adding.py, DISMISS_PICKER).
export const DISMISS_PICKER = 'tell application "System Events" to quit'

// Close the picker: a Finder window that opened behind Claude, or that the attorney walked away from, is closed, and
// the page is given back at once instead of waiting up to ten minutes for it. Only the picker Immigration Packet Builder opened
// is closed (its own prompt names it).
export async function closePicker($: EngineInterface) {
  session.flight += 1
  session.seq += 1
  session.inFlight = false
  session.waitingOn = ''
  await updateBusy($, () => false)
  try {
    const killed = await $.process.run(['pkill', '-f', 'choose (file|folder) with prompt "Choose the'], { timeoutMs: 5000 })
    // The script is gone, but the dialog it asked System Events for stays open until System Events quits (it starts
    // again by itself the next time anything needs it).
    if (killed.exitCode === 0) await $.process.run(['osascript', '-e', DISMISS_PICKER], { timeoutMs: 10000 })
  } catch {
    // nothing to close
  }
  await setNote($, 'The file picker is closed and nothing was added. Press Add files… when you’re ready.', 'ok')
}

// A quiet refresh of what the screen shows: the open matter on its screens, the list on Matters. No busy state, no
// toast, nothing flashes. One that set out before an action and comes back after it is dropped. One that fails twice
// in a row says so in plain words (the matter may have been moved in Finder) instead of going silent.
export async function refresh($: EngineInterface) {
  if (session.inFlight) return
  const [p, v] = await Promise.all([readPayload($), readView($)])
  if (!p) return
  const onMatter = MATTER_VIEWS.includes(v) && Boolean(p.matter)
  if (!onMatter && v !== 'home') return
  const seq = session.seq
  try {
    // The list screen reads the light rows of the `list` op, archived ones included, for Archived at its foot.
    const next = onMatter
      ? await call($, { op: 'state', matter_path: p.matter!.path })
      : { ...p, matters: (await call($, { op: 'list', include_archived: true })).matters }
    // An action finished while this was on its way: its answer is newer than this one.
    if (session.seq !== seq || session.inFlight) return
    if (onMatter && (await readPayload($))?.matter?.path !== p.matter!.path) return
    await updatePayload($, () => next)
    session.refreshFails = 0
    if (next.matter) await follow($, next.matter)
  } catch (err) {
    session.refreshFails += 1
    if (session.refreshFails === 2) {
      const text = err instanceof Error ? err.message : String(err)
      await setNote($, text, 'warn', undefined, /isn['’]t in your Matters folder/.test(text) ? { id: 'all', label: 'Go back to Matters' } : undefined)
    }
  }
}

// A local action that changes nothing on the page (open a folder or a file).
export async function act($: EngineInterface, request: Record<string, unknown>, toast: string): Promise<boolean> {
  if (session.inFlight) {
    await stillWorking($)
    return false
  }
  try {
    await call($, request)
    await setNote($, '')
    $.ui.toast(toast)
    return true
  } catch (err) {
    await setNote($, err instanceof Error ? err.message : String(err))
    return false
  }
}

// Keep the open matter's run up to date with where the build stands, and drop a chat-box start the server overtook.
export async function follow($: EngineInterface, c: Card) {
  const r = (await readRuns($))[c.path]
  if (!r || (r.status !== 'running' && r.status !== 'starting')) return
  const sig = progressSig(c)
  const s = stepOf(c)
  const step = stepText(s)
  if (sig === r.lastSeen && step === r.step) return
  const now = await nowIso($)
  await updateRuns($, all => {
    const cur = all?.[c.path]
    if (!cur) return all ?? {}
    return { ...(all ?? {}), [c.path]: { ...cur, step, stepLabel: s?.label ?? cur.stepLabel, lastSeen: sig, lastChangeAt: sig !== cur.lastSeen ? now : cur.lastChangeAt } }
  })
}
