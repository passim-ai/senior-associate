// Packet: every step, the review notes, the finished files.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { ASK_NOTE, STAGE_ABOUT, STAGE_WORD, noteLine, noteTone, reviewOnly, trackSvg } from '../matter'
import { askAboutThis, perform } from '../perform'
import { HEAD, MUTED, STAGE_TEXT, WARN } from '../theme'
import { brief, dateOnly, nowMs, plural } from '../words'
import { matterStatus, isBusy } from '../status'
import { typed } from '../state'

export async function packetScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Input, field, isDesktop, svg, allRuns, actions, button, lone, section, rule, link, links, matterPage, research } = x
  const prg = c.progress
  const notes = c.review_notes
  const NOTES_SHOWN = 40
  const forms = c.outputs.forms ?? []
  const live = isBusy(matterStatus(c, allRuns[c.path], nowMs()))
  // Any step that has run can be redone: it and every step after it. Not while Claude is at work on the matter.
  const redoable = (status: string) => !live && status !== 'pending'
  const files = c.outputs.packet || c.outputs.cover_letter || forms.length > 0
  // The attorney's sign-off on this version: what makes it impossible (nothing assembled), what to weigh first.
  const fr = c.filing_readiness ?? null
  const open_points = fr?.risks ?? []
  // When the law the letter cites was last checked, said beside the approval, with the way to check it again.
  const rs = c.research ?? null
  const lawLine = rs ? `The law the letter cites: ${rs.headline.charAt(0).toLowerCase()}${rs.headline.slice(1)}${rs.state === 'checked' && rs.age_days !== null ? ` (${rs.age_days === 0 ? 'today' : rs.age_days === 1 ? 'yesterday' : `${rs.age_days} days ago`})` : ''}.` : ''
  return matterPage(c, 'packet',
    fr && files ? section('Approve for filing', [
      // Approved: this exact version, by whom and when, and what was open when they approved.
      fr.approved
        ? <Text key="approval-state">{`${fr.attorney ? `${fr.attorney} approved` : 'You approved'} this version for filing${fr.approved_at ? ` on ${dateOnly(fr.approved_at)}` : ''}. The clean copies, without the DRAFT marking, are in the matter’s folder under Approved for filing. If the packet or the client’s documents change, the new version needs approving again.`}</Text>
        : fr.eligible
          ? <Text key="approval-state">{open_points.length
              ? `Every page of the packet is marked DRAFT until you approve it. You can approve it as it is; ${plural(open_points.length, 'point is', 'points are')} open first, and your reason for filing with ${open_points.length === 1 ? 'it' : 'them'} open is kept with the approval.`
              : 'Every page of the packet is marked DRAFT until you approve it. Read it through, then approve: clean copies without the marking go in the matter’s folder. Nothing is filed or sent.'}</Text>
          : <Text key="approval-state">This version can’t be approved yet.</Text>,
      ...(fr.approved ? [] : fr.blockers).map((text, i) => <Text key={`approval-block-${i}`} color={WARN}>{text}</Text>),
      open_points.length
        ? <Box key="approval-points" flexDirection="column" gap="xs">
            {fr.approved ? <Text dimColor size="footnote">Open when you approved:</Text> : null}
            {open_points.map((text, i) => <Text key={`approval-risk-${i}`} size="footnote" dimColor={fr.approved ? true : undefined}>{`• ${text}`}</Text>)}
            {fr.approved && fr.risk_note ? <Text dimColor size="footnote">{`Your reason: ${fr.risk_note}`}</Text> : null}
          </Box>
        : null,
      open_points.length && fr.eligible && !fr.approved ? field(`Why you’re filing with ${open_points.length === 1 ? 'this' : 'these'} open`, label => <Input key="filing-risk-note" label={label} placeholder="e.g. The client’s deadline is Friday; the tax transcript follows by interfiling." rows={2} value={typed.answers[`${c.path}#filing-risk`] || undefined} onInput={value => { typed.answers[`${c.path}#filing-risk`] = value }} onSubmit={value => { typed.answers[`${c.path}#filing-risk`] = value }} />, 'filing-risk') : null,
      rs && !fr.approved
        ? <Box key="approval-law" flexDirection="row" flexWrap="wrap" columnGap="md" rowGap="xs" alignItems="center">
            <Text size="footnote">{lawLine}</Text>
            {!live && research?.ok && rs.state !== 'without' ? button('approval-recheck', 'Check the law again ›', () => { void perform($, 'recheck') }, 'link') : null}
            {!live && research?.ok && rs.state === 'without' ? button('approval-redo-research', 'Redo the research with BIA Edge ›', () => { void perform($, 'redo:cover_letter_researcher') }, 'link') : null}
            {research && !research.ok && research.link ? button(`approval-link:${research.link.id}`, `${research.link.label} ›`, () => { void perform($, `open-link:${research.link!.id}`) }, 'link') : null}
          </Box>
        : null,
      live && fr.eligible && !fr.approved ? <Text key="approval-live" dimColor size="footnote">Claude is working on this matter now; approve once it has finished.</Text> : null,
      !live && fr.eligible && !fr.approved
        ? lone('approve-filing', button('approve-filing', 'Approve this version for filing', () => { void perform($, 'approve-filing') }, 'primary')) : null,
      fr.approved ? lone('open-approved-packet', button('open-approved-packet', 'Show the approved copies', () => { void perform($, 'open-approved-packet') }, 'primary')) : null,
    ], 'sec-approval') : null,
    files
      ? section('Files for this matter', [
          rule('files-rule'),
          c.outputs.packet ? <Text key="pk" weight="medium">{c.outputs.packet.name}</Text> : null,
          c.outputs.paper_packet ? <Text key="pp" weight="medium">{`${c.outputs.paper_packet.name}: the forms that go on paper`}</Text> : null,
          c.outputs.cover_letter ? <Text key="cl" weight="medium">{c.outputs.cover_letter.name}</Text> : null,
          forms.length ? <Text key="forms-head" dimColor size="footnote">Forms (each opens on its own):</Text> : null,
          forms.length ? links('forms', forms.map(f => link(`open-form:${f.name}`, f.name.replace(/\.pdf$/i, ''), () => { void perform($, `open-form:${f.name}`) }, true))) : null,
          actions([
            ...(c.outputs.packet ? [{ id: 'open-packet', label: 'Open packet', kind: 'primary' as const }] : []),
            ...(c.outputs.cover_letter ? [{ id: 'open-letter', label: 'Open cover letter', kind: 'secondary' as const }] : []),
          ]),
          links('dl', [
            c.outputs.filing_checklist ? link('print-checklist', 'Print the filing checklist', () => { void perform($, 'print-checklist') }, true) : null,
            c.outputs.upload_files ? link('upload-files', 'Show the files to upload in Finder', () => { void perform($, 'upload-files') }) : null,
            c.outputs.paper_packet ? link('open-paper-packet', 'Open the paper part', () => { void perform($, 'open-paper-packet') }) : null,
            c.outputs.folder ? link('open-deliverables', 'Show the files in Finder', () => { void perform($, 'open-deliverables') }) : null,
          ]),
        ], 'sec-files')
      : null,
    section('Steps', [
      <Text key="steps-done" weight="medium" color={HEAD}>{`${prg.done} of ${prg.total} steps done`}</Text>,
      <Text key="steps-what" dimColor size="footnote">{live
        ? 'Each step is done by its own specialist, and the reviews are independent. Claude is working on this matter now; you can redo a step once it’s done.'
        : 'Each step is done by its own specialist, and the reviews are independent. To change something, redo a step: Claude redoes it and every step after it, and keeps the ones before.'}</Text>,
      isDesktop ? <Box key="track" flexDirection="column">{svg(trackSvg(prg.stages), `${prg.done} of ${prg.total} steps done`)}</Box> : null,
      rule('steps-rule'),
      ...prg.stages.map((s, i) => {
        return (
          <Box key={s.id} flexDirection="row" gap="md" alignItems="flex-start">
            <Box flexDirection="row" flexShrink={0} width={3}>
              <Text color={STAGE_TEXT[s.status] ?? MUTED} weight="semibold" tabular>{s.status === 'passed' ? '✓' : String(i + 1).padStart(2, '0')}</Text>
            </Box>
            <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
              <Box flexDirection="row" columnGap="sm" rowGap="xs" flexWrap="wrap" alignItems="center">
                <Text weight={s.status === 'in_progress' ? 'semibold' : 'medium'} color={HEAD}>{s.label}</Text>
                <Text color={STAGE_TEXT[s.status] ?? MUTED} size="footnote">{s.status === 'passed'
                  ? (notes.some(n => n.stage_label === s.label) ? 'Completed with findings' : 'Completed')
                  : STAGE_WORD[s.status] ?? s.status}</Text>
                {redoable(s.status)
                  ? button(`redo:${s.id}`, s.id === 'docs_review' && reviewOnly(c) ? 'Review again ›' : 'Redo from here ›', () => { void perform($, `redo:${s.id}`) }, 'link')
                  : null}
              </Box>
              {STAGE_ABOUT[s.id] ? <Text dimColor size="footnote">{STAGE_ABOUT[s.id]}</Text> : null}
            </Box>
          </Box>
        )
      }),
    ], 'sec-steps'),
    notes.length > 0
      ? section(`Review notes · ${notes.length} open`, [
          <Text key="what" dimColor size="footnote">What the independent reviews found. Anything you need to act on is also on Questions.</Text>,
          rule('notes-rule'),
          ...notes.slice(0, NOTES_SHOWN).map((f, i) => (
            <Box key={`f-${i}`} flexDirection="row" gap="sm" alignItems="flex-start">
              <Text color={noteTone(f)} weight="bold">▲</Text>
              <Box flexDirection="column" flexGrow={1} flexShrink={1} minWidth={0} gap="xs">
                <Text weight="medium">{f.title}</Text>
                {f.detail && f.detail !== f.title ? <Text dimColor size="footnote">{brief(f.detail)}</Text> : null}
                <Text dimColor size="footnote">{noteLine(f)}</Text>
                {links(`note-acts-${i}`, [link(`ask-note:${i}`, 'Ask Claude about this', () => { void askAboutThis($, c, f.title, ASK_NOTE) }, false)])}
              </Box>
            </Box>
          )),
          notes.length > NOTES_SHOWN
            ? <Text key="notes-more" dimColor>{`…and ${notes.length - NOTES_SHOWN} more. The memo lists every one; Ask Claude about this matter can go through them with you.`}</Text>
            : null,
        ], 'sec-notes')
      : null,
  )
}
