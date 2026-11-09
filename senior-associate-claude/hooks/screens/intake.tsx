// Change what is being filed: the case type and the posture, after the matter exists.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { chosenCase, metaChanged } from '../matter'
import { typed, updateDraft } from '../state'
import { WARN } from '../theme'
import { nowMs } from '../words'
import { setMeta } from '../perform'
import { matterStatus, isBusy } from '../status'

export async function intakeScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Text, Input, field, p, allRuns, d, open, missingCase, actions, card, subpage, caseChooser, postureChips, filingChoices } = x
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
    { title: c.name, subtitle: 'Change what is being filed', back: { id: 'intake-cancel', label: c.name }, here: 'Change what is being filed' },
    card(null, [
      <Text key="now" weight="semibold">{`Now: ${[c.case_line, c.intake.filing_posture_label].filter(Boolean).join(' · ') || 'not chosen yet'}`}</Text>,
      <Text key="what">{started
        ? 'The steps start over for the new case, and your documents stay. The current packet, memo and open items are kept in the matter folder, not deleted.'
        : 'Nothing has run yet, so this only changes what Claude will build.'}</Text>,
      <Text key="name" dimColor>{`The matter keeps its name, ${c.name}.`}</Text>,
    ]),
    card('What is being filed?', caseChooser(d, open, missingCase ? 'Choose one below, then press the button.' : '', {
      submitLabel: 'Use', onSubmit: value => { void updateDraft($, dd => ({ ...dd, other: value })) },
    }), missingCase ? WARN : undefined, 'card-case'),
    // Protected by its case type: a protected catalog entry, or (the server says) the case as it is recorded now.
    card('How it is filed', filingChoices(d, Boolean(types.find(t => t.id === d.typeId)?.protected) || (sameCase && c.meta.protected_reason === 'case_type')), undefined, 'card-filing'),
    card('New filing or a response?', [postureChips(d)]),
    card('Jurisdiction for this matter', [
      <Text key="jurisdiction-help" dimColor>Confirm the relevant forum and circuit from the matter’s venue and posture, not the attorney’s office address.</Text>,
      ...(['forum', 'circuit', 'jurisdiction_basis'] as const).map(key => field(
        key === 'forum' ? 'Forum' : key === 'circuit' ? 'Circuit (ca1–ca11, dc, federal, or none)' : 'Why this jurisdiction applies',
        label => <Input key={key} label={label} value={c.meta[key] || undefined} onSubmit={value => { void setMeta($, c, { [key]: value }) }} />, `jurisdiction-${key}`)),
    ]),
    busyHere
      ? <Text key="intake-busy">Claude is working on this matter right now. Wait for it to finish, or stop it on the matter page, then come back.</Text>
      : actions([
          { id: 'intake-save', label: started && !sameCase ? 'Change and start over' : 'Save', kind: 'primary', detail: same ? 'Choose a different case or posture' : label ? `As ${label}` : 'Choose what is being filed first' },
          { id: 'intake-cancel', label: 'Cancel', kind: 'secondary', detail: 'Keep it as it is' },
        ]),
  )
}
