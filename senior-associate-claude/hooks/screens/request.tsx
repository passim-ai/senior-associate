// Client request: what the client still needs to send, read right here instead of in another app; and the language
// it is also written in for the client.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { requestTranslations } from '../matter'
import { markdown } from '../md'
import { perform } from '../perform'
import { typed } from '../state'
import { readerToolbar } from './memo'

// The languages most clients read, offered first; anything else under Other….
export const LANGUAGES = ['Spanish', 'Portuguese', 'French', 'Haitian Creole', 'Vietnamese', 'Chinese']

export async function requestScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Input, open, actions, card, eyebrow, chips, field, matterPage } = x
  const text = c.client_request_text ?? ''
  const language = c.meta.client_language
  const translations = requestTranslations(c)
  const translated = translations.find(t => t.language === language)?.text ?? ''
  const other = language !== 'English' && !LANGUAGES.includes(language)
  const typingOther = open.includes('lang-other') || other
  return matterPage(c, 'memo',
    readerToolbar($, x, 'request', []),
    text
      ? card(null, [eyebrow('For the client', 'request-eyebrow'), markdown(x, 'request', text)], undefined, 'card-request')
      : card(null, [<Text key="none" dimColor>There’s no client request yet. Claude writes it when it finishes a build or a document review.</Text>]),
    text
      ? actions([
          { id: 'copy-request', label: 'Copy the client request', kind: 'primary', detail: 'Plain text, ready to paste into an email' },
          ...translations.map(t => ({ id: `copy-request-lang:${t.language}`, label: `Copy it in ${t.language}`, kind: 'secondary' as const, detail: 'The same request, in the client’s language' })),
        ])
      : null,
    text ? <Text key="request-when" dimColor size="footnote">Claude rewrites it after every document review and update, so it always matches what’s still missing.</Text> : null,
    card('Also write it in', [
      <Text key="lang-what" dimColor size="footnote">{language === 'English'
        ? 'For a client who reads another language better, Claude writes the request in it too, from the next document review or update on. You always get the English one as well.'
        : translated
          ? `Claude writes it in ${language} as well as English.`
          : `Claude writes it in ${language} too, from the next document review or update on.`}</Text>,
      chips('langs', [
        { id: 'lang:English', label: 'English only', chosen: language === 'English' },
        ...LANGUAGES.map(l => ({ id: `lang:${l}`, label: l, chosen: language === l })),
        { id: 'lang-other', label: other ? `Other: ${language}` : 'Other…', chosen: other },
      ]),
      typingOther
        ? <Box key="lang-other-box" flexDirection="column">
            {field(<Input key="lang-other-input" label="Another language" placeholder="e.g. Tagalog" submitLabel="use" value={typed.language || (other ? language : undefined)} onInput={val => { typed.language = val }} onSubmit={val => { void perform($, `lang:${val.trim()}`) }} />)}
          </Box>
        : null,
    ], undefined, 'card-language'),
  )
}
