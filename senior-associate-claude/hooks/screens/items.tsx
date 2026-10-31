// Questions: the decisions only the attorney can make, each with Claude's suggested approach and a box for the answer;
// then what the client owes, what the attorney has to do and the risks to weigh, each with what to do about it; then
// what is settled; and at the foot, the press that takes the saved answers to Claude.
import type { EngineInterface } from 'claude-code'
import type { Card, OpenItem } from '../../types'
import type { ActionButton, Ctx } from '../kit'
import { ASK_ITEM, CLIENT_TYPES, ITEM_GROUPS, builtPast, docChanges, needsOf, neededBeforeFiling, replyKey, reportQuestions, requestTranslations } from '../matter'
import type { Need } from '../matter'
import { askAboutThis, askClaude, copyRequest, perform } from '../perform'
import { answerFor, saveAnswer, savedAnswerFor } from '../runs'
import { typed } from '../state'
import { ACCENT, ACCENT_TEXT, ERROR, HEAD, MUTED, OK, WARN } from '../theme'
import { ASK_LABEL, brief, nowMs, plural } from '../words'
import { matterStatus, isBusy } from '../status'

export async function itemsScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Input, allRuns, open, savedAnswers, noProfile, card, section, barCard, rule, pill, button, lone, link, links, field, savedMark, actions, matterPage } = x
  const ledger = c.open_items
  const openItems = ledger?.open ?? []
  // Answers are taken while Claude isn't at work on the matter.
  const shown = matterStatus(c, allRuns[c.path], nowMs())
  const answerable = !isBusy(shown) && shown.phase !== 'stopped'
  const needs = needsOf(c)
  const docs = docChanges(c)
  const arrived = docs.added.length + docs.changed.length
  const built = builtPast(c) || shown.phase === 'needs_you'
  // The button that takes the saved answers to Claude, as the saved line names it.
  const sendWith = built ? 'Update the packet' : arrived ? 'Review the documents again or Build packet' : 'Build packet'

  // ----- the attorney's decisions: Claude's questions and the open items that are decisions, each once -----
  const decisions: (Need & { item?: OpenItem })[] = []
  const seen = new Set<string>()
  for (const n of needs.filter(n => n.who === 'attorney')) {
    seen.add(n.qkey)
    decisions.push({ ...n, item: openItems.find(it => it.id === n.qkey) })
  }
  for (const it of openItems.filter(it => it.type === 'attorney_decision' && !seen.has(it.id))) {
    decisions.push({
      i: -1, key: `${c.path}#${it.id}`, qkey: it.id, blocks: it.blocks_filing, id: it.id, who: 'attorney', question: it.question || it.title,
      detail: it.detail ? brief(it.detail) : '', recommendation: it.recommendation ? brief(it.recommendation, 160) : '', stage: '', fix: '', ask: '', item: it,
    })
  }
  decisions.sort((a, b) => Number(b.blocks) - Number(a.blocks))
  // Before the matter keeps open items, a report that ends in questions is how Claude asks.
  const run = allRuns[c.path]
  const reportAsks = shown.phase === 'needs_you' && run?.status === 'done' && Boolean(run.answer)
  const asked = reportAsks && !decisions.length ? reportQuestions(run!.answer) : []
  const answeredCount = decisions.filter(d => answerFor(c, d.qkey, savedAnswers).trim()).length

  const answerBox = (inputKey: string, qkey: string, akey: string, question: string, number: number) => {
    const value = answerFor(c, qkey, savedAnswers)
    return [
      field(`Your answer to question ${number}`, l => <Input
        key={inputKey}
        label={l}
        placeholder="Record your decision and any conditions…"
        rows={3}
        value={value || undefined}
        onInput={val => { typed.answers[akey] = val }}
        onSubmit={val => { void saveAnswer($, c, qkey, question, val, sendWith) }}
      />, `field-${inputKey}`),
      <Box key={`save-row-${inputKey}`} flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">
        {button(`save-answer:${qkey}`, 'Save answer', () => { void saveAnswer($, c, qkey, question, typed.answers[akey] ?? value, sendWith) }, 'primary')}
        {savedMark(akey, value === savedAnswerFor(c, qkey, savedAnswers))}
      </Box>,
    ]
  }

  const decisionRow = (dn: Need & { item?: OpenItem }, k: number) => (
    <Box key={`item-${dn.qkey}`} flexDirection="column" gap="sm">
      {k ? rule(`dec-rule-${dn.qkey}`) : null}
      <Box flexDirection="row" gap="md" alignItems="flex-start">
        <Box flexDirection="row" flexShrink={0}><Text size="heading" weight="semibold" color={ACCENT_TEXT} tabular>{String(k + 1).padStart(2, '0')}</Text></Box>
        <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
          <Text weight="semibold" color={HEAD}>{dn.question}</Text>
          {dn.blocks ? <Text color={ERROR} size="caption" weight="medium">Needed before filing</Text> : <Text size="caption" dimColor>Not needed before filing</Text>}
          {dn.detail && dn.detail !== dn.question ? <Text dimColor size="footnote">{dn.detail}</Text> : null}
        </Box>
      </Box>
      {dn.recommendation
        ? barCard(`rec-${dn.qkey}`, ACCENT, [
            <Text key="rec-head" size="footnote" weight="semibold" color={HEAD}>Suggested approach</Text>,
            <Text key="rec-text" size="footnote">{`Recommended: ${dn.recommendation}`}</Text>,
            answerable ? lone(`rec:${dn.qkey}`, button(`rec:${dn.qkey}`, 'Use the recommendation', () => { void perform($, `rec:${dn.qkey}`) }, 'secondary')) : null,
          ])
        : null}
      {answerable
        ? answerBox(`answer-${dn.qkey}`, dn.qkey, dn.key, dn.question, k + 1)
        : <Text key={`answer-later:${dn.qkey}`} dimColor size="footnote">You can answer it here once Claude has finished.</Text>}
      {links(`dec-acts-${dn.qkey}`, [
        link(`ask-item:${dn.qkey}`, 'Ask Claude about this', () => {
          void askAboutThis($, c, dn.question, ASK_ITEM.attorney_decision ?? 'What should we do about this?')
        }, false),
      ])}
    </Box>
  )

  // Claude's questions from its report, when it had no list to put them on: one box each, or one for them all.
  const reportRows = asked.map((q, k) => (
    <Box key={`item-report-${k}`} flexDirection="column" gap="sm">
      {k ? rule(`rq-rule-${k}`) : null}
      <Box flexDirection="row" gap="md" alignItems="flex-start">
        <Box flexDirection="row" flexShrink={0}><Text size="heading" weight="semibold" color={ACCENT_TEXT} tabular>{String(k + 1).padStart(2, '0')}</Text></Box>
        <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0}><Text weight="semibold" color={HEAD}>{q}</Text></Box>
      </Box>
      {answerable ? answerBox(`rq-${k}`, `report-${k}`, `${c.path}#report-${k}`, q, k + 1) : null}
    </Box>
  ))
  const replyBox = reportAsks && !decisions.length && !asked.length && answerable
    ? (() => {
        const key = replyKey(c)
        const value = answerFor(c, 'reply', savedAnswers)
        return (
          <Box key="reply-box" flexDirection="column" gap="sm">
            <Text>Claude asked its questions in its report, on the Overview. Answer them here, in one box.</Text>
            {field('Your answers', l => <Input key="reply" label={l} placeholder="Your answers to Claude’s questions" rows={3} submitLabel="Save" value={value || undefined} onInput={val => { typed.answers[key] = val }} onSubmit={val => { void saveAnswer($, c, 'reply', 'Claude’s questions in its report', val, 'Update the packet') }} />)}
            {savedMark(key, value === savedAnswerFor(c, 'reply', savedAnswers))}
          </Box>
        )
      })()
    : null

  // ----- every other open item, by who acts -----
  const line = (it: OpenItem) => {
    const mentionsDetails = /your details|attorney profile/i.test(`${it.title} ${it.detail}`)
    const isClient = it.type === 'client_document'
    return (
      <Box key={`item-${it.id}`} flexDirection="row" gap="sm" alignItems="flex-start">
        <Text color={it.blocks_filing ? ERROR : WARN} weight="bold">{it.type === 'risk' ? '◆' : '▲'}</Text>
        <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
          <Text weight="semibold" color={HEAD}>{it.title}</Text>
          {it.detail ? <Text dimColor size="footnote">{brief(it.detail)}</Text> : null}
          {it.blocks_filing ? <Text color={ERROR} size="caption" weight="medium">Needed before filing</Text> : null}
          {links(`acts-${it.id}`, [
            isClient ? link(`recv:${it.id}`, 'Received — Add files…', () => { void perform($, `recv:${it.id}`) }, true) : null,
            it.type === 'attorney_action' && (!mentionsDetails || !noProfile) ? link(`done:${it.id}`, 'Mark done', () => { void perform($, `done:${it.id}`) }, true) : null,
            it.type === 'client_question' ? link(`client-said:${it.id}`, 'The client answered — tell Claude', () => { void perform($, `client-said:${it.id}`) }, true) : null,
            it.type === 'risk' ? link(`accept:${it.id}`, 'Accept this risk', () => { void perform($, `accept:${it.id}`) }, true) : null,
            mentionsDetails ? link(`details:${it.id}`, noProfile ? 'Add your details' : 'Your details', () => { void perform($, 'profile') }, true) : null,
            link(`ask-item:${it.id}`, 'Ask Claude about this', () => {
              void askAboutThis($, c, it.title, ASK_ITEM[it.type] ?? 'What should we do about this?')
            }, false),
          ])}
        </Box>
      </Box>
    )
  }
  const hasClientItems = openItems.some(it => CLIENT_TYPES.includes(it.type))
  // What the client owes that Claude asked in its questions rather than on the list.
  const clientNeeds = needs.filter(n => n.who === 'client' && !openItems.some(it => it.id === n.qkey))
  // A list Claude wrote that can't be read is said as such, never as no list yet, with Claude to rewrite it.
  const damaged = !ledger && c.status.open_items_state === 'damaged'
  const rewrite = c.needs_you.find(nn => nn.key === 'open-items-damaged')?.ask ?? `Rewrite the open items list for ${c.name} from the review findings and the memo.`
  const resolvedItems = ledger?.resolved ?? []
  const showResolved = open.includes('resolved-group')
  const needed = neededBeforeFiling(c).total
  const anything = decisions.length || asked.length || replyBox || openItems.length || clientNeeds.length

  const foot: ActionButton | null = answerable && (decisions.length || asked.length || replyBox)
    ? built
      ? { id: 'update', label: 'Update the packet with saved answers', kind: 'primary', detail: 'Claude works your saved answers in and checks the packet again' }
      : { id: 'build', label: 'Build packet', kind: 'primary', detail: 'Your saved answers go with the build' }
    : null

  return matterPage(c, 'items',
    section('Questions & missing evidence', [
      <Text key="q-status" weight="medium" color={HEAD}>{ledger
        ? openItems.length ? `${plural(openItems.length, 'open item', 'open items')}, ${needed} needed before filing` : 'Nothing open'
        : damaged ? 'The list can’t be read' : decisions.length || asked.length ? plural(decisions.length || asked.length, 'question', 'questions') : 'Nothing listed yet'}</Text>,
      <Text key="q-what" dimColor>{built ? 'Save your decisions here, then update the packet to apply them.' : 'Save your decisions here; they go with the build.'}</Text>,
    ], 'sec-questions', needed ? pill(`${needed} needed before filing`, 'accent', 'needed-pill') : null),
    damaged
      ? card('Claude’s list of open items can’t be read', [
          <Text key="damaged">The file Claude keeps the list in is damaged, so what’s left can’t be shown. Claude can rewrite it from the review notes and the memo; this page shows it again once it’s done.</Text>,
          links('damaged-acts', [link('ask-rewrite', ASK_LABEL, () => { void askClaude($, rewrite) }, true)]),
        ], WARN, 'card-damaged')
      : !anything
        ? ledger
          ? card(null, [<Text key="clear">Nothing is open. {ledger.packet_status === 'ready_to_file' ? 'The packet is ready to file once you’ve read it through.' : ''}</Text>])
          : card(null, [<Text key="none" dimColor>Claude writes this list when it reviews the documents or builds the packet: what the client still needs to send, what needs your decision, and what you need to do before filing.</Text>])
        : null,
    decisions.length || asked.length || replyBox
      ? section(decisions.length > 1 ? `Attorney decisions · ${answeredCount} of ${decisions.length} answered` : 'Attorney decisions', [
          ...decisions.map(decisionRow),
          ...reportRows,
          replyBox,
        ], 'sec-decisions')
      : null,
    ...ITEM_GROUPS.filter(gr => !gr.types.includes('attorney_decision')).map(gr => {
      const group = openItems.filter(it => gr.types.includes(it.type))
      return group.length ? section(`${gr.title} · ${group.length}`, [rule(`grp-rule-${gr.title}`), ...group.map(line)], `grp-${gr.title}`) : null
    }),
    clientNeeds.length
      ? section('Waiting on the client', [
          ...clientNeeds.map(nn => <Text key={`cl-${nn.i}`}>{`• ${nn.question}`}</Text>),
          links('client-acts', [link('client-add', 'Client sent it? Add files…', () => { void perform($, 'add-files') }, true)]),
        ], 'sec-client')
      : null,
    hasClientItems && c.outputs.client_request
      ? links('request', [
          link('copy-request', 'Copy the client request', press => { void copyRequest($, press.surface) }, true),
          ...requestTranslations(c).map(t => link(`copy-request-lang:${t.language}`, `Copy it in ${t.language}`, () => { void perform($, `copy-request-lang:${t.language}`) })),
          link('show-request', 'Show the client request', () => { void perform($, 'request') }),
        ])
      : null,
    ledger && ledger.resolved_count
      ? <Box key="resolved" flexDirection="column" gap="sm">
          {lone('resolved-group', button('resolved-group', `Resolved (${ledger.resolved_count}) ${showResolved ? '⌄' : '›'}`, () => { void perform($, 'resolved-group') }, 'link'))}
          {showResolved
            ? resolvedItems.length
              ? card(null, [
                  <Text key="res-what" dimColor size="footnote">Settled by you or by Claude. Reopen puts one back on the list; Claude takes it up again on the next update.</Text>,
                  ...resolvedItems.map(it => (
                    <Box key={`res-${it.id}`} flexDirection="row" gap="sm" alignItems="flex-start">
                      <Text color={OK} weight="bold">✓</Text>
                      <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
                        <Text>{it.title}</Text>
                        {it.resolution ? <Text dimColor size="footnote">{brief(it.resolution, 200)}</Text> : null}
                        {links(`res-acts-${it.id}`, [link(`reopen:${it.id}`, 'Reopen', () => { void perform($, `reopen:${it.id}`) }, true)])}
                      </Box>
                    </Box>
                  )),
                ], undefined, 'card-resolved')
              : <Text key="res-none" dimColor>{`${plural(ledger.resolved_count, 'item is', 'items are')} resolved.`}</Text>
            : null}
        </Box>
      : null,
    foot
      ? <Box key="update-bar" flexDirection="column" gap="md">
          {rule('update-rule')}
          <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="lg" rowGap="sm">
            <Box flexDirection="column" gap="xs" flexShrink={1} minWidth={0}>
              <Text weight="semibold" color={HEAD}>Ready to use your answers?</Text>
              <Text size="footnote" color={MUTED}>{built ? 'Saved answers are worked in the next time you update the packet.' : 'Saved answers go with the build.'}</Text>
            </Box>
            {actions([foot])}
          </Box>
        </Box>
      : null,
  )
}
