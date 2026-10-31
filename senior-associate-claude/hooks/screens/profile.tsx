// Your details: the attorney's own information, kept on this Mac.
import type { EngineInterface } from 'claude-code'
import type { Ctx } from '../kit'
import { PROFILE_FIELDS } from '../matter'
import { perform, saveProfile, unsavedProfile } from '../perform'
import { typed } from '../state'
import { andList } from '../words'
import { WARN_TEXT } from '../theme'

export async function profileScreen($: EngineInterface, x: Ctx): Promise<JSX.Element> {
  // Beside the account number: with no account, Claude asks nothing about one and no open item is raised for it.
  const accountChoice = () => {
    const none = (typed.profile.has_uscis_online_account ?? x.p.profile?.has_uscis_online_account) === 'no'
    return x.choice('account-none', none ? 'account:yes' : 'account:none', 'I don’t have a USCIS online account', none ? 'Press again if you open one' : 'Questions about it are then left out', none)
  }
  const { Box, Text, Input, p, asked, actions, button, card, field, savedMark, choice, link, links, subpage } = x
  const current = p.profile ?? {}
  const noAccount = (typed.profile.has_uscis_online_account ?? current.has_uscis_online_account) === 'no'
  const unsaved = unsavedProfile(p)
  return subpage(
    { title: 'Your details', subtitle: 'Used on the G-28, each form’s preparer section, and the cover letter’s letterhead and signature. Leave anything blank that doesn’t apply.', back: { id: 'back-profile', label: 'Back' }, here: 'Your details', foot: 'Back' },
    asked === 'profile-back' && unsaved.length
      ? card(null, [
          <Text key="unsaved">{`You changed ${andList(unsaved)} and haven’t saved ${unsaved.length === 1 ? 'it' : 'them'}. Save and go back keeps ${unsaved.length === 1 ? 'it' : 'them'}; Discard leaves your details as they were.`}</Text>,
          <Box key="unsaved-acts" flexDirection="row" columnGap="md" rowGap="sm" flexWrap="wrap" alignItems="center">
            {button('profile-save-back', 'Save and go back', () => { void perform($, 'profile-save-back') }, 'primary')}
            {button('profile-discard', 'Discard', () => { void perform($, 'profile-discard') }, 'secondary')}
            {links('unsaved-more', [link('confirm-no', 'Keep editing', () => { void perform($, 'confirm-no') })])}
          </Box>,
        ], WARN_TEXT, 'card-unsaved')
      : null,
    card(null, PROFILE_FIELDS.flatMap((f, i) => f.key === 'uscis_online_account_number' && noAccount ? [accountChoice()] : [
      field(<Input
        key={`profile-${f.key}`}
        label={f.label}
        placeholder={f.placeholder}
        value={typed.profile[f.key] ?? current[f.key] ?? ''}
        submitLabel="save"
        autoFocus={i === 0 ? true : undefined}
        onInput={value => { typed.profile = { ...typed.profile, [f.key]: value } }}
        onSubmit={value => { typed.profile = { ...typed.profile, [f.key]: value }; void saveProfile($, false, `profile-${f.key}`) }}
      />, `field-${f.key}`),
      savedMark(`profile-${f.key}`, typed.profile[f.key] === undefined),
      f.key === 'uscis_online_account_number' ? accountChoice() : null,
    ])),
    card('Orders restricting your practice', [
      <Text key="ask" dimColor size="footnote">The G-28 asks whether you are subject to any order suspending, enjoining, restraining, disbarring, or otherwise restricting you in the practice of law (Part 2, item 1.c).</Text>,
      choice('discipline-no', 'discipline:no', 'I am not subject to any such order', '', current.subject_to_discipline_order === 'no'),
      choice('discipline-yes', 'discipline:yes', 'I am subject to such an order', 'Explain it below; it goes in the G-28’s Part 6', current.subject_to_discipline_order === 'yes'),
      current.subject_to_discipline_order === 'yes'
        ? field(<Input
            key="profile-discipline_order_details"
            label="Explanation"
            placeholder="The order, who issued it, and its terms"
            value={typed.profile.discipline_order_details ?? current.discipline_order_details ?? ''}
            submitLabel="save"
            onInput={value => { typed.profile = { ...typed.profile, discipline_order_details: value } }}
            onSubmit={value => { typed.profile = { ...typed.profile, discipline_order_details: value }; void saveProfile($, false, 'profile-discipline_order_details') }}
          />, 'field-discipline')
        : null,
      savedMark('profile-discipline_order_details', typed.profile.discipline_order_details === undefined),
    ]),
    actions([{ id: 'save-profile', label: 'Save', kind: 'primary', detail: 'Used in every build from now on' }]),
    <Text key="where" dimColor size="footnote">Saved on this Mac, in your Matters folder.</Text>,
  )
}
