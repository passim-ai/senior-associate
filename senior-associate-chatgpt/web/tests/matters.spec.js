import {test, expect} from '@playwright/test';
import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const artifacts=fileURLToPath(new URL('../../artifacts/',import.meta.url));

test.beforeEach(async ({page}) => {await page.clock.install(); await page.goto('/'); await expect(page.frameLocator('#widget').getByRole('heading', {name:'Matters', exact:true})).toBeVisible();});

test('create, import documents, request review, and cancel a pending start', async ({page}) => {
  const ui = page.frameLocator('#widget');
  await ui.getByRole('button', {name:'New matter', exact:true}).click();
  await ui.getByLabel('Client name', {exact:true}).fill('Browser Fictional Alvarez');
  await ui.getByLabel('What is being filed?', {exact:true}).selectOption('n400');
  await ui.getByRole('button', {name:'Create matter', exact:true}).click();
  await expect(ui.getByRole('heading', {name:/Browser Fictional Alvarez/})).toBeVisible();
  await ui.getByRole('button', {name:'Add files…', exact:true}).click();
  await ui.getByRole('button', {name:'Documents', exact:true}).click();
  await expect(ui.getByText('Fictional evidence.txt', {exact:true})).toBeVisible();
  await ui.getByRole('button', {name:'Overview', exact:true}).click();
  await ui.getByRole('button', {name:'Review documents first', exact:true}).click();
  await expect(ui.getByText('Requested in the chat. Follow its progress and any permission prompts there.', {exact:true})).toBeVisible();
  const messages = await page.evaluate(() => window.messages);
  expect(messages).toHaveLength(1);
  expect(messages[0].content[0].text).toContain('CHATGPT-RUNTIME.md');
  expect(messages[0].content[0].text).toContain('Your run id is');
  await ui.getByRole('button', {name:'Cancel pending start', exact:true}).click();
  await expect(ui.getByRole('button', {name:'Build packet', exact:true})).toBeVisible();
});

test('saved attorney answers persist, memo is inert text, and layouts fit', async ({page}) => {
  const fixture = await page.evaluate(async () => window.fixture({name:'Fictional Rivera N-400'}));
  await page.evaluate(result => window.pushResult(result), fixture.result);
  const ui = page.frameLocator('#widget');
  await expect(ui.getByRole('heading', {name:'Fictional Rivera N-400', exact:true})).toBeVisible();
  await ui.getByRole('button', {name:'Questions', exact:true}).click();
  await ui.getByRole('button', {name:'Use the recommendation', exact:true}).click();
  await ui.getByRole('button', {name:'Save answer', exact:true}).click();
  await expect(ui.getByText('Saved for the next update.', {exact:true})).toBeVisible();
  await ui.getByRole('button', {name:'Refresh', exact:true}).click();
  await expect(ui.getByRole('textbox').first()).toHaveValue('Use counsel’s address.');
  await ui.getByRole('button', {name:'Memo & request', exact:true}).click();
  await expect(ui.getByText(/This is a UI fixture, not legal work/)).toBeVisible();
  expect(await page.frame({url:/\/widget$/}).evaluate(() => window.fixtureXss)).toBeUndefined();
  await ui.getByRole('button', {name:'Overview', exact:true}).click();
  fs.mkdirSync(artifacts, {recursive:true});
  await page.screenshot({path:artifacts+'matters-desktop.png', fullPage:true});
  await page.setViewportSize({width:420,height:950});
  await expect(ui.getByRole('button', {name:'Settings', exact:true})).toBeVisible();
  const widths = await page.frame({url:/\/widget$/}).evaluate(() => ({scroll:document.documentElement.scrollWidth,width:innerWidth}));
  expect(widths.scroll).toBeLessThanOrEqual(widths.width);
  await page.screenshot({path:artifacts+'matters-panel.png', fullPage:true});
});

test('rejected chat handoff cancels its reservation and offers a safe retry', async ({page}) => {
  const fixture = await page.evaluate(async () => window.fixture({name:'Fictional Handoff N-400'}));
  await page.evaluate(result => {window.rejectMessages=true;window.pushResult(result);}, fixture.result);
  const ui = page.frameLocator('#widget');
  await ui.getByRole('button', {name:'Build packet', exact:true}).click();
  await expect(ui.getByRole('alert')).toContainText('No pending start');
  await ui.getByRole('button', {name:'Refresh', exact:true}).click();
  await expect(ui.getByRole('button', {name:'Build packet', exact:true})).toBeVisible();
});

test('profile saves without leaking it into model context', async ({page}) => {
  const ui = page.frameLocator('#widget');
  await ui.getByRole('button', {name:'Your details', exact:true}).click();
  await ui.getByLabel('Attorney name', {exact:true}).fill('Fictional Counsel');
  await ui.getByLabel('Email', {exact:true}).fill('fictional@example.test');
  await ui.getByRole('button', {name:'Save your details', exact:true}).click();
  await expect(ui.getByRole('status')).toHaveText('Your details are saved.');
  await page.reload();
  await ui.getByRole('button', {name:'Your details', exact:true}).click();
  await expect(ui.getByLabel('Attorney name', {exact:true})).toHaveValue('Fictional Counsel');
  const contexts = await page.evaluate(() => JSON.stringify(window.contexts));
  expect(contexts).not.toContain('fictional@example.test');
});


test('progress refresh continues after a button receives focus', async ({page}) => {
  const fixture = await page.evaluate(async () => window.fixture({name:'Fictional Refresh N-400'}));
  await page.evaluate(result => window.pushResult(result), fixture.result);
  const ui = page.frameLocator('#widget');
  await ui.getByRole('button', {name:'Overview', exact:true}).click();
  const before = await page.evaluate(() => window.toolCalls.filter(name => name === 'matters_view').length);
  await page.clock.fastForward(16000);
  await expect.poll(() => page.evaluate(() => window.toolCalls.filter(name => name === 'matters_view').length)).toBeGreaterThan(before);
});

test('new matter preserves drafts and asks for a custom filing only when needed', async ({page}) => {
  const ui=page.frameLocator('#widget');
  await ui.getByRole('button',{name:'New matter',exact:true}).click();
  await ui.getByLabel('Client name',{exact:true}).fill('Fictional Draft Preserved');
  await expect(ui.getByLabel('Describe the filing',{exact:true})).toHaveCount(0);
  await ui.getByLabel('What is being filed?',{exact:true}).selectOption('custom');
  await ui.getByLabel('Describe the filing',{exact:true}).fill('I-601A provisional waiver');
  await ui.getByRole('button',{name:'Your details',exact:true}).click();
  await ui.getByRole('button',{name:'Matters',exact:true}).click();
  await ui.getByRole('button',{name:'New matter',exact:true}).click();
  await expect(ui.getByLabel('Client name',{exact:true})).toHaveValue('Fictional Draft Preserved');
  await expect(ui.getByLabel('Describe the filing',{exact:true})).toHaveValue('I-601A provisional waiver');
  await ui.getByLabel('Client name',{exact:true}).press('Enter');
  await expect(ui.getByRole('heading',{name:'Fictional Draft Preserved',exact:true})).toBeVisible();
});

test('search keeps typing focus and a no-match search does not offer sample creation', async ({page}) => {
  const ui=page.frameLocator('#widget');
  await page.evaluate(async()=>window.fixture({name:'Fictional Search Client'}));
  await ui.getByRole('button',{name:'Matters',exact:true}).click();
  await ui.getByRole('searchbox').pressSequentially('no such client');
  await expect(ui.getByRole('searchbox')).toHaveValue('no such client');
  await expect(ui.getByRole('heading',{name:'No matching matters'})).toBeVisible();
  await ui.getByRole('button',{name:'Clear search',exact:true}).click();
  await expect(ui.getByRole('button',{name:/Fictional Search Client/})).toBeVisible();
});

test('document reader formats safe Markdown and supports client request switching', async ({page}) => {
  const fixture=await page.evaluate(async()=>window.fixture({name:'Fictional Readable Memo'}));
  fixture.result._meta.view.matter.memo_text='# Review memo\n\n**Important finding** with [USCIS](https://www.uscis.gov).\n\n- First item\n- Second item\n\n<script>window.fixtureXss=true</script>\n\n[Unsafe](javascript:alert(1))';
  await page.evaluate(result=>window.pushResult(result),fixture.result);
  const ui=page.frameLocator('#widget');
  await ui.getByRole('button',{name:'Memo & request',exact:true}).click();
  await expect(ui.getByRole('heading',{name:'Review memo',exact:true})).toBeVisible();
  await expect(ui.getByRole('link',{name:'USCIS',exact:true})).toHaveAttribute('rel','noopener noreferrer');
  await expect(ui.getByRole('link',{name:'Unsafe',exact:true})).toHaveCount(0);
  await ui.getByRole('link',{name:'USCIS',exact:true}).click();
  await expect.poll(()=>page.evaluate(()=>window.links)).toEqual(['https://www.uscis.gov/']);
  await expect(ui.locator('article li')).toHaveCount(2);
  expect(await page.frame({url:/\/widget$/}).evaluate(()=>window.fixtureXss)).toBeUndefined();
  await ui.getByRole('button',{name:'Client request',exact:true}).click();
  await expect(ui.getByText('Please confirm the mailing address. Fictional fixture only.')).toBeVisible();
});

test('redo requires a clear confirmation with keyboard cancellation and focus containment', async ({page}) => {
  const fixture=await page.evaluate(async()=>window.fixture({name:'Fictional Redo Review'}));
  fixture.result._meta.view.matter.progress.started=true;
  await page.evaluate(result=>window.pushResult(result),fixture.result);
  const ui=page.frameLocator('#widget');
  await ui.getByRole('button',{name:'Packet',exact:true}).click();
  await ui.getByRole('button',{name:'Redo',exact:true}).first().click();
  const dialog=ui.getByRole('dialog');
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button',{name:'Cancel',exact:true})).toBeFocused();
  await dialog.getByRole('button',{name:'Cancel',exact:true}).press('Shift+Tab');
  await expect(dialog.getByRole('button',{name:'Redo from here',exact:true})).toBeFocused();
  await dialog.getByRole('button',{name:'Redo from here',exact:true}).press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(ui.getByRole('button',{name:'Redo',exact:true}).first()).toBeFocused();
  expect(await page.evaluate(()=>window.messages)).toHaveLength(0);
});

test('all primary screens fit a narrow panel, dark theme, and reduced motion', async ({page}) => {
  const fixture=await page.evaluate(async()=>window.fixture({name:'Fictional Barrientos–Eckhardt N-400'}));
  await page.evaluate(result=>window.pushResult(result),fixture.result);
  const ui=page.frameLocator('#widget');
  const widget=page.frame({url:/\/widget$/});
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.setViewportSize({width:320,height:950});
  for(const name of ['Overview','Documents','Questions','Packet','Memo & request','Timeline']){
    await ui.getByRole('button',{name,exact:true}).click();
    expect(await widget.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await page.evaluate(()=>document.querySelector('#widget').contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/host-context-changed',params:{theme:'dark'}},location.origin));
  await expect(ui.locator('html')).toHaveAttribute('data-theme','dark');
  await ui.getByRole('button',{name:'Overview',exact:true}).click();
  await page.setViewportSize({width:420,height:950});
  await page.screenshot({path:artifacts+'redesign-dark-panel.png',fullPage:true});
  await ui.getByRole('button',{name:'Your details',exact:true}).click();
  expect(await widget.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await ui.getByRole('button',{name:'Settings',exact:true}).click();
  expect(await widget.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});


test('visual review of onboarding, forms, questions, documents, packet, and memo', async ({page}) => {
  const ui=page.frameLocator('#widget');
  const screenshots=artifacts+'ui-redesign-2026-10-31';
  fs.mkdirSync(screenshots,{recursive:true});
  async function capture(name){
    await page.locator('#widget').evaluate(el=>{el.style.height='950px';el.style.height=Math.max(950,el.contentWindow.document.documentElement.scrollHeight)+'px';});
    await page.screenshot({path:`${screenshots}/${name}.png`,fullPage:true});
  }
  // Only the UI fixture is varied; this is not a legal workflow receipt.
  const fixture=await page.evaluate(async()=>window.fixture({name:'Fictional Rivera N-400'}));
  const home=structuredClone(fixture.result);home._meta.view.matter=null;home._meta.view.matters=[];
  await page.evaluate(result=>window.pushResult(result),home);
  await capture('01-welcome');
  await ui.getByRole('button',{name:'New matter',exact:true}).click();
  await ui.getByLabel('Client name',{exact:true}).fill('Rivera, Ana');
  await ui.getByLabel('What is being filed?',{exact:true}).selectOption('n400');
  await capture('02-new-matter');
  await page.evaluate(result=>window.pushResult(result),fixture.result);
  await capture('03-overview');
  for(const [tab,file] of [['Questions','04-questions'],['Documents','05-documents'],['Packet','06-packet'],['Memo & request','07-memo']]){
    await ui.getByRole('button',{name:tab,exact:true}).click();await capture(file);
  }
  await ui.getByRole('button',{name:'Your details',exact:true}).click();await capture('08-profile');
  await ui.getByRole('button',{name:'Settings',exact:true}).click();await capture('09-settings');
  await page.evaluate(result=>window.pushResult(result),fixture.result);
  await ui.getByRole('button',{name:'Questions',exact:true}).click();
  await page.setViewportSize({width:420,height:950});await capture('10-panel-questions');
});


test('attorney approval binds the displayed version, requires risk reasons, and becomes stale', async ({page}) => {
  const fixture=await page.evaluate(async()=>window.fixture({name:'Fictional Filing Approval',reviewed_packet:true}));
  await page.evaluate(result=>window.pushResult(result),fixture.result);
  const ui=page.frameLocator('#widget');
  await ui.getByRole('button',{name:'Packet',exact:true}).click();
  await expect(ui.getByText('Draft for attorney review. Completing the build does not approve it for filing.')).toBeVisible();
  const approve=ui.getByRole('button',{name:'I reviewed this version and approve it for filing',exact:true});
  await approve.click();
  await expect(ui.getByRole('alert')).toContainText('Explain your decision');
  await ui.getByLabel('Reason for filing with these risks').fill('Fictional integration test acknowledges the synthetic risk.');
  await approve.click();
  await expect(ui.getByText('Approved for filing by Fictional Browser Attorney. Approval applies only to this version.')).toBeVisible();
  await expect(ui.getByRole('button',{name:'Show approved filing copies'})).toBeVisible();
  await ui.getByRole('button',{name:'Show approved filing copies'}).click();
  await expect(ui.getByRole('status')).toHaveText('Opening the approved filing copies.');
  await page.evaluate(async path=>window.fixture({path,change_source:true}),fixture.path);
  await ui.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect(ui.getByRole('button',{name:'Show approved filing copies'})).toHaveCount(0);
  await expect(ui.getByText(/changed after the final review/)).toBeVisible();
});

test('jurisdiction settings persist and are part of filing review', async ({page}) => {
  const fixture=await page.evaluate(async()=>window.fixture({name:'Fictional Jurisdiction'}));
  await page.evaluate(result=>window.pushResult(result),fixture.result);
  const ui=page.frameLocator('#widget');
  await ui.getByText('Jurisdiction',{exact:true}).click();
  await ui.getByLabel('Forum',{exact:true}).fill('USCIS');
  await ui.getByLabel('Controlling circuit',{exact:true}).fill('ca5');
  await ui.getByLabel('Jurisdiction basis',{exact:true}).fill('Fictional residence in Texas');
  await ui.getByRole('button',{name:'Save jurisdiction',exact:true}).click();
  await ui.getByRole('button',{name:'Refresh',exact:true}).click();
  await expect(ui.getByLabel('Controlling circuit',{exact:true})).toHaveValue('ca5');
  await expect(ui.getByLabel('Jurisdiction basis',{exact:true})).toHaveValue('Fictional residence in Texas');
});
