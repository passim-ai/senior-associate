// Redo: a step and every step after it, a fresh document review, or what Claude should change.
import type { EngineInterface } from 'claude-code'
import type { Card, View } from '../../types'
import type { Ctx, Kids } from '../kit'
import { REVIEW_STEPS, docChanges, minutesFrom, reviewOnly, worksIn } from '../matter'
import { session, setNote, typed } from '../state'
import { duration, nowMs, plural } from '../words'
import { matterStatus, isBusy } from '../status'

export async function redoScreen($: EngineInterface, x: Ctx, c: Card): Promise<JSX.Element> {
  const { Text, Input, allRuns, savedAnswers, redoing, actions, card, field, savedMark, subpage } = x
  const r = redoing && redoing.matter === c.path ? redoing : { matter: c.path, stage: '', from: 'matter' as View }
  const stages = c.progress.stages
  const at = stages.findIndex(s => s.id === r.stage)
  const target = at >= 0 ? stages[at]! : null
  const review = target?.id === 'docs_review' && reviewOnly(c)
  const later = target ? stages.slice(at + 1).filter(s => !review) : []
  const kept = target ? stages.slice(0, at).filter(s => s.status === 'passed' || s.status === 'skipped') : []
  const mins = target ? (review ? 8 : minutesFrom(c, target.id)) : null
  const docs = docChanges(c)
  const answered = new Set([
    ...[...Object.entries(savedAnswers), ...Object.entries(typed.answers)].filter(([k, val]) => k.startsWith(`${c.path}#`) && val.trim()).map(([k]) => k),
    ...Object.entries(c.answers).filter(([, a]) => a.answer.trim()).map(([k]) => `${c.path}#${k}`),
  ]).size
  // Redoing a review is a fresh, full review: everything is checked again, not only what changed (CONTRACTS §9).
  const freshReview = Boolean(target && REVIEW_STEPS.has(target.id) && !review)
  const title = !target ? 'Tell Claude what to change' : review ? 'Review the documents again' : `Redo ${target.label}`
  const startLabel = !target ? 'Update the packet' : review ? 'Review the documents again' : `Redo from ${target.label}`
  const what: Kids = !target
    ? [
        <Text key="w1">Claude works in what you write below: it redoes the steps your change affects, checks the packet again, and updates Questions, the memo and the client request.</Text>,
        <Text key="w2" dimColor>A change to the letter takes about 20–30 minutes; a change to the forms can take an hour. It runs in the background, and nothing is filed or sent.</Text>,
      ]
    : review
      ? [
          <Text key="w1">Claude re-reads every document in the matter, including any you’ve added since, and rewrites what’s missing, the memo and the client request. It stops before the forms, so you see the list first.</Text>,
          <Text key="w2" dimColor>About 5–10 minutes, in the background.</Text>,
        ]
      : [
          <Text key="w1">{later.length ? `Claude redoes ${target.label} and every step after it: ${later.map(s => s.label).join(', ')}.` : `Claude redoes ${target.label}.`}</Text>,
          freshReview ? <Text key="w1b">{`${target.label} is done fresh and in full: Claude checks everything again, not only what changed since the last review, and reads the earlier findings only as a reference.`}</Text> : null,
          kept.length ? <Text key="w2">{`${kept.map(s => s.label).join(', ')} ${kept.length === 1 ? 'stays as it is' : 'stay as they are'}.`}</Text> : null,
          <Text key="w3" dimColor>{`${mins ? `About ${duration(mins * 60000)}, in the background.` : 'It runs in the background.'} The current files stay in the folder until Claude replaces them.`}</Text>,
        ]
  const alsoIn = [worksIn(docs), answered ? `your ${plural(answered, 'answer', 'answers')}` : ''].filter(Boolean)
  if (alsoIn.length) what.push(<Text key="w4">{`It also works in ${alsoIn.join(' and ')}.`}</Text>)
  const backLabel = r.from === 'packet' ? 'Packet' : r.from === 'documents' ? 'Documents' : r.from === 'items' ? 'Questions' : c.name
  const busyHere = isBusy(matterStatus(c, allRuns[c.path], nowMs()))
  return subpage(
    { title: c.name, subtitle: title, back: { id: 'redo-cancel', label: backLabel }, here: title },
    card('What happens', what),
    card(target ? 'Anything Claude should know? (optional)' : 'What should Claude change?', [
      field('Your note', l => <Input
        key="redo-note"
        label={l}
        placeholder={target ? 'e.g. Use the 2024 tax return, not the 2023 one' : 'e.g. Lead the letter with the joint lease, and use the newer bank statements'}
        rows={4}
        submitLabel="Save"
        autoFocus={!target ? true : undefined}
        value={typed.redo || undefined}
        onInput={val => { typed.redo = val }}
        onSubmit={val => { typed.redo = val; typed.savedRedo = val; session.savedField = 'redo-note'; void setNote($, `Saved. Claude gets it when you press ${startLabel}.`, 'ok') }}
      />, 'field-redo'),
      savedMark('redo-note', typed.redo === typed.savedRedo),
    ]),
    busyHere
      ? <Text key="redo-busy">Claude is working on this matter right now. Wait for it to finish, or stop it on the matter page, then come back.</Text>
      : actions([
          { id: 'redo-start', label: startLabel, kind: 'primary', detail: review ? 'About 5–10 minutes · runs in the background' : mins ? `About ${duration(mins * 60000)} · runs in the background` : 'Runs in the background' },
          { id: 'redo-cancel', label: 'Cancel', kind: 'secondary', detail: 'Nothing changes' },
        ]),
  )
}
