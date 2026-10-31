// Packet: every step, the review notes, the finished files.
import type { EngineInterface } from 'claude-code'
import type { Card } from '../../types'
import type { Ctx } from '../kit'
import { ASK_NOTE, STAGE_ABOUT, STAGE_WORD, noteLine, noteTone, reviewOnly } from '../matter'
import { askAboutThis, perform } from '../perform'
import { STAGE_FILL, TRACK, onFill } from '../theme'
import { brief, nowMs } from '../words'
import { matterStatus, isBusy } from '../status'

export async function packetScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Button, allRuns, actions, pillOf, card, link, links, subpage } = x
  const prg = c.progress
  const notes = c.review_notes
  const NOTES_SHOWN = 40
  const forms = c.outputs.forms ?? []
  const live = isBusy(matterStatus(c, allRuns[c.path], nowMs()))
  // Any step that has run can be redone: it and every step after it. Not while Claude is at work on the matter.
  const redoable = (status: string) => !live && status !== 'pending'
  return subpage(
    { title: c.name, subtitle: `${prg.done} of ${prg.total} steps done`, status: pillOf(c), back: { id: 'matter', label: c.name }, here: 'Packet' },
    card('Steps', [
      <Text key="steps-what" dimColor>{live
        ? 'Each step is done by its own specialist, and the reviews are independent. Claude is working on this matter now; you can redo a step once it’s done.'
        : 'Each step is done by its own specialist, and the reviews are independent. To change something, redo a step: Claude redoes it and every step after it, and keeps the ones before.'}</Text>,
      ...prg.stages.map((s, i) => (
        <Box key={s.id} flexDirection="row" gap="sm" alignItems="flex-start">
          <Box backgroundColor={STAGE_FILL[s.status] ?? TRACK} paddingX="sm" borderStyle="round" borderColor={STAGE_FILL[s.status] ?? TRACK}>
            <Text color={onFill(STAGE_FILL[s.status] ?? TRACK)} weight="semibold" size="caption">{String(i + 1)}</Text>
          </Box>
          <Box flexDirection="column" flexGrow={1} flexShrink={1} gap="xs">
            <Box flexDirection="row" gap="sm" flexWrap="wrap" alignItems="center">
              <Text weight={s.status === 'in_progress' ? 'semibold' : 'medium'}>{s.label}</Text>
              <Text dimColor>{STAGE_WORD[s.status] ?? s.status}</Text>
              {redoable(s.status)
                ? <Button key={`redo:${s.id}`} plain label={s.id === 'docs_review' && reviewOnly(c) ? 'Review the documents again' : `Redo from ${s.label}`} onPress={() => perform($, `redo:${s.id}`)}><Text weight="medium">{s.id === 'docs_review' && reviewOnly(c) ? 'Review again ›' : 'Redo from here ›'}</Text></Button>
                : null}
            </Box>
            {STAGE_ABOUT[s.id] ? <Text dimColor>{STAGE_ABOUT[s.id]}</Text> : null}
          </Box>
        </Box>
      )),
    ]),
    notes.length > 0
      ? card(`Review notes · ${notes.length} open`, [
          <Text key="what" dimColor>What the independent reviews found. Anything you need to act on is also on What’s left.</Text>,
          ...notes.slice(0, NOTES_SHOWN).map((f, i) => (
            <Box key={`f-${i}`} flexDirection="row" gap="sm">
              <Text color={noteTone(f)} weight="bold">▲</Text>
              <Box flexDirection="column" flexShrink={1} gap="xs">
                <Text>{f.title}</Text>
                {f.detail && f.detail !== f.title ? <Text dimColor>{brief(f.detail)}</Text> : null}
                <Text dimColor>{noteLine(f)}</Text>
                {links(`note-acts-${i}`, [link(`ask-note:${i}`, 'Ask Claude about this', () => { void askAboutThis($, c, f.title, ASK_NOTE) }, false, `Ask Claude about: ${brief(f.title, 80)}`)])}
              </Box>
            </Box>
          )),
          notes.length > NOTES_SHOWN
            ? <Text key="notes-more" dimColor>{`…and ${notes.length - NOTES_SHOWN} more. The memo lists every one; Ask Claude about this matter can go through them with you.`}</Text>
            : null,
        ])
      : null,
    c.outputs.packet || c.outputs.cover_letter || forms.length > 0
      ? card('Files for this matter', [
          c.outputs.packet ? <Text key="pk">{c.outputs.packet.name}</Text> : null,
          c.outputs.paper_packet ? <Text key="pp">{`${c.outputs.paper_packet.name}: the forms that go on paper`}</Text> : null,
          c.outputs.cover_letter ? <Text key="cl">{c.outputs.cover_letter.name}</Text> : null,
          forms.length ? <Text key="forms-head" dimColor>Forms (each opens on its own):</Text> : null,
          forms.length ? links('forms', forms.map(f => link(`open-form:${f.name}`, f.name.replace(/\.pdf$/i, ''), () => { void perform($, `open-form:${f.name}`) }, true, `Open ${f.name.replace(/\.pdf$/i, '')}`))) : null,
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
        ])
      : null,
  )
}
