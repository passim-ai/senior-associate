// Help.
import type { EngineInterface } from 'claude-code'
import type { Ctx } from '../kit'
import { PHASE_LABEL, PHASE_TONE } from '../status'

import { askClaude, perform } from '../perform'
import { ASK_LABEL, MATTERS_ASK, NEW_FOLDER, UPDATE_ASK } from '../words'
import { HEAD } from '../theme'

export async function helpScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  const { Box, Text, pill, card, button, lone, link, links, version, folder, howItWorks, subpage } = x
  const howTo = (key: string, q: string, a: string) => (
    <Box key={key} flexDirection="column" gap="xs">
      <Text weight="semibold" color={HEAD}>{q}</Text>
      <Text dimColor size="footnote">{a}</Text>
    </Box>
  )
  const meaning = (phase: string, text: string) => (
    <Box key={`means-${phase}`} flexDirection="row" gap="md" alignItems="flex-start">
      {pill(PHASE_LABEL[phase]!, PHASE_TONE[phase]!, `pill-${phase}`)}
      <Box flexDirection="column" flexShrink={1} minWidth={0}><Text size="footnote">{text}</Text></Box>
    </Box>
  )
  return subpage(
    { title: 'Help', subtitle: version ? `Immigration Packet Builder ${version}` : 'Immigration Packet Builder', back: { id: 'back-help', label: 'Back' }, here: 'Help', foot: 'Back' },
    card('How it works', howItWorks),
    card('What each status means', [
      meaning('new', 'Add the client’s documents.'),
      meaning('ready', 'Build the packet, or review the documents first.'),
      meaning('reviewed', 'Claude listed what’s missing. Send the client request, or build now. Add documents and review them again whenever the client sends more.'),
      meaning('building', 'Keep Claude open. You’ll get a notification when it’s done. Stop, on the matter page, if you need to.'),
      meaning('starting', 'Claude needs your OK to start: press Enter in the chat box. Cancel, on the matter page, takes the request back.'),
      meaning('needs_you', 'Answer Claude’s questions on the Questions tab, then update the packet.'),
      meaning('waiting_client', 'The client owes documents or answers. Add them when they arrive.'),
      meaning('draft', 'The packet is built; some items are needed before filing.'),
      meaning('complete', 'Read it through, sign, and file.'),
      meaning('paused', 'Claude stopped partway, or you stopped it. Continue building picks up where it stopped.'),
      meaning('stopped', 'Something interrupted Claude. Try again picks up where it stopped; Not now shows where the matter stands.'),
      meaning('filed', 'You marked it filed. It waits, folded, at the foot of the list; Undo on the matter page puts it back.'),
    ]),
    card('How do I…', [
      howTo('h1', 'Add documents after Claude has reviewed or built', 'On the matter’s Overview, More you can do › Add documents… (or the Documents tab). Then press Review the documents again before a build, or Update the packet after one.'),
      howTo('h2', 'Have Claude look at the documents again', 'Before a build: Review the documents again, on the matter page. After a build: add the files, then Update the packet, or Tell Claude what to change. (Redo from here on Document review rebuilds everything, about 1½ hours.)'),
      howTo('h0', 'Ask about a case, research a point, or have one thing changed', 'On the matter page, Ask Claude about this matter: type it and press Ask. Claude answers in the chat, looks up the law in BIA Edge, and makes the change you ask for; then Update the packet has the reviews check it.'),
      howTo('h3', 'Fix something in the draft', 'Ask Claude about this matter for one change, made in the chat. Or, on the matter page, Tell Claude what to change: Claude redoes the steps your change affects, in the background.'),
      howTo('h3b', 'Tell Claude how to handle the matter before it builds', 'On the matter page, Attorney instructions: what to lead with, what to leave out. Claude follows them in every step, in the build and every run after it.'),
      howTo('h4', 'Redo one part, such as the forms or the letter', 'Open the Packet tab, choose the step, and press Redo from here. Claude redoes it and every step after it; the steps before it are kept.'),
      howTo('h4b', 'Make sure the law in the letter is still good before filing', 'On the matter’s Overview, the Research card says when the law the letter cites was last checked. Check the law again, there or on the Packet tab, takes about 5 minutes with BIA Edge and changes nothing in the packet.'),
      howTo('h5', 'Change the case type or the filing posture', 'On the matter page, More you can do › Change what is being filed. The steps start over; your documents stay and earlier work is kept.'),
      howTo('h6', 'Take out a document added by mistake', 'Documents › Remove beside the file. It’s kept with the matter, and Put back returns it.'),
      howTo('h7', 'Undo Mark done', 'Questions › Resolved › Reopen.'),
      howTo('h7b', 'Stop Claude asking permission for every step', 'Under the prompt box, switch the permission setting to Auto before you build. In Claude’s usual setting a full build asks several hundred times, and “don’t ask again” removes only a few. In Auto, Build puts the request in your chat box: press Enter there to send it.'),
      howTo('h8', 'Stop Claude', 'While Claude works, press Stop on the matter page. Everything finished is kept, and Continue building picks up there.'),
      howTo('h9', 'Undo Mark as filed', 'Open the matter and press Undo.'),
      howTo('h9b', 'Keep clients’ names off the screen', 'The list opens with its groups folded: Show opens one, and Hide names folds them all again. Notifications never name a matter.'),
      howTo('h9c', 'Show Immigration Packet Builder to someone else', 'Type /matters demo. Only the fictional sample matter is shown, from a folder of its own, until you press Leave the demo.'),
      <Box key="h10" flexDirection="column" gap="xs">
        <Text weight="semibold" color={HEAD}>Try Immigration Packet Builder on a fictional case</Text>
        <Text dimColor size="footnote">The sample matter is an I-601A built from made-up documents, with gaps a good review should catch. Archive it when you’re done; this brings it back.</Text>
        {lone('add-sample', button('add-sample', 'Open the sample matter', () => { void perform($, 'add-sample') }, 'secondary'))}
      </Box>,
    ]),
    card('Keyboard', [
      <Text key="k0" dimColor size="footnote">In the side panel, once you’ve clicked in it:</Text>,
      <Text key="k1">b presses the matter’s main button.</Text>,
      <Text key="k2">n starts a new matter, from Matters.</Text>,
      <Text key="k3">f finds a matter, once there are more than six.</Text>,
      <Text key="k4">1 to 9 open the matter in that place on the list.</Text>,
      <Text key="k5">Tab moves between buttons and boxes; Enter presses a button or saves a box. In the question box, Shift+Enter starts a new line.</Text>,
    ]),
    card('If something goes wrong', [
      <Text key="g1">A build stopped: open the matter and press Try again. Everything finished before it stopped is saved.</Text>,
      <Text key="g2">The client sent more documents, or you answered Claude’s questions: add the files, then press Update the packet (or Review the documents again, before a build).</Text>,
      <Text key="g3">Something won’t run on this Mac: check your setup.</Text>,
      <Text key="g4">{`Your files: each matter has a folder in your Matters folder${folder ? ` (${folder})` : ''}. On a matter’s Overview, Matter details › Show files in Finder opens its finished files.`}</Text>,
      <Box key="g5" flexDirection="column" gap="xs">
        <Text>{NEW_FOLDER}</Text>
        {links('help-ask-matters-row', [button('help-ask-matters', ASK_LABEL, () => { void askClaude($, MATTERS_ASK) }, 'link')])}
      </Box>,
      <Box key="g6" flexDirection="column" gap="xs">
        <Text>To get the newest version of Immigration Packet Builder, Claude can update it for you.</Text>
        {links('help-ask-update-row', [button('help-ask-update', ASK_LABEL, () => { void askClaude($, UPDATE_ASK) }, 'link')])}
      </Box>,
      links('help-links', [link('help-setup', 'Check my setup', () => { void perform($, 'setup') }, true)]),
    ]),
    <Text key="contact" dimColor size="footnote">Questions or a problem: github.com/passim-ai/senior-associate/issues</Text>,
  )
}
