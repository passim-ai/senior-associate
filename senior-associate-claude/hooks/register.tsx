// Immigration Packet Builder: the Passim app inside Claude Code.
//
// Client documents in, a filing-ready USCIS packet out (or, when documents are
// missing, a draft packet as far as the record allows plus a memo and a client
// request), without leaving the session. `/matters` opens the app beside the
// transcript, on the matters list with every group folded, so no client's name
// is on screen until the attorney asks for one. Where the side panel can't be
// placed (or for `/matters here`) the same app is drawn at the command's own row
// in the conversation; both draw from one state, so a press in either updates
// both. `/matters demo` shows only the fictional sample matter, from a folder of
// its own. The screens, in the order an attorney
// meets them, are laid out in docs/EXPERIENCE.md: Getting set up and Welcome
// (the first time), Matters, Your details, New matter, and a matter's tabs
// (Overview, Documents, Questions, Packet, Memo & request, Timeline), Help.
//
// Everything is the host's own elements (its font, cursor, hover and press
// behaviour), in the app's own colours, so it reads in a light or a dark
// theme, with Passim's wordmark and orange (theme.ts, kit.tsx).
//
// The work itself (build, update, review, the officer's review, clean up)
// runs as the plugin's own background agent, spawned from a button press and
// reported back into the app. When the session won't let the app start it,
// the request goes into the chat box for the attorney to send; nothing is
// ever sent on the attorney's behalf.
//
// The code is in small files beside this one: state.ts (the session's values), words.ts (plain words and
// times), server.ts (the server, one action at a time), matter.ts (reading a matter's card), runs.ts
// (starting and following Claude), perform.ts (what each press does), kit.tsx and draw.tsx (the frame and
// the pieces every screen shares), and screens/ (one file per screen).
import type { EngineInterface, Register, ResolveInput } from 'claude-code'
import { draw } from './draw'
import { BLOCKED, forgetTerms, isResearch, isScreened, researchGate, toolInput } from './privacy'
import { tableFor } from './kit'
import { noteAccess } from './library'
import { clearToList, enterDemo, goHome, goTo, openPane, paneUp } from './perform'
import { adoptSpawn, ensurePoll, finishRun, markWaiting } from './runs'
import { doctor, load, refresh } from './server'
import { PANE, go, liveAgents, loadPrefs, readPayload, readPrefs, readRuns, rebuildSession, remember, session } from './state'

export const register: Register = (on, options) => {
  session.config = {
    matters_root: String(options.matters_root ?? ''),
    exemplars_dir: String(options.exemplars_dir ?? ''),
  }

  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'matters',
      description: 'Immigration Packet Builder: build USCIS filing packets from a client’s documents. Type /matters pane to open it beside the chat.',
    })
    await loadPrefs($)
    await rebuildSession($)
    forgetTerms()

    // One timer follows runs and keeps what the screen shows current (runs.ts).
    session.poll?.cancel()
    session.poll = undefined
    ensurePoll($)

    return next(e)
  })

  // `/matters` opens the app beside the chat, on the matters list with its groups folded: no client's name is on
  // screen until the attorney asks for one, and none is left in the conversation. Where the side panel can't be
  // placed, and for `/matters here`, the app is drawn at the command's own row instead. `/matters demo` shows only the
  // fictional sample matter, from a folder of its own.
  on('command.run', { command: 'matters' }, async ($, e) => {
    const args = e.args ?? ''
    const wantsInline = /\bhere\b|\binline\b/i.test(args)
    if (!session.prefsLoaded) await loadPrefs($)
    // The demo's folder is chosen before anything is drawn, so the attorney's own list is never asked for meanwhile.
    // A demo that couldn't open says why on the page; the attorney's own list is not opened in its place.
    const askedDemo = /\bdemo\b/i.test(args)
    const wantsDemo = askedDemo && (await enterDemo($))
    if (askedDemo && !wantsDemo) return { text: 'Immigration Packet Builder couldn’t open the demo.' }
    // A panel already open stays where the attorney has it; a fresh opening starts at the folded list, and the page is
    // cleared to it before the panel is on screen, not once the server has answered.
    const wasUp = await paneUp($)
    if (!wasUp && !wantsDemo) await clearToList($)
    const placed = wantsInline ? false : await openPane($, true)
    if (!placed) await remember($, { inlineUses: (await readPrefs($)).inlineUses + 1 })
    const p = await readPayload($)
    if (wantsDemo) {
      if (!session.inFlight) void load($, { op: 'state', auto_select: false })
    } else if (/\bwelcome\b/i.test(args)) {
      // `/matters welcome` shows the first-time screen again, whatever is remembered.
      if (!p) await load($, { op: 'state', auto_select: false })
      await go($, 'welcome')
    } else if (/\bsetup\b/i.test(args)) {
      if (!p) await load($, { op: 'state', auto_select: false })
      await goTo($, 'setup')
      await doctor($)
    } else if (!p) {
      if (!session.inFlight) void load($, { op: 'state', auto_select: false })
    } else if (wasUp) {
      void refresh($)
    } else {
      // The list, folded and as it is now. A run that finished meanwhile is said there, with the press that opens
      // its matter.
      void goHome($)
    }
    return { text: placed ? 'Immigration Packet Builder is open in the side panel.' : 'Immigration Packet Builder' }
  })

  // The side panel was closed: nothing of the matter that was open is kept for when it shows again, and the
  // /matters rows in the conversation, which draw the app once the panel is gone, show the folded list too.
  on('ui.close', async ($, e, next) => {
    const res = await next(e)
    if (e.id === PANE && e.origin?.kind !== 'unload') {
      try {
        await clearToList($)
      } catch {
        // the next /matters clears it before it opens
      }
    }
    return res
  })

  // A request the app left in the chat box, sent: the agent the chat starts carries the app's run id in its brief, so
  // it is matched to its matter by that id (the chat may describe it differently) and followed as the app's own run.
  on('agent.spawn', async ($, e, next) => {
    const res = await next(e)
    if (res.agentId && !e.resume && !e.workflow) {
      try {
        if (await adoptSpawn($, e.prompt, e.description, res.agentId)) ensurePoll($)
      } catch {
        // the agent list finds it on the next tick, by its description
      }
    }
    return res
  })

  // A background run of ours finished: its final message is the report the attorney reads.
  on('turn.complete', async ($, e, next) => {
    if (e.agentId) {
      const all = await readRuns($)
      const mine = Object.values(all).find(r => r.agentId === e.agentId && r.status === 'running')
      if (mine) await finishRun($, e.agentId, e.reason === 'answer' ? 'done' : 'failed', e.reason === 'answer' ? e.answer : '', e.reason)
    }
    return next(e)
  })

  // Research inside Claude's agents never carries the client's details, and a matter run's own agents use nothing else
  // that could send words off the Mac (privacy.ts). The check decides before anything runs, at both of the host's
  // gates: tool.check (the permission verdict) and tool.call (the call itself), so a call that skips one still meets
  // the other. A check that fails refuses research rather than let it through. The host's local tools and local
  // shell commands pass untouched, and a matter's own agent asking for the attorney's OK is shown on its page.
  on('tool.check', async ($, e, next) => {
    if (isScreened(e.tool)) {
      const reason = await researchGate($, e.tool, e.input, e.agentId)
      if (reason) return { decision: 'deny', reason }
    }
    const result = await next(e)
    if (e.agentId && liveAgents.has(e.agentId)) {
      try {
        await markWaiting($, e.agentId, result.decision === 'ask' && e.approver === 'person')
      } catch {
        // the page misses one hint; the check stands
      }
    }
    return result
  }).catch(($, e, next) => (e.agentId && isResearch(e.tool) ? { decision: 'deny', reason: BLOCKED } : next(e)))
  on('tool.call', async ($, e, next) => {
    if (isScreened(e.tool)) {
      // The tool's own arguments, not the call's envelope (its name, its id), are what the gate reads.
      const reason = await researchGate($, e.tool, toolInput(e as unknown as Record<string, unknown>), e.agentId)
      if (reason) return { deny: reason }
    }
    const result = await next(e)
    // Passim's answer that the account has no research access is kept for the page; any other answer is not read.
    try {
      await noteAccess($, e.tool, result)
    } catch {
      // the page misses it this once; the call's own result stands
    }
    if (e.agentId && liveAgents.has(e.agentId)) {
      try {
        await markWaiting($, e.agentId, false)
      } catch {
        // as above
      }
    }
    return result
  }).catch(($, e, next) => (next.called ? next(e) : e.agentId && isResearch(e.tool) ? { deny: BLOCKED } : next(e)))

  // The same app in both places: inline, the row under `/matters` in the conversation, and the side panel.
  on('ui.render', { component: 'CommandOutput', props: { command: 'matters' } }, async ($, e) => render($, e, 'inline'))
  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => render($, e, 'pane'))
}

async function render($: EngineInterface, e: ResolveInput, site: 'inline' | 'pane'): Promise<JSX.Element> {
  // How wide the site is, in cells: the side panel says so in its props, the row in the conversation in the viewport.
  const drawn = e as ResolveInput & { props?: { bodyColumns?: unknown }; viewport?: { columns?: number } }
  const bodyColumns = drawn.props?.bodyColumns
  const columns = site === 'pane' && typeof bodyColumns === 'number' ? bodyColumns : drawn.viewport?.columns
  const els = tableFor($, e, columns)
  if (!els) {
    const { Text } = $.ui.resolve(e)
    return <Text>Immigration Packet Builder opens in the Claude desktop app. Open it there and type /matters.</Text>
  }
  return draw($, els, site)
}
