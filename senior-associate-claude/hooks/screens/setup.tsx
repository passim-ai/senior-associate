// Getting set up: what this Mac needs, checked.
import type { EngineInterface } from 'claude-code'
import type { Check } from '../../types'
import type { Ctx } from '../kit'
import { requiredMissing } from '../matter'
import { askClaude, perform } from '../perform'
import { ERROR_TEXT, OK_TEXT, QUIET_TEXT, WARN_TEXT } from '../theme'
import { ASK_LABEL, MATTERS_ASK, NEW_FOLDER } from '../words'

export async function setupScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  const { Box, Text, Button, st, actions, card, subpage } = x
  const checks = st?.checks ?? []
  const missing = requiredMissing(st)
  const pending = st?.pending ?? null
  const recommended = (ch: Check) => (ch.level ? ch.level === 'recommended' : /profile|details/i.test(ch.id))
  const rowFor = (raw: Check) => {
    const ch = !raw.ok && !raw.ask && /matters/i.test(raw.id) ? { ...raw, ask: MATTERS_ASK, fix: raw.fix ?? NEW_FOLDER } : raw
    const optional = ch.level ? ch.level === 'optional' : !ch.required && !recommended(ch)
    const mark = ch.ok ? '✓' : optional ? '○' : '✗'
    const color = ch.ok ? OK_TEXT : optional ? QUIET_TEXT : ch.required ? ERROR_TEXT : WARN_TEXT
    const label = optional && !/optional/i.test(`${ch.label} ${ch.detail}`) ? `${ch.label} (optional)` : ch.label
    const detail = ch.detail ? ch.detail.charAt(0).toUpperCase() + ch.detail.slice(1) : ''
    const fix = !ch.ok && ch.fix && ch.fix !== ch.detail ? ch.fix : ''
    return (
      <Box key={`check-${ch.id}`} flexDirection="row" gap="sm" alignItems="flex-start">
        <Text color={color} weight="bold">{mark}</Text>
        <Box flexDirection="column" flexGrow={1} flexShrink={1} gap="xs">
          <Text weight="semibold">{label}</Text>
          {detail ? <Text>{detail}</Text> : null}
          {fix ? <Text dimColor>{fix}</Text> : null}
          {!ch.ok && ch.ask
            ? <Box flexDirection="row" gap="md" alignItems="center">
                <Button key={`ask:${ch.id}`} plain onPress={() => { void askClaude($, ch.ask!) }}><Text weight="medium">{ASK_LABEL}</Text></Button>
              </Box>
            : null}
          {!ch.ok && recommended(ch)
            ? <Box flexDirection="row"><Button key="setup-profile" plain onPress={() => perform($, 'profile')}><Text weight="medium">Add your details</Text></Button></Box>
            : null}
        </Box>
      </Box>
    )
  }
  const ready = missing.length === 0
  return subpage(
    { title: 'Getting set up', subtitle: 'Once, about 5 minutes.', back: { id: 'back-setup', label: 'Back' }, here: 'Getting set up', foot: null },
    checks.length
      ? card(null, checks.map(rowFor))
      : card(null, [<Text key="none" dimColor>Checking this Mac…</Text>]),
    checks.some(ch => !ch.ok && ch.ask)
      ? <Text key="how" dimColor>{`${ASK_LABEL} sends the request to Claude in the chat. Claude does the installing and asks before each step; choose Allow. When it’s done, press Check again.`}</Text>
      : null,
    actions(ready
      ? [
          { id: 'setup-continue', label: 'Continue', kind: 'primary', detail: pending ? 'Start the build' : 'Everything Claude needs is ready' },
          { id: 'setup-check', label: 'Check again', kind: 'secondary' },
        ]
      : [
          { id: 'setup-check', label: 'Check again', kind: 'primary', detail: 'After Claude installs what’s marked ✗' },
          { id: 'setup-continue', label: 'Continue anyway', kind: 'secondary', detail: pending ? 'Build without it' : 'Fix it later' },
        ]),
  )
}
