// Welcome: the first time, before any matter exists.
import type { EngineInterface } from 'claude-code'
import type { Ctx } from '../kit'

export async function welcomeScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  const { Box, Text, site, actions, band, topNav, card, page, body, folder, noProfile, tip, howItWorks, p } = x
  // The sample matter the server adds to a new Matters folder: a fictional case to try before a real one.
  const sample = p.matters.some(m => m.sample)
    ? [{ id: 'sample', label: 'Open the sample matter', kind: 'secondary' as const, detail: 'A fictional I-601A case to try first' }]
    : []
  return page(
    [band('Client documents in. Filing-ready packet out.', 'Senior Associate builds USCIS filing packets from a client’s documents, here in Claude.'), site === 'inline' ? topNav(null, '') : null],
    tip,
    body(
      card('How it works', howItWorks),
      actions(noProfile
        ? [
            { id: 'profile', label: 'Add your details', kind: 'primary', detail: '2 minutes, once' },
            { id: 'start', label: 'Start the first matter', kind: 'secondary', detail: 'Name the client and the case' },
            ...sample,
          ]
        : [{ id: 'start', label: 'Start the first matter', kind: 'primary', detail: 'Name the client and the case' }, ...sample]),
      <Box key="where" flexDirection="column" gap="xs">
        {folder ? <Text dimColor>Matters are kept in {folder}.</Text> : null}
        <Text dimColor>Type /matters any time to come back.</Text>
      </Box>,
    ),
  )
}
