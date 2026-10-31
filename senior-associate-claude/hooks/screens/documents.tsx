// Documents: every file in the matter, and the two ways to add more.
import type { EngineInterface } from 'claude-code'
import type { Card, MatterFile } from '../../types'
import type { ActionButton } from '../kit'
import type { Ctx } from '../kit'
import { FOLDER_FIRST, builtPast, changesLine, docChanges, groupFiles, reviewOnly, worksIn } from '../matter'
import { perform } from '../perform'
import { ACCENT, ACCENT_LIGHT, NAVY } from '../theme'
import { nowMs, plural, when } from '../words'
import { matterStatus, isBusy } from '../status'

export async function documentsScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Button, allRuns, pr, open, asked, actions, button, lone, card, barCard, section, rule, pill, link, links, matterPage, confirmBox } = x
  const docs = c.documents
  const groups = groupFiles(docs.files, docs.folders)
  const listed = docs.listed ?? docs.files.length
  const capped = docs.count > listed
  const fresh = new Set(docs.added_since_build ?? [])
  const replaced = new Set(docs.changed_since_build ?? [])
  const what = docChanges(c)
  const arrived = fresh.size + replaced.size
  const removed = docs.removed ?? []
  const live = isBusy(matterStatus(c, allRuns[c.path], nowMs()))
  const subtitle = docs.count
    ? capped ? `${docs.count} files · showing the ${listed} most recent` : `${plural(docs.count, 'file', 'files')} in the matter folder`
    : 'No documents yet'
  // New files since Claude last looked: the press that works them in is right here, not back on the matter page.
  const nextUp: ActionButton | null = arrived && !live
    ? reviewOnly(c)
      ? { id: 'review-again', label: 'Review the documents again', kind: 'primary', detail: `About 5–10 minutes · includes ${worksIn(what)}` }
      : builtPast(c) ? { id: 'update', label: 'Update the packet', kind: 'primary', detail: `Works in ${worksIn(what)}` } : null
    : null
  const fileRow = (f: MatterFile, i: number) => {
    const asking = asked === `remove:${f.path}`
    const mark = fresh.has(f.name) || fresh.has(f.path) ? 'new' : replaced.has(f.name) || replaced.has(f.path) ? 'changed' : ''
    return (
      <Box key={f.path} flexDirection="column" gap="xs">
        {i ? rule(`file-rule-${f.path}`) : null}
        <Box flexDirection="row" columnGap="sm" rowGap="xs" alignItems="center" flexWrap="wrap" paddingY="xs">
          <Text dimColor>▪</Text>
          <Box flexDirection="row" flexShrink={1}>
            <Button key={`open-doc:${f.path}`} plain label={`Open ${f.name}`} onPress={() => perform($, `open-doc:${f.path}`)}><Text weight="medium">{f.name}</Text></Button>
          </Box>
          {mark ? pill(mark, ACCENT_LIGHT, `mark-${f.path}`) : null}
          <Text dimColor size="footnote">{when(f.modified)}</Text>
          {!asking && !live ? button(`remove:${f.path}`, 'Remove', () => { void perform($, `remove:${f.path}`) }, 'quiet', { name: `Remove ${f.name}`, small: true }) : null}
        </Box>
        {asking ? confirmBox('remove', `Take ${f.name} out of the matter? It’s kept, and Put back returns it.`, { id: `remove-yes:${f.path}`, label: 'Yes, remove it', name: `Yes, remove ${f.name}` }, 'Keep it') : null}
      </Box>
    )
  }
  return matterPage(c, 'documents',
    section('Source documents', [
      <Text key="subtitle" weight="medium" color={NAVY}>{subtitle}</Text>,
      <Text key="copies" dimColor>{`Claude works from copies; your originals stay where they are. Press a file to open it.${live ? '' : ' Remove takes one out of the matter, and you can put it back.'}`}</Text>,
      !pr.pickerSeen ? <Text key="sysev" dimColor size="footnote">macOS may ask whether Claude can control System Events. Choose OK; that’s what lets the file picker open in front.</Text> : null,
      nextUp
        ? barCard('card-fresh', ACCENT, [
            <Text key="fresh" weight="semibold" color={NAVY}>{replaced.size
              ? changesLine({ ...what, removed: [] }, reviewOnly(c) ? 'Claude reviewed the documents' : 'the packet was built').replace(/ Update the packet.*$/, '')
              : `${plural(fresh.size, 'new file', 'new files')} since Claude ${reviewOnly(c) ? 'reviewed the documents' : 'built the packet'}.`}</Text>,
            actions([nextUp, { id: 'add-files', label: 'Add more files…', kind: 'secondary', detail: 'Choose the client’s documents' }]),
            links('add-more', [link('add-folder-link', 'Add a folder…', () => { void perform($, 'add-folder') }, true)]),
          ])
        : actions([
            { id: 'add-files', label: 'Add files…', kind: 'primary', detail: 'Choose the client’s documents' },
            { id: 'add-folder', label: 'Add a folder…', kind: 'secondary', detail: 'Copies a folder of their documents' },
          ]),
    ], 'sec-documents'),
    groups.length === 0
      ? card(null, [<Text key="none" dimColor>Nothing here yet. Add the client’s files one at a time, or a whole folder at once.</Text>])
      : <Box key="groups" flexDirection="column" gap="lg">
          {groups.map(gr => {
            const key = `more:${gr.folder || '.'}`
            const all = open.includes(key)
            const shown = all ? gr.files : gr.files.slice(0, FOLDER_FIRST)
            const unlisted = gr.count - gr.files.length
            return (
              <Box key={`g-${gr.folder || 'root'}`} flexDirection="column" gap="xs">
                <Text weight="semibold" color={NAVY}>{`${gr.folder || 'Matter folder'} · ${gr.count}`}</Text>
                {rule(`g-rule-${gr.folder || 'root'}`)}
                {shown.map(fileRow)}
                {gr.files.length > FOLDER_FIRST
                  ? lone(key, button(key, all ? 'Show fewer' : `Show all ${gr.count}`, () => { void perform($, key) }, 'quiet', { name: all ? `Show fewer in ${gr.folder || 'the matter folder'}` : `Show all ${gr.count} in ${gr.folder || 'the matter folder'}` }))
                  : null}
                {all && unlisted > 0 ? <Text dimColor>{`…and ${unlisted} older in Finder`}</Text> : null}
              </Box>
            )
          })}
        </Box>,
    removed.length
      ? section(`Removed · ${removed.length}`, [
          <Text key="removed-what" dimColor size="footnote">Taken out of the matter, so Claude doesn’t use them. Each is kept with the matter’s files until you put it back.</Text>,
          ...removed.map(r => (
            <Box key={`removed-${r.kept}`} flexDirection="row" columnGap="sm" rowGap="xs" alignItems="center" flexWrap="wrap">
              <Text dimColor>▫</Text>
              <Text dimColor>{r.path}</Text>
              {r.removed_at ? <Text dimColor size="footnote">{`removed ${when(r.removed_at)}`}</Text> : null}
              {/* Not while Claude works: the run reads the documents as they were when it started. */}
              {!live ? button(`restore:${r.kept}`, 'Put back', () => { void perform($, `restore:${r.kept}`) }, 'link', { name: `Put back ${r.name || r.path}` }) : null}
            </Box>
          )),
        ], 'card-removed')
      : null,
    links('folder', [link('open-folder', 'Open the matter folder in Finder to see every file.', () => { void perform($, 'open-folder') }, true)]),
  )
}
