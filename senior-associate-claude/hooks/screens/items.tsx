// What's left: the open items, grouped by who acts.
import type { EngineInterface } from 'claude-code'
import type { Card, OpenItem } from '../../types'
import type { Ctx } from '../kit'
import { ASK_ITEM, CLIENT_TYPES, ITEM_GROUPS, neededBeforeFiling, requestTranslations } from '../matter'
import { askAboutThis, askClaude, copyRequest, perform } from '../perform'
import { AMBER, ERROR_TEXT, OK_TEXT, WARN_TEXT } from '../theme'
import { ASK_LABEL, brief, nowMs, plural } from '../words'
import { matterStatus, isBusy } from '../status'

export async function itemsScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Button, allRuns, open, pillOf, card, link, links, noProfile, subpage } = x
  const ledger = c.open_items
  const openItems = ledger?.open ?? []
  // The matter page shows the answer boxes when Claude isn't at work on the matter.
  const shown = matterStatus(c, allRuns[c.path], nowMs())
  const answerable = !isBusy(shown) && shown.phase !== 'stopped'
  const line = (it: OpenItem) => {
    const mentionsDetails = /your details|attorney profile/i.test(`${it.title} ${it.detail}`)
    const isClient = it.type === 'client_document'
    // Each item's presses are named for it, so a screen reader hears "Mark done: Sign the G-28", not five "Mark done"s.
    const name = brief(it.type === 'attorney_decision' && it.question ? it.question : it.title, 80)
    return (
      <Box key={`item-${it.id}`} flexDirection="row" gap="sm" alignItems="flex-start">
        <Text color={it.blocks_filing ? ERROR_TEXT : WARN_TEXT} weight="bold">{it.type === 'risk' ? '◆' : '▲'}</Text>
        <Box flexDirection="column" flexGrow={1} flexShrink={1} gap="xs">
          <Text weight="semibold">{it.type === 'attorney_decision' && it.question ? it.question : it.title}</Text>
          {it.detail ? <Text dimColor>{brief(it.detail)}</Text> : null}
          {it.blocks_filing
            ? <Text color={ERROR_TEXT} size="caption" weight="medium">Needed before filing</Text>
            : it.type === 'attorney_decision' ? <Text size="caption" dimColor>Not needed before filing</Text> : null}
          {links(`acts-${it.id}`, [
            isClient ? link(`recv:${it.id}`, 'Received — Add files…', () => { void perform($, `recv:${it.id}`) }, true, `Received: ${name}. Add files…`) : null,
            it.type === 'attorney_action' && (!mentionsDetails || !noProfile) ? link(`done:${it.id}`, 'Mark done', () => { void perform($, `done:${it.id}`) }, true, `Mark done: ${name}`) : null,
            it.type === 'attorney_decision'
              ? answerable ? link(`answer:${it.id}`, 'Answer', () => { void perform($, `answer:${it.id}`) }, true, `Answer: ${name}`) : <Text key={`answer-later:${it.id}`} dimColor>Answer it on the matter page once Claude has finished.</Text>
              : null,
            it.type === 'client_question' ? link(`client-said:${it.id}`, 'The client answered — tell Claude', () => { void perform($, `client-said:${it.id}`) }, true, `The client answered: ${name}. Tell Claude`) : null,
            it.type === 'risk' ? link(`accept:${it.id}`, 'Accept this risk', () => { void perform($, `accept:${it.id}`) }, true, `Accept this risk: ${name}`) : null,
            mentionsDetails ? link(`details:${it.id}`, noProfile ? 'Add your details' : 'Your details', () => { void perform($, 'profile') }, true) : null,
            link(`ask-item:${it.id}`, 'Ask Claude about this', () => {
              void askAboutThis($, c, it.type === 'attorney_decision' && it.question ? it.question : it.title, ASK_ITEM[it.type] ?? 'What should we do about this?')
            }, false, `Ask Claude about: ${name}`),
          ])}
        </Box>
      </Box>
    )
  }
  const hasClientItems = openItems.some(it => CLIENT_TYPES.includes(it.type))
  // A list Claude wrote that can't be read is said as such, never as no list yet, with Claude to rewrite it.
  const damaged = !ledger && c.status.open_items_state === 'damaged'
  const rewrite = c.needs_you.find(n => n.key === 'open-items-damaged')?.ask ?? `Rewrite the open items list for ${c.name} from the review findings and the memo.`
  const resolvedItems = ledger?.resolved ?? []
  const showResolved = open.includes('resolved-group')
  const subtitle = ledger
    ? openItems.length ? `${plural(openItems.length, 'open item', 'open items')}, ${neededBeforeFiling(c).total} needed before filing` : 'Nothing open'
    : damaged ? 'The list can’t be read' : 'Nothing listed yet'
  return subpage(
    { title: c.name, subtitle, status: pillOf(c), back: { id: 'matter', label: c.name }, here: 'What’s left' },
    damaged
      ? card('Claude’s list of open items can’t be read', [
          <Text key="damaged">The file Claude keeps the list in is damaged, so what’s left can’t be shown. Claude can rewrite it from the review notes and the memo; this page shows it again once it’s done.</Text>,
          links('damaged-acts', [link('ask-rewrite', ASK_LABEL, () => { void askClaude($, rewrite) }, true, `${ASK_LABEL}: rewrite the list of open items`)]),
        ], AMBER, 'card-damaged')
      : !ledger
      ? card(null, [<Text key="none" dimColor>Claude writes this list when it reviews the documents or builds the packet: what the client still needs to send, what needs your decision, and what you need to do before filing.</Text>])
      : openItems.length === 0
        ? card(null, [<Text key="clear">Nothing is open. {ledger.packet_status === 'ready_to_file' ? 'The packet is ready to file once you’ve read it through.' : ''}</Text>])
        : null,
    ...ITEM_GROUPS.map(gr => {
      const group = openItems.filter(it => gr.types.includes(it.type))
      return group.length ? card(`${gr.title} · ${group.length}`, group.map(line)) : null
    }),
    hasClientItems && c.outputs.client_request
      ? links('request', [
          link('copy-request', 'Copy the client request', press => { void copyRequest($, press.surface) }, true),
          ...requestTranslations(c).map(t => link(`copy-request-lang:${t.language}`, `Copy it in ${t.language}`, () => { void perform($, `copy-request-lang:${t.language}`) })),
          link('show-request', 'Show the client request', () => { void perform($, 'request') }),
        ])
      : null,
    ledger && ledger.resolved_count
      ? <Box key="resolved" flexDirection="column" gap="sm">
          <Box flexDirection="row">
            <Button key="resolved-group" plain onPress={() => perform($, 'resolved-group')}>
              <Text weight="semibold">{`Resolved (${ledger.resolved_count}) ${showResolved ? '⌄' : '›'}`}</Text>
            </Button>
          </Box>
          {showResolved
            ? resolvedItems.length
              ? card(null, [
                  <Text key="res-what" dimColor>Settled by you or by Claude. Reopen puts one back on the list; Claude takes it up again on the next update.</Text>,
                  ...resolvedItems.map(it => (
                    <Box key={`res-${it.id}`} flexDirection="row" gap="sm" alignItems="flex-start">
                      <Text color={OK_TEXT} weight="bold">✓</Text>
                      <Box flexDirection="column" flexGrow={1} flexShrink={1} gap="xs">
                        <Text>{it.title}</Text>
                        {it.resolution ? <Text dimColor>{brief(it.resolution, 200)}</Text> : null}
                        {links(`res-acts-${it.id}`, [link(`reopen:${it.id}`, 'Reopen', () => { void perform($, `reopen:${it.id}`) }, true, `Reopen: ${brief(it.title, 80)}`)])}
                      </Box>
                    </Box>
                  )),
                ], undefined, 'card-resolved')
              : <Text key="res-none" dimColor>{`${plural(ledger.resolved_count, 'item is', 'items are')} resolved.`}</Text>
            : null}
        </Box>
      : null,
  )
}
