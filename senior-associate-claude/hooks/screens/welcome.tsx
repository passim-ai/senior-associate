// Welcome: the first time, before any matter exists. Matters, then the first matter's path in three steps, the
// sample to try, and where the documents stay.
import type { EngineInterface } from 'claude-code'
import type { Ctx } from '../kit'
import { perform } from '../perform'
import { ACCENT_TEXT, MUTED, HEAD } from '../theme'

export async function welcomeScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  const { Box, Text, narrow, actions, button, title, eyebrow, rule, page, body, folder, noProfile, tip, numbered, p } = x
  // The sample matter the server adds to a new Matters folder: a fictional case to try before a real one.
  const hasSample = p.matters.some(m => m.sample)
  const step = (num: string, heading: string, text: string) => (
    <Box key={`first-${num}`} flexDirection="column" gap="sm" flexGrow={1} flexShrink={1} minWidth={0} width={narrow ? '100%' : '30%'}>
      {rule(`first-rule-${num}`)}
      {narrow ? numbered(num, heading, text) : (
        <Box flexDirection="column" gap="xs" paddingTop="xs">
          <Text size="title" weight="semibold" color={ACCENT_TEXT} tabular>{num.padStart(2, '0')}</Text>
          <Text weight="semibold" color={HEAD}>{heading}</Text>
          <Text size="footnote">{text}</Text>
        </Box>
      )}
    </Box>
  )
  return page(
    [title('Matters', 'Client documents in. Filing-ready packet out.', actions(noProfile
      ? [
          { id: 'profile', label: 'Add your details', kind: 'primary', detail: '2 minutes, once' },
          { id: 'start', label: 'New matter', kind: 'secondary', detail: 'Name the client and the case' },
        ]
      : [{ id: 'start', label: 'New matter', kind: 'primary', detail: 'Name the client and the case' }]))],
    tip,
    body(
      rule('welcome-rule'),
      <Box key="first" flexDirection="column" gap="sm">
        {eyebrow('Your first matter')}
        <Text size="title" weight="semibold" color={HEAD}>A clear path from documents to review.</Text>
        <Text color={MUTED}>Senior Associate builds USCIS filing packets from a client’s documents, here in Claude. Nothing is filed or sent: you get a draft to read.</Text>
      </Box>,
      <Box key="first-steps" flexDirection={narrow ? 'column' : 'row'} columnGap="xl" rowGap="md" alignItems="flex-start">
        {step('1', 'Add the documents', 'Pick files one at a time, or a whole folder. Claude works from copies; your originals stay where they are.')}
        {step('2', 'Review what’s needed', 'A document review takes about 5–10 minutes: what’s missing, and the decisions only you can make.')}
        {step('3', 'Build and review', 'A full build takes about 1–1½ hours, in the background. Read the findings, then decide when it’s ready to file.')}
      </Box>,
      noProfile
        ? <Text key="details-why" size="footnote" color={MUTED}>Add your details first: your name, firm and bar number go on the G-28, each form’s preparer section and the letter’s signature.</Text>
        : null,
      hasSample
        ? <Box key="sample" flexDirection="column" gap="sm">
            {rule('sample-rule')}
            <Box flexDirection="row" flexWrap="wrap" justifyContent="space-between" alignItems="center" columnGap="lg" rowGap="sm">
              <Box flexDirection="row" gap="md" alignItems="flex-start" flexShrink={1} minWidth={0}>
                <Text color={ACCENT_TEXT} weight="semibold">✦</Text>
                <Box flexDirection="column" gap="xs" flexShrink={1} minWidth={0}>
                  <Text weight="semibold" color={HEAD}>See how it works</Text>
                  <Text size="footnote" color={MUTED}>A fictional I-601A case to try first</Text>
                </Box>
              </Box>
              <Box key="sample-actions" flexDirection="row">
                {button('main:sample', 'Open the sample matter', () => { void perform($, 'sample') }, 'secondary')}
              </Box>
            </Box>
          </Box>
        : null,
      rule('foot-rule'),
      <Box key="where" flexDirection="column" gap="xs">
        <Text size="caption" color={MUTED}>{`🔒 Documents stay in your Matters folder on this Mac${folder ? ` (${folder})` : ''}. Claude reads the files the work needs.`}</Text>
        <Text size="caption" color={MUTED}>Type /matters any time to come back.</Text>
      </Box>,
    ),
  )
}
