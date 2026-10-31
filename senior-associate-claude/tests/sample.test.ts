// The sample matter: the fictional I-601A a new attorney finds on the list. The welcome still comes first, the sample
// opens from it with what to try, its page shows what a good review catches once the documents are reviewed, and
// Help brings it back.
import { expect, test } from 'claude-code/testing'
import { OPTS, SEEN, boot, inActions, open, sampleCard, world } from './world'

test('a new attorney: the sample is added once, the welcome comes first, and the sample opens with what to try', OPTS(), async ($, on) => {
  const { ui, tap, requests, store } = await boot($, on, [], { sample: true }, { prefs: { ...SEEN, onboarded: false } })
  expect(requests.filter(r => r.ensure_sample)).toHaveLength(1)
  // The only matter is the sample, but it doesn't take the place of the welcome.
  expect(await ui.find({ type: 'Text', text: /Client documents in/ })).toBeDefined()
  expect(await inActions(ui, /^New matter$/)).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^See how it works$/ })).toBeDefined()
  expect(await ui.find({ type: 'Button', key: 'main:sample' })).toMatchObject({ text: 'Open the sample matter' })
  expect(await ui.find({ type: 'Text', text: /^A fictional I-601A case to try first$/ })).toBeDefined()
  await tap('main:sample')
  expect(await ui.find({ type: 'Text', text: /^This is a sample matter$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Press Review documents first\./ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^What a good review catches$/ })).toBeUndefined()
  expect(await inActions(ui, /^Review documents first$/)).toBeDefined()
  expect(store.prefs).toMatchObject({ onboarded: true })
  // Later loads don't ask again.
  await tap('nav-all')
  expect(requests.filter(r => r.ensure_sample)).toHaveLength(1)
  await ui.unmount()
})

test('an attorney already at work is never sent the sample', OPTS(), async ($, on) => {
  const { ui, requests, matters } = await boot($, on, [], { sample: true }, { prefs: SEEN })
  expect(requests.some(r => r.ensure_sample)).toBe(false)
  expect(matters).toHaveLength(0)
  await ui.unmount()
})

test('after the sample’s review, its page lists what a good review catches; Help opens it again', OPTS(), async ($, on) => {
  const { ui, tap, ops } = await boot($, on, [sampleCard('reviewed')], { sample: true, open: false }, { prefs: SEEN })
  await tap('open:/matters/Sample - Barrientos-Eckhardt')
  expect(await ui.find({ type: 'Text', text: /^What a good review catches$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^2\. His intake gives the wedding date as March 12, 2016/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Compare them with Questions, above\.$/ })).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /^Press Review documents first/ })).toBeUndefined()
  // From Help: the sample on the list is opened, not added again.
  await tap('help')
  await tap('add-sample')
  expect(ops).not.toContain('add_sample')
  expect(await ui.find({ type: 'Text', text: /^This is a sample matter$/ })).toBeDefined()
  await ui.unmount()
})

test('Help adds the sample back when it is gone from the list', OPTS(), async ($, on) => {
  const { ui, tap, ops } = await boot($, on, [], { sample: true }, { prefs: SEEN })
  await tap('help')
  expect(await ui.find({ type: 'Text', text: /^Try Immigration Packet Builder on a fictional case$/ })).toBeDefined()
  await tap('add-sample')
  expect(ops).toContain('add_sample')
  expect(await ui.find({ type: 'Text', text: /^This is a sample matter$/ })).toBeDefined()
  await ui.unmount()
})
