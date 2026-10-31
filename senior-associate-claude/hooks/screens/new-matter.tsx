// New matter: the client's name, what is being filed, and how.
import type { EngineInterface } from 'claude-code'
import type { Ctx } from '../kit'
import { chosenCase, folderName, freeName } from '../matter'
import { createMatter, perform } from '../perform'
import { typed } from '../state'
import { AMBER } from '../theme'

export async function newMatterScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  const { Box, Text, Button, Input, p, d, open, missingCase, actions, card, subpage, caseChooser, postureChips, filingChoices } = x
  const chosen = chosenCase(p, d)
  const entered = typed.name.trim()
  const example = folderName(entered || 'Garcia', chosen?.short ?? '')
  const dupe = entered ? freeName(p, example) : { taken: null, next: example }
  const response = /\b(RFE|NOID)\b/.exec(d.posture || 'new filing packet')?.[1] ?? ''
  return subpage(
    { title: 'New matter', subtitle: 'Name the client and choose what is being filed. Claude takes it from there.', back: { id: 'all', label: 'Matters' }, here: 'New matter', foot: 'Back to matters' },
    card('Who is the client?', [
      <Input
        key="name"
        label="Client’s name"
        placeholder="e.g. Maria Garcia"
        submitLabel="Create"
        autoFocus
        value={typed.name || undefined}
        onInput={value => { typed.name = value }}
        onSubmit={value => createMatter($, value)}
      />,
      dupe.taken
        ? <Box key="dupe" flexDirection="column" gap="xs">
            <Text>{`You already have ${dupe.taken.name}. This one will be named “${dupe.next}”.`}</Text>
            <Box flexDirection="row"><Button key={`open:${dupe.taken.path}`} plain onPress={() => perform($, `open:${dupe.taken!.path}`)}><Text weight="medium">Open the existing matter</Text></Button></Box>
          </Box>
        : <Text key="hint" dimColor>The matter folder will be named “{example}”.</Text>,
    ]),
    card('What is being filed?', caseChooser(d, open, missingCase ? 'Choose one below, then press Create matter.' : '', {
      submitLabel: 'Create', onSubmit: () => { void createMatter($, typed.name) },
    }), missingCase ? AMBER : undefined, 'card-case'),
    card('New filing or a response?', [
      postureChips(d),
      response ? <Text key="response" dimColor>{`Add the ${response} notice along with the client’s documents.`}</Text> : null,
    ]),
    card('How it is filed', filingChoices(d, Boolean(p.catalog.matter_types.find(t => t.id === d.typeId)?.protected)), undefined, 'card-filing'),
    actions([{ id: 'create', label: 'Create matter', kind: 'primary', detail: chosen ? 'or press Enter' : 'Choose what is being filed first' }]),
  )
}
