// Documents: every file in the matter, and the two ways to add more.
import type { EngineInterface } from 'claude-code'
import type { Card, MatterFile } from '../../types'
import type { ActionButton } from '../kit'
import type { Ctx } from '../kit'
import { FOLDER_FIRST, builtPast, changesLine, docChanges, groupFiles, reviewOnly, worksIn } from '../matter'
import { perform } from '../perform'
import { ORANGE } from '../theme'
import { nowMs, plural, when } from '../words'
import { matterStatus, isBusy } from '../status'

export async function documentsScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Box, Text, Button, allRuns, pr, open, asked, actions, card, link, links, subpage, confirmBox } = x
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
  const fileRow = (f: MatterFile) => {
    const asking = asked === `remove:${f.path}`
    return (
      <Box key={f.path} flexDirection="column" gap="xs">
        <Box flexDirection="row" gap="sm" alignItems="center" flexWrap="wrap">
          <Text dimColor>▪</Text>
          <Button key={`open-doc:${f.path}`} plain label={`Open ${f.name}`} onPress={() => perform($, `open-doc:${f.path}`)}><Text>{f.name}</Text></Button>
          {fresh.has(f.name) || fresh.has(f.path) ? <Text color="claude" weight="semibold">new</Text> : replaced.has(f.name) || replaced.has(f.path) ? <Text color="claude" weight="semibold">changed</Text> : null}
          <Text dimColor>{when(f.modified)}</Text>
          {!asking && !live ? <Button key={`remove:${f.path}`} plain dimColor label={`Remove ${f.name}`} onPress={() => perform($, `remove:${f.path}`)}>Remove</Button> : null}
        </Box>
        {asking ? confirmBox('remove', `Take ${f.name} out of the matter? It’s kept, and Put back returns it.`, { id: `remove-yes:${f.path}`, label: 'Yes, remove it', name: `Yes, remove ${f.name}` }, 'Keep it') : null}
      </Box>
    )
  }
  return subpage(
    { title: c.name, subtitle, back: { id: 'matter', label: c.name }, here: 'Documents' },
    nextUp
      ? card(null, [
          <Text key="fresh" weight="semibold">{replaced.size
            ? changesLine({ ...what, removed: [] }, reviewOnly(c) ? 'Claude reviewed the documents' : 'the packet was built').replace(/ Update the packet.*$/, '')
            : `${plural(fresh.size, 'new file', 'new files')} since Claude ${reviewOnly(c) ? 'reviewed the documents' : 'built the packet'}.`}</Text>,
          actions([nextUp, { id: 'add-files', label: 'Add more files…', kind: 'secondary', detail: 'Choose the client’s documents' }]),
        ], ORANGE, 'card-fresh')
      : actions([
          { id: 'add-files', label: 'Add files…', kind: 'primary', detail: 'Choose the client’s documents' },
          { id: 'add-folder', label: 'Add a folder…', kind: 'secondary', detail: 'Copies a folder of their documents' },
        ]),
    nextUp ? links('add-more', [link('add-folder-link', 'Add a folder…', () => { void perform($, 'add-folder') })]) : null,
    <Text key="copies" dimColor>{`Claude works from copies; your originals stay where they are. Press a file to open it.${live ? '' : ' Remove takes one out of the matter, and you can put it back.'}`}</Text>,
    !pr.pickerSeen ? <Text key="sysev" dimColor>macOS may ask whether Claude can control System Events. Choose OK; that’s what lets the file picker open in front.</Text> : null,
    groups.length === 0
      ? card(null, [<Text key="none" dimColor>Nothing here yet. Add the client’s files one at a time, or a whole folder at once.</Text>])
      : card(null, groups.map(gr => {
          const key = `more:${gr.folder || '.'}`
          const all = open.includes(key)
          const shown = all ? gr.files : gr.files.slice(0, FOLDER_FIRST)
          const unlisted = gr.count - gr.files.length
          return (
            <Box key={`g-${gr.folder || 'root'}`} flexDirection="column" gap="xs">
              <Text weight="semibold">{`${gr.folder || 'Matter folder'} · ${gr.count}`}</Text>
              {shown.map(fileRow)}
              {gr.files.length > FOLDER_FIRST
                ? <Box flexDirection="row"><Button key={key} plain dimColor label={all ? `Show fewer in ${gr.folder || 'the matter folder'}` : `Show all ${gr.count} in ${gr.folder || 'the matter folder'}`} onPress={() => perform($, key)}>{all ? 'Show fewer' : `Show all ${gr.count}`}</Button></Box>
                : null}
              {all && unlisted > 0 ? <Text dimColor>{`…and ${unlisted} older in Finder`}</Text> : null}
            </Box>
          )
        })),
    removed.length
      ? card(`Removed · ${removed.length}`, [
          <Text key="removed-what" dimColor>Taken out of the matter, so Claude doesn’t use them. Each is kept with the matter’s files until you put it back.</Text>,
          ...removed.map(r => (
            <Box key={`removed-${r.kept}`} flexDirection="row" gap="sm" alignItems="center" flexWrap="wrap">
              <Text dimColor>▫</Text>
              <Text dimColor>{r.path}</Text>
              {r.removed_at ? <Text dimColor>{`removed ${when(r.removed_at)}`}</Text> : null}
              {/* Not while Claude works: the run reads the documents as they were when it started. */}
              {!live ? <Button key={`restore:${r.kept}`} plain label={`Put back ${r.name || r.path}`} onPress={() => perform($, `restore:${r.kept}`)}><Text weight="medium">Put back</Text></Button> : null}
            </Box>
          )),
        ], undefined, 'card-removed')
      : null,
    links('folder', [link('open-folder', 'Open the matter folder in Finder to see every file.', () => { void perform($, 'open-folder') })]),
  )
}
