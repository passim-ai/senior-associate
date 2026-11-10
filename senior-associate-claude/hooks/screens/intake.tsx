// Change what is being filed: the case type and the posture, after the matter exists.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { chosenCase, metaChanged, shownName } from '../matter'
import { typed, updateDraft } from '../state'
import { WARN } from '../theme'
import { nowMs } from '../words'
import { CIRCUITS, saveJurisdiction } from '../perform'
import { matterStatus, isBusy } from '../status'

export async function intakeScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Input, field, chips, p, allRuns, d, open, missingCase, actions, card, subpage, caseChooser, postureChips, filingChoices } = x
  const types = p.catalog.matter_types
  const chosen = chosenCase(p, d)
  const posture = d.posture || 'new filing packet'
  const started = c.progress.stages.some(s => s.status !== 'pending') || Boolean(c.outputs.memo || c.open_items)
  const chosenType = chosen ? types.find(t => t.id === chosen.matterType)?.matter_type ?? chosen.matterType : ''
  const sameCase = chosenType.toLowerCase() === c.intake.matter_type.toLowerCase() && posture === (c.intake.filing_posture || 'new filing packet')
  const same = sameCase && !metaChanged(c, d)
  const label = d.typeId === 'other' ? (typed.other || d.other).trim() : types.find(t => t.id === d.typeId)?.label ?? ''
  const busyHere = isBusy(matterStatus(c, allRuns[c.path], nowMs()))
  return subpage(
    { title: shownName(c), subtitle: 'Change what is being filed', back: { id: 'intake-cancel', label: shownName(c) }, here: 'Change what is being filed' },
    card(null, [
      <Text key="now" weight="semibold">{`Now: ${[c.case_line, c.intake.filing_posture_label].filter(Boolean).join(' · ') || 'not chosen yet'}`}</Text>,
      <Text key="what">{started
        ? 'The steps start over for the new case, and your documents stay. The current packet, memo and open items are kept in the matter folder, not deleted.'
        : 'Nothing has run yet, so this only changes what Claude will build.'}</Text>,
      <Text key="name" dimColor>{`The matter keeps its name, ${shownName(c)}.`}</Text>,
    ]),
    card('What is being filed?', caseChooser(d, open, missingCase ? 'Choose one below, then press the button.' : '', {
      submitLabel: 'Use', onSubmit: value => { void updateDraft($, dd => ({ ...dd, other: value })) },
    }), missingCase ? WARN : undefined, 'card-case'),
    // Protected by its case type: a protected catalog entry, or (the server says) the case as it is recorded now.
    card('How it is filed', filingChoices(d, Boolean(types.find(t => t.id === d.typeId)?.protected) || (sameCase && c.meta.protected_reason === 'case_type')), undefined, 'card-filing'),
    card('New filing or a response?', [postureChips(d)]),
    card('Where the case is decided', [
      <Text key="jurisdiction-help" dimColor>Claude checks the case law of the federal circuit that governs this matter. Choose it from where the client lives or where the case is heard, not from your office address. Each choice saves as you make it.</Text>,
      field('Who decides it', label => <Input key="forum" label={label} placeholder="e.g. USCIS" submitLabel="Save" value={c.meta.forum || undefined} onSubmit={value => { void saveJurisdiction($, c, { forum: value }) }} />, 'jurisdiction-forum'),
      <Box key="circuit" flexDirection="column" gap="xs">
        <Text size="footnote" weight="medium">Federal circuit</Text>
        {chips('circuits', CIRCUITS.map(o => ({ id: `circuit:${o.id}`, label: o.label, chosen: (c.meta.circuit || '') === o.id })))}
      </Box>,
      field('Why that circuit applies', label => <Input key="jurisdiction_basis" label={label} placeholder="e.g. The client lives in Houston" submitLabel="Save" value={c.meta.jurisdiction_basis || undefined} onSubmit={value => { void saveJurisdiction($, c, { jurisdiction_basis: value }) }} />, 'jurisdiction-jurisdiction_basis'),
    ]),
    busyHere
      ? <Text key="intake-busy">Claude is working on this matter right now. Wait for it to finish, or stop it on the matter page, then come back.</Text>
      : actions([
          { id: 'intake-save', label: started && !sameCase ? 'Change and start over' : 'Save', kind: 'primary', detail: same ? 'Choose a different case or posture' : label ? `As ${label}` : 'Choose what is being filed first' },
          { id: 'intake-cancel', label: 'Cancel', kind: 'secondary', detail: 'Keep it as it is' },
        ]),
  )
}
