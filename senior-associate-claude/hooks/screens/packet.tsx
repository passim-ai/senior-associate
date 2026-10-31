// Packet: every step, the review notes, the finished files.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { ASK_NOTE, STAGE_ABOUT, STAGE_WORD, noteLine, noteTone, reviewOnly, trackSvg } from '../matter'
import { askAboutThis, perform } from '../perform'
import { HEAD, MUTED, STAGE_TEXT } from '../theme'
import { brief, nowMs } from '../words'
import { matterStatus, isBusy } from '../status'

export async function packetScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, isDesktop, svg, allRuns, actions, button, section, rule, link, links, matterPage } = x
  const prg = c.progress
  const notes = c.review_notes
  const NOTES_SHOWN = 40
  const forms = c.outputs.forms ?? []
  const live = isBusy(matterStatus(c, allRuns[c.path], nowMs()))
  // Any step that has run can be redone: it and every step after it. Not while Claude is at work on the matter.
  const redoable = (status: string) => !live && status !== 'pending'
  const files = c.outputs.packet || c.outputs.cover_letter || forms.length > 0
  return matterPage(c, 'packet',
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
                <Text color={STAGE_TEXT[s.status] ?? MUTED} size="footnote">{STAGE_WORD[s.status] ?? s.status}</Text>
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
