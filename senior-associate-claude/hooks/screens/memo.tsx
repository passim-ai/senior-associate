// Memo & request: the attorney memo and the client request, read right here, one at a time.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { markdown } from '../md'
import { copyMemo, copyRequest, perform } from '../perform'
import { requestTranslations } from '../matter'

// The two documents of the tab, side by side as one control: the one shown is the app's main button.
export function readerToolbar($: EngineInterface, x: Ctx, which: 'memo' | 'request', right: (JSX.Element | null)[]): JSX.Element {
  const { Box, Button } = x
  const seg = (key: string, id: string, label: string, on: boolean) =>
    <Button key={key} label={label} variant={on ? 'primary' : undefined} onPress={() => { void perform($, id) }} />
  return (
    <Box key="reader-toolbar" flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="lg" rowGap="sm">
      <Box flexDirection="row" gap="xs">
        {seg('seg-memo', 'memo', 'Attorney memo', which === 'memo')}
        {seg('request', 'request', 'Client request', which === 'request')}
      </Box>
      <Box flexDirection="row" flexWrap="wrap" columnGap="sm" rowGap="xs" alignItems="center">{right}</Box>
    </Box>
  )
}

export async function memoScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Text, card, eyebrow, button, link, links, matterPage } = x
  const text = c.memo_text ?? ''
  return matterPage(c, 'memo',
    readerToolbar($, x, 'memo', text
      ? [
          button('copy-memo', 'Copy memo', press => { void copyMemo($, press.surface) }, 'secondary'),
          button('open-memo', 'Open the memo file', () => { void perform($, 'open-memo') }, 'secondary'),
        ]
      : []),
    text
      ? card(null, [eyebrow('Attorney work product', 'memo-eyebrow'), markdown(x, 'memo', text)], undefined, 'card-memo')
      : card(null, [<Text key="none" dimColor>There’s no memo yet. Claude writes it at the end of every build or document review.</Text>]),
    text && c.outputs.client_request
      ? links('memo-actions', [
          link('copy-request', 'Copy the client request', press => { void copyRequest($, press.surface) }, true),
          ...requestTranslations(c).map(t => link(`copy-request-lang:${t.language}`, `Copy it in ${t.language}`, () => { void perform($, `copy-request-lang:${t.language}`) })),
        ])
      : null,
  )
}
