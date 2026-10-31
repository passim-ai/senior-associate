// Memo & request: the attorney memo and the client request, read right here, one at a time.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { markdown } from '../md'
import { copyMemo, copyRequest, perform } from '../perform'
import { requestTranslations } from '../matter'
import { LINE, MUTED, NAVY, SURFACE, WHITE } from '../theme'

// The two documents of the tab, side by side as one control: the one shown filled in navy.
export function readerToolbar($: EngineInterface, x: Ctx, which: 'memo' | 'request', right: (JSX.Element | null)[]): JSX.Element {
  const { Box, Text, Button } = x
  const seg = (key: string, id: string, label: string, on: boolean) => (
    <Box key={`segbx:${key}`} flexDirection="row" backgroundColor={on ? NAVY : SURFACE} borderStyle="round" borderColor={on ? NAVY : SURFACE} paddingX="md" paddingY="xs">
      <Button key={key} plain label={on ? `${label}, shown` : label} onPress={() => { void perform($, id) }}>
        <Text size="footnote" weight={on ? 'semibold' : 'medium'} color={on ? WHITE : MUTED}>{label}</Text>
      </Button>
    </Box>
  )
  return (
    <Box key="reader-toolbar" flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="lg" rowGap="sm">
      <Box flexDirection="row" backgroundColor={SURFACE} borderStyle="round" borderColor={LINE} padding="xs" gap="xs">
        {seg('seg-memo', 'memo', 'Attorney memo', which === 'memo')}
        {seg('request', 'request', 'Client request', which === 'request')}
      </Box>
      <Box flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">{right}</Box>
    </Box>
  )
}

export async function memoScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Text, card, eyebrow, button, link, links, matterPage } = x
  const text = c.memo_text ?? ''
  return matterPage(c, 'memo',
    readerToolbar($, x, 'memo', text
      ? [
          button('copy-memo', 'Copy memo', press => { void copyMemo($, press.surface) }, 'secondary', { small: true }),
          button('open-memo', 'Open the memo file', () => { void perform($, 'open-memo') }, 'secondary', { small: true }),
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
