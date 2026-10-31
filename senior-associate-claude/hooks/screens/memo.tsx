// Attorney memo: the handoff, read right here.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { copyRequest, perform } from '../perform'
import { requestTranslations } from '../matter'

export async function memoScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Text, Markdown, pillOf, card, link, links, subpage } = x
  const text = c.memo_text ?? ''
  return subpage(
    { title: c.name, subtitle: 'Attorney memo', status: pillOf(c), back: { id: 'matter', label: c.name }, here: 'Attorney memo' },
    text
      ? card(null, [<Markdown key="memo" text={text} />])
      : card(null, [<Text key="none" dimColor>There’s no memo yet. Claude writes it at the end of every build or document review.</Text>]),
    text
      ? links('memo-actions', [
          link('open-memo', 'Open the memo file', () => { void perform($, 'open-memo') }),
          c.outputs.client_request ? link('show-request-memo', 'Show the client request', () => { void perform($, 'request') }) : null,
          c.outputs.client_request ? link('copy-request', 'Copy the client request', press => { void copyRequest($, press.surface) }) : null,
          ...requestTranslations(c).map(t => link(`copy-request-lang:${t.language}`, `Copy it in ${t.language}`, () => { void perform($, `copy-request-lang:${t.language}`) })),
        ])
      : null,
  )
}
