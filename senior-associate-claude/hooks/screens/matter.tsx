// One matter's Overview: the next step, the numbers, what needs attention beside the ask box, and the rest folded.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { ActionButton } from '../kit'
import type { Ctx, Kids } from '../kit'
import { CLIENT_TYPES, REVIEW_KINDS, STEP_KINDS, builtPast, changesLine, clientCount, docChanges, itemsLine, minutesWords, missingCount, neededBeforeFiling, neededParts, needsOf, removedWords, reportQuestions, reviewOnly, runKind, stepOf, stepText, suggestedQuestions, trackSvg, worksIn } from '../matter'
import type { Need } from '../matter'
import { askClaude, perform, sendQuestion } from '../perform'
import { answerFor, saveInstructions } from '../runs'
import { session, setNote, typed } from '../state'
import { ACCENT, ACCENT_TEXT, AMBER, DANGER, LINE, MUTED, NAVY, QUIET_TEXT, STAGE_TEXT } from '../theme'
import { markdown } from '../md'
import { ASK_LABEL, brief, clock, dateOnly, duration, nowMs, plural, when, whenPhrase } from '../words'
import { matterStatus } from '../status'

export async function matterScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Button, Input, isDesktop, narrow, svg, allRuns, pr, d, savedAnswers, st, g, open, missingCase, asked, actions, button, lone, link, links, card, barCard, columns, disclosure, eyebrow, rule, field, savedMark, matterPage, noProfile, tip, confirmBox, caseChooser, postureChips } = x
  const prg = c.progress
  const ledger = c.open_items ?? null
  const needs = needsOf(c)
  // Where the matter stands: the server's status with what only this session knows added (status.ts). The pill, the
  // card, the list and the notification all read it the same way.
  const run = allRuns[c.path] ?? null
  const shown = matterStatus(c, run, nowMs())
  const state = shown.phase
  // The matter's own state under what the app adds: what it shows once a stop is set aside.
  const phase = shown.base
  const step = stepOf(c)
  const fresh = c.documents.added_since_build ?? []
  const docs = docChanges(c)
  // New files and files replaced with new contents are offered the same way.
  const arrived = docs.added.length + docs.changed.length
  const needed = neededBeforeFiling(c)
  const blocking = needed.total
  const starting = state === 'starting' ? shown.run : null
  // Claude at work in this session's own agent; `serverWorking` when it works elsewhere (the chat, another window).
  const working = state === 'building' ? shown.run : null
  const failed = state === 'stopped' ? shown.run : null
  const serverWorking = shown.elsewhere
  const report = run && run.status === 'done' && run.answer ? run : null
  // Before the matter keeps open items, a report that ends in questions is how Claude asks.
  const reportAsks = state === 'needs_you' && shown.run?.status === 'done'
  const questions = reportAsks && report ? reportQuestions(report.answer) : []
  const attorneyNeeds = needs.filter(x => x.who === 'attorney')
  const clientNeeds = needs.filter(x => x.who === 'client')
  const systemNeeds = needs.filter(x => x.who === 'system')
  const gated = g?.matter === c.path && noProfile && !working && !starting
  const stalled = shown.stalled

  // The attorney's questions are answered on the Questions tab. Here: how many, and how many have an answer saved.
  const answered = (list: Need[]) => list.filter(x => answerFor(c, x.qkey, savedAnswers).trim()).length
  // Once every step is done, a decision not needed before filing still waits on Questions.
  const optional = ledger ? attorneyNeeds.filter(x => !x.blocks) : []

  // Setup problems, and a list of open items Claude can't read, each with Claude to fix it and a way to check again.
  const systemBlock = (heading: string) => (
    <Box key="sys" flexDirection="column" gap="sm">
      <Text weight="semibold" color={NAVY}>{heading}</Text>
      {systemNeeds.map(x => (
        <Box key={`sys-${x.i}`} flexDirection="column" gap="xs">
          <Text>{`• ${x.question}`}</Text>
          {x.fix ? <Text dimColor size="footnote">{x.fix}</Text> : null}
          {links(`sys-acts-${x.i}`, [
            x.ask ? link(`ask-fix:${x.i}`, ASK_LABEL, () => { void askClaude($, x.ask) }, true, `${ASK_LABEL}: ${brief(x.question, 60)}`) : null,
            link(`check-again:${x.i}`, 'Done — check again', () => { void perform($, 'check-again') }, true, `Done — check again: ${brief(x.question, 60)}`),
          ])}
        </Box>
      ))}
    </Box>
  )

  let title = 'What to do now'
  let border: string = ACCENT
  const lines: Kids = []
  // Under the actions: what to keep in mind (keep Claude open, macOS may ask), in small type.
  const foot: Kids = []
  let main: ActionButton[] = []
  const extra: (JSX.Element | null | false)[] = []
  const requestReady = Boolean(c.outputs.client_request && c.client_request_text)
  const copyButton: ActionButton = { id: 'copy-request', label: 'Copy the client request', kind: 'secondary', detail: 'Ready to paste into an email' }
  const taken = docs.removed
  // What the attorney changed in chat since Claude last finished a step: the reviews haven't seen it yet.
  const inChat = builtPast(c) ? c.chat_changes ?? [] : []
  const changes = arrived + taken.length + inChat.length
  const tookOut = removedWords(docs)
  const madeInChat = inChat.length === 1 ? (docs.masked ? 'you made a change in chat' : `you made a change in chat (${inChat[0]!.what})`) : `you made ${inChat.length} changes in chat`
  const freshLine = (since: string) => <Text key="fresh" weight="semibold" color={NAVY}>{changesLine(docs, since, inChat.length ? madeInChat : '')}</Text>
  const updateButton: ActionButton = {
    id: 'update', label: 'Update the packet', kind: 'primary',
    detail: !taken.length && !inChat.length ? `Works in ${worksIn(docs)}` : !arrived && !taken.length ? 'Re-checks what you changed in chat' : 'Brings the packet up to date',
  }

  if (state === 'starting') {
    title = 'Waiting for you'
    border = AMBER
    lines.push(<Text key="s1">Claude needs your OK to start. Press Enter to send the request in your chat box.</Text>)
    foot.push(<Text key="s2" dimColor size="footnote">This page switches to Claude is working by itself once it starts.</Text>)
    extra.push(link('cancel-start', 'Cancel', () => { void perform($, 'cancel-start') }))
  } else if (state === 'building') {
    title = 'Claude is working'
    const kind = working?.kind ?? 'build'
    const label = runKind(kind).doing
    const s = stepText(step)
    lines.push(<Text key="w1" weight="semibold" color={NAVY}>{STEP_KINDS.has(kind) && s ? `${label} · ${s}` : label}</Text>)
    // The track: one segment per step, and what comes next.
    if (STEP_KINDS.has(kind) || serverWorking) {
      lines.push(
        <Box key="track" flexDirection="column" gap="xs">
          {isDesktop
            ? svg(trackSvg(prg.stages), `${prg.done} of ${prg.total} steps done`)
            : <Box flexDirection="row">{prg.stages.map(st => <Text key={st.id} color={STAGE_TEXT[st.status] ?? QUIET_TEXT}>{'━━ '}</Text>)}</Box>}
          {step && prg.current?.status === 'in_progress' && step.index < prg.stages.length
            ? <Text dimColor size="footnote">Then: {prg.stages.slice(step.index, step.index + 2).map(st => st.label).join(', ')}</Text>
            : null}
        </Box>,
      )
    }
    if (working?.waitingOk) {
      border = AMBER
      lines.push(<Text key="ok">{`Claude is waiting for your OK in the chat. The ${runKind(kind).noun} continues once you answer.`}</Text>)
    } else if (stalled) {
      border = AMBER
      lines.push(<Text key="stall">Nothing has changed for 20 minutes. Claude may be waiting for your OK in the chat, or it stopped.</Text>)
    }
    if (working) {
      const left = STEP_KINDS.has(kind) ? prg.minutes_left : REVIEW_KINDS.has(kind) ? 8 : kind === 'stress_test' ? 15 : null
      const elapsed = nowMs() - Date.parse(working.startedAt)
      lines.push(<Text key="w2">{[`Started ${clock(working.startedAt)}`, elapsed < 60000 ? 'just started' : `running ${duration(elapsed)}`, left !== null && !stalled ? minutesWords(left) : ''].filter(Boolean).join(' · ')}</Text>)
      if (!stalled) foot.push(<Text key="w3" dimColor size="footnote">Keep Claude open until it finishes. You can use Claude for other things meanwhile; you’ll get a notification when it’s done.</Text>)
      if (asked === 'stop') {
        lines.push(confirmBox('stop', `Stop Claude now? Everything finished so far is kept.${STEP_KINDS.has(kind) ? ' Continue building picks up where it stopped.' : ''}`, { id: 'stop-yes', label: 'Yes, stop' }, 'Keep working'))
      }
      extra.push(link('watch', 'Watch Claude work', () => { void perform($, 'watch') }, true))
      if (stalled) extra.push(link('stop-retry', 'Stop and try again', () => { void perform($, 'stop-retry') }, true))
      else if (asked !== 'stop') extra.push(link('stop', 'Stop', () => { void perform($, 'stop') }))
    } else {
      // Claude works on it elsewhere: the run lease says who and since when. Starting another run now would only be
      // refused, so the way forward is to leave it; a lease nobody renews for 30 minutes ends, and the matter pauses.
      const lease = c.status.lease
      const since = lease?.heartbeat_at || prg.updated_at || c.updated_at || ''
      if (since) lines.push(<Text key="w2">{`Last progress ${clock(since)} (${when(since)})`}</Text>)
      foot.push(<Text key="w3" dimColor size="footnote">{lease?.holder === 'chat'
        ? 'Claude is changing this matter in the chat. It updates here as it goes; keep Claude open until it’s done.'
        : 'Claude is working on this matter outside this page. It updates as each step finishes; keep Claude open until it’s done. If Claude is still working on it in the chat, leave it.'}</Text>)
      // An older plugin's run keeps no lease: then a step marked running may be nobody's, and Continue building is offered.
      if (!lease) extra.push(link('continue-link', `Not working? Continue building${step?.label ? `: picks up at ${step.label}` : ''}`, () => { void perform($, 'continue') }, true))
      // A run this session didn't start holds the matter and looks alive, but the attorney knows Claude stopped (the chat
      // was closed mid-run, say): they can let the matter go, after a confirmation here on the page.
      else if (lease.fresh && lease.run_id && lease.run_id !== run?.runId) {
        if (asked === 'not-working') {
          lines.push(confirmBox('not-working', 'Let go of this matter? Do this only if Claude isn’t working on it in the chat or another window. If a run is still going, it stops at its next step. Everything finished so far is kept.', { id: 'not-working-yes', label: 'Yes, let it go' }, 'Keep waiting'))
        } else extra.push(link('not-working', 'Claude isn’t working on this anymore', () => { void perform($, 'not-working') }, true))
      }
    }
  } else if (state === 'stopped' && failed) {
    title = 'Stopped'
    border = DANGER
    const why = failed.reason === 'error' ? 'Claude hit a temporary problem, such as a busy service or a dropped connection'
      : failed.reason === 'by_you' ? 'you stopped it'
      : failed.reason === 'aborted' || failed.reason === 'killed' ? 'it was stopped'
      : failed.reason === 'refusal' ? 'Claude declined to continue'
      : 'it ran into an error'
    const at = failed.stepLabel || step?.label || ''
    const where = STEP_KINDS.has(failed.kind) && step ? ` at step ${step.index} of ${step.total}${at ? ` (${at})` : ''}` : ''
    const tail = STEP_KINDS.has(failed.kind) ? 'Everything finished before that is saved.' : 'Nothing was lost.'
    lines.push(<Text key="stop">{`The ${runKind(failed.kind).noun} stopped${where}: ${why}. ${tail}`}</Text>)
    main = [{ id: 'retry-run', label: 'Try again', kind: 'primary', detail: STEP_KINDS.has(failed.kind) && at ? `Picks up at ${at}` : 'Starts it again' }]
    if (failed.agentId) extra.push(link('watch', 'See what Claude was doing', () => { void perform($, 'watch') }))
    extra.push(link('dismiss-run', 'Not now: show where the matter stands', () => { void perform($, 'dismiss-run') }))
  } else if (c.needs_intake && state !== 'stopped') {
    title = 'What is being filed?'
    border = missingCase ? AMBER : ACCENT
    lines.push(<Text key="intake">This folder was made outside Senior Associate, so Claude doesn’t know the case yet. Choose it, then press Save.</Text>)
    lines.push(...caseChooser(d, open, missingCase ? 'Choose one below, then press Save.' : '', { submitLabel: 'save', onSubmit: () => { void perform($, 'set-intake') } }))
    lines.push(
      <Box key="intake-postures" flexDirection="column" gap="sm">
        <Text weight="semibold" color={NAVY}>New filing or a response?</Text>
        {postureChips(d)}
      </Box>,
    )
    main = [{ id: 'set-intake', label: 'Save', kind: 'primary', detail: 'Then build or review the documents' }]
  } else if (gated) {
    title = 'Before you build'
    border = AMBER
    lines.push(<Text key="gate">⚠ Your details aren’t filled in, so the G-28 and the letter’s signature will be left blank.</Text>)
    main = [
      { id: 'gate-details', label: 'Add your details first', kind: 'primary', detail: '2 minutes' },
      { id: 'gate-build', label: 'Build anyway', kind: 'secondary', detail: 'Fill them in later' },
    ]
    extra.push(link('gate-cancel', 'Not now', () => { void perform($, 'gate-cancel') }))
  } else if (state === 'needs_you') {
    const asks = attorneyNeeds.length || reportAsks
    title = asks ? 'Your judgment is needed' : 'Something on this Mac needs setting up'
    lines.push(<Text key="lead">{asks
      ? 'Answer what you can on Questions, then press Update the packet. Anything you leave blank stays on the list for later.'
      : 'Something on this Mac needs setting up before Claude can go on. Fix it below, then press Update the packet.'}</Text>)
    if (systemNeeds.length) lines.push(systemBlock('On this Mac'))
    if (arrived) lines.push(<Text key="fresh" dimColor>{`It also works in ${worksIn(docs)}, since the last build.`}</Text>)
    if (taken.length) lines.push(<Text key="taken" dimColor>{`It also takes out what ${tookOut}.`}</Text>)
    if (inChat.length) lines.push(<Text key="in-chat" dimColor>{`It also re-checks what ${madeInChat}.`}</Text>)
    const count = attorneyNeeds.length || questions.length
    main = asks
      ? [
          { id: 'items', label: 'Review questions', kind: 'primary', detail: count ? `${plural(count, 'question', 'questions')} · ${attorneyNeeds.length ? answered(attorneyNeeds) : questions.filter((_q, k) => answerFor(c, `report-${k}`, savedAnswers).trim()).length} answered` : 'Claude’s questions' },
          { id: 'update', label: 'Update the packet', kind: 'secondary', detail: 'With your answers' },
        ]
      : [{ id: 'update', label: 'Update the packet', kind: 'primary', detail: 'With your answers' }]
    if (c.outputs.packet) extra.push(link('open-packet', 'Open draft packet', () => { void perform($, 'open-packet') }, true))
  } else if (state === 'waiting_client') {
    title = 'Waiting on the client'
    const k = clientCount(c, needs)
    if (changes) {
      lines.push(freshLine('the packet was built'))
      main = [updateButton, ...(requestReady ? [copyButton] : [])]
    } else {
      lines.push(<Text key="wc">{`Waiting on the client for ${plural(k, 'item', 'items')}.`}</Text>)
      main = [{ id: 'add-files', label: 'Add files…', kind: 'primary', detail: 'What the client sent' }, ...(requestReady ? [copyButton] : [])]
    }
    if (clientNeeds.length) lines.push(<Box key="wc-list" flexDirection="column" gap="xs">{clientNeeds.slice(0, 6).map(x => <Text key={`wc-${x.i}`}>{`• ${x.question}`}</Text>)}</Box>)
    if (optional.length && !main.some(m => m.id === 'update')) extra.push(link('update', 'Update the packet', () => { void perform($, 'update') }, true, 'Update the packet with your answers'))
    if (c.outputs.packet) extra.push(link('open-packet', 'Open draft packet', () => { void perform($, 'open-packet') }, true))
  } else if (phase === 'new') {
    title = 'Add the client’s documents'
    lines.push(<Text key="new">Add the client’s documents to get started. The Build button appears once there’s something to build.</Text>)
    if (!pr.pickerSeen) foot.push(<Text key="sysev" dimColor size="footnote">macOS may ask whether Claude can control System Events. Choose OK; that’s what lets the file picker open in front.</Text>)
    main = [
      { id: 'add-files', label: 'Add files…', kind: 'primary', detail: 'Choose the client’s documents' },
      { id: 'add-folder', label: 'Add a folder…', kind: 'secondary', detail: 'Copies a folder of their documents' },
    ]
  } else if (phase === 'ready') {
    title = 'Ready to build'
    lines.push(<Text key="ready">Claude reviews the documents, prepares the forms, drafts and researches the cover letter, assembles and checks the packet, and leaves you a memo. If documents are missing, it lists exactly what to get. Nothing is filed or sent.</Text>)
    main = [
      { id: 'build', label: 'Build packet', kind: 'primary', detail: 'About 1–1½ hours · runs in the background' },
      { id: 'review', label: 'Review documents first', kind: 'secondary', detail: 'About 5–10 minutes · see what’s missing first' },
    ]
  } else if (phase === 'reviewed') {
    const k = missingCount(c)
    title = arrived || taken.length ? 'Documents changed since the review' : 'Documents reviewed'
    if (arrived || taken.length) {
      // New or replaced documents after a review: look at them again first (quick), or go straight to the build,
      // which reviews them first.
      lines.push(<Text key="fresh" weight="semibold" color={NAVY}>{changesLine(docs, 'Claude reviewed the documents')}</Text>)
      lines.push(<Text key="fresh-how">Review the documents again to see what’s still missing and refresh the client request. Or build the packet now: the build starts by reviewing them.</Text>)
      main = [
        { id: 'review-again', label: 'Review the documents again', kind: 'primary', detail: 'About 5–10 minutes · see what’s still missing' },
        { id: 'build', label: 'Build packet', kind: 'secondary', detail: 'About 1–1½ hours · reviews them first' },
      ]
    } else {
      lines.push(<Text key="rev">{k
        ? `Claude reviewed the ${plural(c.documents.count, 'document', 'documents')}. ${plural(k, 'thing is', 'things are')} missing; they’re on the client request. Send it now and build when they arrive, or build now and Claude leaves placeholders.`
        : `Claude reviewed the ${plural(c.documents.count, 'document', 'documents')} and found nothing missing. Build the packet when you’re ready.`}</Text>)
      main = [
        { id: 'build', label: 'Build packet', kind: 'primary', detail: 'About 1–1½ hours · runs in the background' },
        ...(k && requestReady ? [copyButton] : []),
      ]
    }
    if (attorneyNeeds.length) {
      lines.push(<Text key="rev-qs">{`${attorneyNeeds.length === 1 ? 'A question waits' : `${attorneyNeeds.length} questions wait`} for you on Questions (${answered(attorneyNeeds)} answered). Your answers go with ${arrived ? 'the next review or the build' : 'the build'}; anything you leave blank stays on the list.`}</Text>)
    }
    if (!arrived && !taken.length) foot.push(<Text key="rev-more" dimColor size="footnote">When the client sends more: Add documents…, under More you can do, then Review the documents again.</Text>)
  } else if (phase === 'paused') {
    title = 'Paused'
    const at = step?.label ?? ''
    lines.push(<Text key="paused">{`Claude stopped working on this ${whenPhrase(prg.updated_at || c.updated_at || '')}${step ? `, at step ${step.index} of ${step.total}${at ? ` (${at})` : ''}` : ''}. Everything finished so far is saved.`}</Text>)
    // Nobody in this session started it: it may be running from the chat, so say so before offering to start it again.
    if (prg.stages.some(s => s.status === 'in_progress') && !run) foot.push(<Text key="paused-quiet" dimColor size="footnote">A step is still marked as running, but nothing has changed for a while. If Claude is still working on it in the chat, leave it; this page catches up as each step finishes.</Text>)
    main = step?.index === 1 && prg.stages[0]?.id === 'docs_review' && !(run && STEP_KINDS.has(run.kind))
      ? [
          { id: 'review', label: 'Finish the document review', kind: 'primary', detail: 'About 5–10 minutes · then see what’s missing' },
          { id: 'build', label: 'Build packet', kind: 'secondary', detail: 'About 1–1½ hours · runs in the background' },
        ]
      : [{ id: 'continue', label: 'Continue building', kind: 'primary', detail: at ? `Picks up at ${at}` : 'Picks up where it stopped' }]
  } else if (phase === 'draft') {
    title = changes ? 'Changes to work in' : 'Draft packet ready'
    if (changes) {
      lines.push(freshLine('the packet was built'))
      main = [updateButton, { id: 'items', label: 'Review questions', kind: 'secondary', detail: blocking ? `${blocking} needed before filing` : '' }]
    } else {
      const clientOwes = (ledger?.open ?? []).some(it => CLIENT_TYPES.includes(it.type))
      lines.push(<Text key="draft">{ledger
        ? blocking
          ? `The draft packet is built. ${plural(blocking, 'thing is', 'things are')} needed before filing: ${neededParts(needed)}.`
          : 'The draft packet is built. Nothing on the list is needed before filing; read it through and decide what else to add.'
        : 'The draft packet is built. The memo lists what’s still needed before filing.'}</Text>)
      const seeLeft: ActionButton = { id: 'items', label: 'Review questions', kind: 'secondary', detail: blocking ? `${blocking} needed before filing` : ledger ? itemsLine(ledger.counts) : '' }
      main = clientOwes && requestReady
        ? [{ ...copyButton, kind: 'primary' }, seeLeft]
        : [{ ...seeLeft, kind: 'primary' }, ...(c.outputs.memo ? [{ id: 'memo', label: 'Read the memo', kind: 'secondary' as const, detail: 'What each item is and why' }] : [])]
    }
    if (optional.length && !main.some(m => m.id === 'update')) extra.push(link('update', 'Update the packet', () => { void perform($, 'update') }, true, 'Update the packet with your answers'))
    if (c.outputs.packet) extra.push(link('open-packet', 'Open draft packet', () => { void perform($, 'open-packet') }, true))
    if (c.outputs.filing_checklist) extra.push(link('print-checklist', 'Print the filing checklist', () => { void perform($, 'print-checklist') }))
  } else if (phase === 'complete') {
    title = c.outputs.packet ? (changes ? 'Changes to work in' : 'Ready to file') : 'Every step is done'
    if (c.outputs.packet) {
      if (changes) {
        lines.push(freshLine('the packet was built'))
        main = [updateButton, { id: 'open-packet', label: 'Open packet', kind: 'secondary', detail: c.outputs.packet.name }]
      } else {
        lines.push(<Text key="done">The packet passed its final review, including the officer’s review, and nothing stands in the way of filing. Read it through, then follow the memo’s Filing logistics: signatures, photos, fees and mailing.</Text>)
        main = [
          { id: 'open-packet', label: 'Open packet', kind: 'primary', detail: c.outputs.packet.name },
          ...(c.outputs.memo ? [{ id: 'memo', label: 'Read the memo', kind: 'secondary' as const, detail: 'Filing steps and signatures' }] : []),
        ]
      }
      // Questions still open here are ones the packet can be filed without; they wait on Questions.
      if (optional.length && !changes) extra.push(link('update', 'Update the packet', () => { void perform($, 'update') }, true, 'Update the packet with your answers'))
      // Files added since the build don't take away filing: the attorney may file without them.
      extra.push(link('mark-filed', 'Mark as filed', () => { void perform($, 'mark-filed') }, true))
      if (c.outputs.filing_checklist) extra.push(link('print-checklist', 'Print the filing checklist', () => { void perform($, 'print-checklist') }, true))
      // A split filing: some forms go on paper in a packet of their own.
      if (c.outputs.paper_packet) extra.push(link('open-paper-packet', 'Open the paper part', () => { void perform($, 'open-paper-packet') }, true, `Open ${c.outputs.paper_packet.name}`))
    } else {
      lines.push(<Text key="clean">Every step is done. Clean up to delete Claude’s working files from the matter folder.</Text>)
      main = [{ id: 'closeout', label: 'Clean up working files', kind: 'primary', detail: 'Deletes Claude’s working copies of client documents' }]
    }
  } else if (phase === 'filed') {
    title = 'Filed'
    lines.push(<Text key="filed">{c.filed_at ? `Filed ${dateOnly(c.filed_at)}.` : 'Filed.'}</Text>)
    extra.push(link('unmark-filed', 'Undo', () => { void perform($, 'unmark-filed') }))
    if (c.outputs.packet) extra.push(link('open-packet', 'Open packet', () => { void perform($, 'open-packet') }))
  } else {
    // A state this version doesn't know: the safe way forward.
    title = 'Continue building'
    lines.push(<Text key="other">Claude isn’t working on this matter now. Continue building picks up from the last finished step.</Text>)
    main = [{ id: 'continue', label: 'Continue building', kind: 'primary', detail: 'Picks up where it stopped' }]
  }

  // On any other card, something to fix first (the open items list can't be read, say) is said there too.
  if (systemNeeds.length && !['needs_you', 'building', 'starting', 'stopped'].includes(state)) lines.unshift(systemBlock('Needs fixing first'))

  // The report of the last run, when it finished well: what Claude did, and when. Questions already given their own
  // answer boxes above aren't repeated under it.
  const reportText = (() => {
    if (!report) return ''
    const first = questions[0]
    const lines = report.answer.split('\n')
    const at = first ? lines.findIndex(l => /^\s*\d+[.)]\s+/.test(l) && first.startsWith(l.replace(/^\s*\d+[.)]\s+/, '').trim())) : -1
    return (at > 0 ? lines.slice(0, at).join('\n') : report.answer).trim()
  })()
  const reportCard = report
    ? card('What Claude did', [
        <Text key="when" dimColor size="footnote">{`${runKind(report.kind).done} · finished ${clock(report.endedAt)}, took ${duration(Date.parse(report.endedAt) - Date.parse(report.startedAt))}`}</Text>,
        markdown(x, 'report', reportText.length > 4000 ? `${reportText.slice(0, 4000)}…` : reportText, true),
      ], undefined, 'card-report')
    : null

  // ----- everything else that can be done with this matter now, each with what it does -----
  const busyNow = Boolean(working || starting || serverWorking)
  const onCard = new Set(main.map(m => m.id))
  const built = builtPast(c)
  const anyDone = prg.stages.some(s => s.status !== 'pending')
  const more: { id: string; label: string; detail: string }[] = []
  const offer = (id: string, label: string, detail: string) => { if (!onCard.has(id)) more.push({ id, label, detail }) }
  // Filed: the one thing left to do is tidy up.
  if (phase === 'filed' && !busyNow && prg.total > 0 && prg.done === prg.total) offer('closeout', 'Clean up working files', 'Deletes Claude’s working copies of the client’s documents. Your documents and the finished files stay.')
  if (!c.needs_intake && !gated && !starting && phase !== 'filed') {
    offer('add-files', 'Add documents…', busyNow
      ? `Claude won’t see them in this run. When it finishes, ${run && REVIEW_KINDS.has(run.kind) ? 'Review the documents again' : 'Update the packet'} works them in.`
      : reviewOnly(c) ? 'What the client sent, or anything left out. Then Review the documents again shows what’s still missing.'
      : built ? 'What the client sent, or anything left out. Then Update the packet works them in.'
      : 'The client’s files, one at a time. The Documents tab also takes a whole folder.')
    if (!busyNow && !failed) {
      if (reviewOnly(c)) offer('review-again', 'Review the documents again', 'About 5–10 minutes. Claude re-reads every document, new ones included, and rewrites what’s missing and the client request. It doesn’t build.')
      if (built) offer('update', 'Update the packet', 'Works in what changed since the build: documents added or taken out, items marked done or reopened, and your answers. Then it checks the packet again.')
      if (built) offer('change', 'Tell Claude what to change', 'A correction, or a different approach. Claude redoes only the steps it affects, checks the packet again, and updates the memo.')
      if (built) offer('steps', 'Redo a step…', 'On the Packet tab, choose a step. Claude redoes it and every step after it; the steps before it stay as they are.')
      if (c.outputs.packet) offer('stress', 'Re-check as a USCIS officer would', 'About 15 minutes. A fresh, full officer’s review of the packet as it is now, not only of what changed; it updates Questions and the memo.')
      if (c.outputs.packet && phase !== 'complete') offer('mark-filed', 'Mark as filed', 'Once you’ve filed it. Moves it to Filed on the matters list; Undo puts it back.')
      if (prg.total > 0 && prg.done === prg.total) offer('closeout', 'Clean up working files', 'Deletes Claude’s working copies of the client’s documents. Your documents and the finished files stay.')
      offer('intake', 'Change what is being filed', anyDone || ledger
        ? 'A different case type, filing posture, or how it is filed. The steps start over for a new case; your documents stay, and the earlier work is kept, not deleted.'
        : 'A different case type, filing posture, or how it is filed, before anything has run.')
    }
  }
  // Archive: off the main list, into Archived at its foot. Not while Claude works on it.
  if (!busyNow && !c.needs_intake) {
    if (c.meta.archived_at) offer('unarchive', 'Unarchive', 'Back on the main list of matters.')
    else offer('archive', 'Archive', 'Takes it off the main list, into Archived at its foot. Nothing is deleted; Unarchive puts it back.')
  }
  const moreList = more.map(m => (
    <Box key={`more-${m.id}`} flexDirection="column" gap="xs">
      <Box flexDirection="row">
        <Button key={`do-${m.id}`} plain label={m.label} onPress={() => { void perform($, m.id) }}>
          <Text weight="semibold" color={NAVY}>{m.label}</Text>
          <Text color={MUTED}>{'  ›'}</Text>
        </Button>
      </Box>
      <Text dimColor size="footnote">{m.detail}</Text>
    </Box>
  ))

  // ----- the attorney's own instructions for the matter, which every run follows -----
  const savedInstructions = c.attorney_instructions ?? ''
  const instructionsValue = typed.instructions[c.path] ?? savedInstructions
  const instructionsAfter = busyNow
    ? 'The steps Claude hasn’t reached yet follow them.'
    : built
      ? 'Claude follows them from its next run. To redo the packet with them now, use Tell Claude what to change.'
      : 'Claude follows them in every step of the build.'
  const instructionsBody = [
    <Text key="ins-what" dimColor size="footnote">Anything Claude should follow on this matter: what to lead with, what to leave out, how to argue it. Claude reads these before every step, in the build and every update after it.</Text>,
    field(<Input
      key="instructions"
      label="Additional attorney instructions"
      placeholder="e.g. Lead the letter with the joint lease. Don’t include an I-765."
      rows={4}
      submitLabel="save"
      value={instructionsValue || undefined}
      onInput={val => { typed.instructions[c.path] = val }}
      onSubmit={val => saveTheInstructions(val)}
    />, 'field-instructions'),
    lone('save-instructions', button('save-instructions', 'Save instructions', () => saveTheInstructions(typed.instructions[c.path] ?? instructionsValue), 'secondary', { small: true })),
    savedMark('instructions', instructionsValue === savedInstructions),
  ]
  function saveTheInstructions(val: string) {
    typed.instructions[c.path] = val
    void saveInstructions($, c, val).then(async saved => {
      if (!saved) return
      session.savedField = 'instructions'
      await setNote($, val.trim() ? `Instructions saved. ${instructionsAfter}` : 'Instructions cleared.', 'ok')
    })
  }

  // ----- the sample matter: what to try, and once its documents are reviewed, what a good review catches -----
  const guide = c.sample ?? null
  const sampleReviewed = prg.stages.some(s => s.id === 'docs_review' && (s.status === 'passed' || s.status === 'skipped'))
  const sampleCard = guide
    ? card(guide.title ?? 'This is a sample matter', [
        guide.intro ? <Text key="sample-intro">{guide.intro}</Text> : null,
        sampleReviewed && guide.caught?.length
          ? <Box key="sample-caught" flexDirection="column" gap="xs">
              <Text weight="semibold" color={NAVY}>{guide.caught_title ?? 'What a good review catches'}</Text>
              {guide.caught.map((line, i) => <Text key={`caught-${i}`}>{`${i + 1}. ${line}`}</Text>)}
              <Text dimColor size="footnote">Compare them with Questions, above.</Text>
            </Box>
          : guide.try ? <Text key="sample-try" dimColor>{guide.try}</Text> : null,
        guide.after ? <Text key="sample-after" dimColor size="footnote">{guide.after}</Text> : null,
      ], undefined, 'card-sample')
    : null

  // ----- asking Claude about the matter: a question, research, or a change, answered in the chat -----
  const research = st?.checks.find(ch => ch.id === 'research')
  const suggestions = suggestedQuestions(c)
  const askColumn = (
    <Box key="ask-col" flexDirection="column" gap="md">
      <Text size="heading" weight="semibold" color={NAVY}>Ask Claude about this matter</Text>
      <Text dimColor size="footnote">{busyNow
        ? 'Ask anything while Claude works. Changes you ask for wait until it finishes, or go into your instructions for the steps it hasn’t reached.'
        : 'A question, some research, or a change you want made. Claude reads this matter’s documents and work, looks up the law in BIA Edge, and makes the changes you ask for. It answers in the chat.'}</Text>
      {research && !research.ok ? <Text key="ask-research" color={AMBER} size="footnote">Connect BIA Edge in Claude’s Connectors so Claude can cite case law.</Text> : null}
      {/* Keyed by the round, so the box is drawn afresh, and empty, once a question has gone. */}
      <Box key={`ask-${session.askRound}`} flexDirection="column" gap="xs">
        {field(<Input
          key="ask"
          label="Your question"
          placeholder={builtPast(c) ? 'e.g. How strong is our bona fide marriage evidence?' : 'e.g. Does the 2019 arrest affect eligibility?'}
          rows={2}
          submitLabel="ask"
          value={typed.ask[c.path] || undefined}
          onInput={val => { typed.ask[c.path] = val }}
          onSubmit={val => { void sendQuestion($, c, val) }}
        />)}
        <Text dimColor size="caption">Enter sends it. For a new line, press Shift+Enter.</Text>
      </Box>
      {suggestions.length
        ? <Box key="ask-try" flexDirection="column" gap="xs">
            <Text dimColor size="footnote">Or ask:</Text>
            {suggestions.map((q, i) => lone(`try-${i}`, button(`ask-try:${i}`, `${q}  ›`, () => { void sendQuestion($, c, q) }, 'link')))}
          </Box>
        : null}
      {inChat.length > 1
        ? <Box key="ask-changes" flexDirection="column" gap="xs">
            <Text dimColor size="footnote">Changed in chat since Claude last checked the packet:</Text>
            {inChat.slice(-6).map((ch, i) => <Text key={`chg-${i}`} dimColor size="footnote">{`• ${ch.what}`}</Text>)}
          </Box>
        : null}
    </Box>
  )

  // ----- what needs the attorney: the open items and Claude's questions, needed before filing first -----
  const KIND: Record<string, string> = { attorney_decision: 'Your decision', client_document: 'From the client', client_question: 'From the client', attorney_action: 'For you to do', risk: 'Risk to weigh' }
  const attention: { id: string; title: string; kind: string; blocks: boolean }[] = []
  const seen = new Set<string>()
  for (const x of [...attorneyNeeds, ...clientNeeds]) {
    if (seen.has(x.qkey)) continue
    seen.add(x.qkey)
    attention.push({ id: x.qkey, title: x.question, kind: x.who === 'attorney' ? 'Your decision' : 'From the client', blocks: x.blocks })
  }
  for (const it of ledger?.open ?? []) {
    if (seen.has(it.id)) continue
    seen.add(it.id)
    attention.push({ id: it.id, title: it.type === 'attorney_decision' && it.question ? it.question : it.title, kind: KIND[it.type] ?? 'Open item', blocks: Boolean(it.blocks_filing) })
  }
  questions.forEach((q, k) => attention.push({ id: `report-${k}`, title: q, kind: 'Claude’s question', blocks: false }))
  attention.sort((a, b) => Number(b.blocks) - Number(a.blocks))
  const ATTENTION_SHOWN = 4
  const attentionColumn = (
    <Box key="attention-col" flexDirection="column" gap="md">
      <Text size="heading" weight="semibold" color={NAVY}>Needs attention</Text>
      {attention.length === 0
        ? <Text dimColor size="footnote">{ledger || builtPast(c) || reviewOnly(c) ? 'Nothing is open right now.' : 'Claude lists what’s missing and what needs you once it reviews the documents.'}</Text>
        : attention.slice(0, ATTENTION_SHOWN).map(a => (
            <Box key={`att-${a.id}`} flexDirection="row" gap="sm" alignItems="flex-start">
              <Text color={a.blocks ? ACCENT_TEXT : MUTED} weight="bold">•</Text>
              <Box flexDirection="column" flexShrink={1} flexGrow={1} gap="xs">
                <Text weight="semibold" size="footnote">{a.title}</Text>
                <Box flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">
                  <Text dimColor size="caption">{`${a.kind} · ${a.blocks ? 'Needed before filing' : 'Not needed before filing'}`}</Text>
                  {button(`view:${a.id}`, 'View ›', () => { void perform($, `view:${a.id}`) }, 'link', { name: `View: ${brief(a.title, 80)}`, small: true })}
                </Box>
              </Box>
            </Box>
          ))}
      {attention.length > ATTENTION_SHOWN ? lone('view-all', button('view-all', `All ${attention.length} on Questions ›`, () => { void perform($, 'items') }, 'link', { small: true })) : null}
    </Box>
  )

  // ----- the numbers: documents, steps, and what is needed before filing; each opens its tab -----
  const metric = (key: string, id: string, value: string, label: string) => (
    <Box key={`metric-${key}`} flexDirection="column" gap="xs" flexGrow={1} flexShrink={1} width="30%" paddingX="sm">
      <Box flexDirection="row">
        <Button key={`metric-${key}`} plain label={`${label}: ${value}`} onPress={() => { void perform($, id) }}>
          <Text size={narrow ? 'heading' : 'title'} weight="semibold" color={NAVY} tabular>{value}</Text>
        </Button>
      </Box>
      <Text size="caption" color={MUTED}>{`${label} ›`}</Text>
    </Box>
  )
  const divider = (key: string) => <Box key={key} width={0} borderStyle="single" borderColor={LINE} />
  const metrics = (
    <Box key="metrics" flexDirection="column" gap="sm">
      {rule('metrics-top')}
      <Box flexDirection="row" alignItems="stretch" columnGap="sm">
        {metric('docs', 'docs', String(c.documents.count), c.documents.count === 1 ? 'Document' : 'Documents')}
        {divider('metric-div-1')}
        {metric('steps', 'packet', `${prg.done} of ${prg.total}`, 'Steps complete')}
        {divider('metric-div-2')}
        {metric('needed', 'items', String(blocking), 'Needed before filing')}
      </Box>
      {rule('metrics-bottom')}
    </Box>
  )

  // ----- the matter's details, folded: each summary as it used to stand on its row -----
  const docsRow = c.documents.count
    ? [plural(c.documents.count, 'file', 'files'), fresh.length ? `${fresh.length} new since the build` : '', docs.changed.length ? `${docs.changed.length} changed since the build` : '', c.documents.last_added ? `last added ${when(c.documents.last_added)}` : ''].filter(Boolean).join(' · ')
    : 'none yet'
  const running = prg.current?.status === 'in_progress'
  const packetRow = phase === 'draft' && ledger
    ? `Draft built · ${blocking} needed before filing`
    : phase === 'complete' || phase === 'filed'
      ? (c.outputs.packet ? 'Built and reviewed' : 'All steps done')
      : prg.done === 0 && !running
        ? `Not started · ${prg.total} steps`
        : `${prg.done} of ${prg.total} steps done${step ? ` · ${running ? 'now' : 'next'}: ${step.label}` : ''}`
  const notesCount = c.review_notes.length
  // "12 entries · last: Forms review passed, 2:14 PM"
  function timelineLine(m: Card): string {
    const newest = [...m.timeline].sort((a, b) => (b.at ?? '').localeCompare(a.at ?? ''))[0]
    return [plural(m.timeline.length, 'entry', 'entries'), newest ? `last: ${brief(newest.text, 70)} ${when(newest.at)}` : ''].filter(Boolean).join(' · ')
  }
  const detail = (key: string, label: string, value: string) => (
    <Box key={`detail-${key}`} flexDirection="row" flexWrap="wrap" columnGap="sm" rowGap="xs">
      <Box flexDirection="column" width={narrow ? '100%' : '24%'}><Text size="footnote" weight="semibold" color={NAVY}>{label}</Text></Box>
      <Box flexDirection="column" flexGrow={1} flexShrink={1}><Text size="footnote">{value}</Text></Box>
    </Box>
  )
  const details = [
    detail('case', 'Case', [c.case_line, c.intake.filing_posture_label].filter(Boolean).join(' · ') || 'Not chosen yet'),
    detail('docs', 'Documents', docsRow),
    detail('packet', 'Packet', `${packetRow}${!ledger && notesCount ? ` · ${plural(notesCount, 'review note', 'review notes')}` : ''}`),
    ledger ? detail('items', 'Open items', ledger.open.length ? `${itemsLine(ledger.counts)}${blocking ? ` · ${blocking} needed before filing` : ''}` : 'Nothing open') : null,
    c.outputs.memo ? detail('memo', 'Attorney memo', c.outputs.memo.modified ? `updated ${when(c.outputs.memo.modified)}` : 'ready to read') : null,
    requestReady ? detail('request', 'Client request', missingCount(c) ? `What the client still needs to send · ${plural(missingCount(c), 'item', 'items')} · ready to copy into an email` : 'Ready to copy into an email') : null,
    c.timeline.length ? detail('timeline', 'Timeline', timelineLine(c)) : null,
    links('links', [
      link('open-folder', 'Open the matter folder in Finder', () => { void perform($, 'open-folder') }, true),
      c.outputs.folder ? link('open-deliverables', 'Show files in Finder', () => { void perform($, 'open-deliverables') }, true) : null,
      c.outputs.earlier ? link('open-earlier', 'Show the earlier work in Finder', () => { void perform($, 'open-earlier') }, true) : null,
    ]),
  ]

  return matterPage(c, 'matter',
    tip,
    barCard('card-main', border, [
      eyebrow('Next step', 'next-eyebrow'),
      <Text key="next-title" size="title" weight="semibold" color={NAVY}>{title}</Text>,
      ...lines,
      asked === 'closeout'
        ? confirmBox('closeout', 'Delete Claude’s working copies of the client’s documents? Your documents and the finished files stay.', { id: 'closeout-yes', label: 'Yes, clean up' }, 'Keep them')
        : null,
      main.length ? actions(main, true) : null,
      links('main-links', extra),
      ...foot,
    ]),
    reportCard,
    sampleCard,
    metrics,
    columns('overview-cols', [attentionColumn, askColumn]),
    <Box key="folded" flexDirection="column" gap="md">
      {rule('folded-rule-1')}
      {!c.needs_intake && phase !== 'filed'
        ? disclosure('sec-instructions', 'Attorney instructions', savedInstructions ? 'Saved; Claude follows them' : 'None yet', open.includes('sec-instructions'), instructionsBody)
        : null}
      {!c.needs_intake && phase !== 'filed' ? rule('folded-rule-2') : null}
      {more.length ? disclosure('sec-more', 'More you can do', plural(more.length, 'action', 'actions'), open.includes('sec-more'), moreList) : null}
      {more.length ? rule('folded-rule-3') : null}
      {disclosure('sec-details', 'Matter details', '', open.includes('sec-details'), details)}
      {rule('folded-rule-4')}
    </Box>,
  )
}
