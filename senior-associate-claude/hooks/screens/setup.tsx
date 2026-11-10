// Getting set up: what this Mac needs, checked.
import type { EngineInterface } from 'claude-code'
import type { Check } from '../../types'
import type { Ctx } from '../kit'
import { requiredMissing } from '../matter'
import { askClaude, perform } from '../perform'
import { ERROR, HEAD, MUTED, OK, WARN } from '../theme'
import { ASK_LABEL, MATTERS_ASK, NEW_FOLDER } from '../words'

export async function setupScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  const { Box, Text, st, actions, button, links, card, rule, subpage, research } = x
  // The research line as it stands now: Passim may have answered about the account since the check ran.
  const checks = (st?.checks ?? []).map(ch => (ch.id === 'research' && research ? research : ch))
  const missing = requiredMissing(st)
  const pending = st?.pending ?? null
  const recommended = (ch: Check) => (ch.level ? ch.level === 'recommended' : /profile|details/i.test(ch.id))
  const rowFor = (raw: Check, i: number) => {
    const ch = !raw.ok && !raw.ask && /matters/i.test(raw.id) ? { ...raw, ask: MATTERS_ASK, fix: raw.fix ?? NEW_FOLDER } : raw
    const optional = ch.level ? ch.level === 'optional' : !ch.required && !recommended(ch)
    const mark = ch.ok ? '✓' : optional ? '○' : '✗'
    const color = ch.ok ? OK : optional ? MUTED : ch.required ? ERROR : WARN
    const label = optional && !/optional/i.test(`${ch.label} ${ch.detail}`) ? `${ch.label} (optional)` : ch.label
    const detail = ch.detail ? ch.detail.charAt(0).toUpperCase() + ch.detail.slice(1) : ''
    const fix = !ch.ok && ch.fix && ch.fix !== ch.detail ? ch.fix : ''
    return (
      <Box key={`check-${ch.id}`} flexDirection="column" gap="sm">
        {i ? rule(`check-rule-${ch.id}`) : null}
        <Box flexDirection="row" gap="md" alignItems="flex-start">
          <Text color={color} weight="bold">{mark}</Text>
          <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
            <Text weight="semibold" color={HEAD}>{label}</Text>
            {detail ? <Text size="footnote">{detail}</Text> : null}
            {fix ? <Text dimColor size="footnote">{fix}</Text> : null}
            {links(`check-acts-${ch.id}`, [
              !ch.ok && ch.ask ? button(`ask:${ch.id}`, ASK_LABEL, () => { void askClaude($, ch.ask!) }, 'link') : null,
              !ch.ok && recommended(ch) ? button('setup-profile', 'Add your details', () => { void perform($, 'profile') }, 'link') : null,
              !ch.ok && ch.link ? button(`setup-link:${ch.link.id}`, `${ch.link.label} ›`, () => { void perform($, `open-link:${ch.link!.id}`) }, 'link') : null,
              !ch.ok && ch.id === 'research' && ch.link?.id === 'passim_trial' ? button('setup-link:connectors', 'Open Claude’s Connectors ›', () => { void perform($, 'open-link:connectors') }, 'quiet') : null,
            ])}
          </Box>
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
      ? <Text key="how" dimColor size="footnote">{`${ASK_LABEL} sends the request to Claude in the chat. Claude does the installing and asks before each step; choose Allow. When it’s done, press Check again.`}</Text>
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
