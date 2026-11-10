import {App, applyDocumentTheme, applyHostFonts, applyHostStyleVariables} from '@modelcontextprotocol/ext-apps';
import {unpack, sendText, handoffRun} from './bridge.js';
import {icon, prose} from './ui.js';
import wordmark from './assets/passim-wordmark.svg';
import darkWordmark from './assets/passim-wordmark-dark.svg';
import './style.css';

const app = new App({name: 'Senior Associate / Matters', version: '0.2.1'}, {});
const root = document.getElementById('app');
const state = {payload: null, page: 'home', tab: 'overview', busy: false, error: '', notice: '', filter: '',
  archived: false, fallback: '', pending: null, drafts: new Map(), connected: false, confirm: null, memoTab: 'memo'};
let readGeneration = 0;
const c = () => state.payload?.matter;
const editing = () => root.contains(document.activeElement) && document.activeElement.matches('input, textarea, select');
const matterDrafts = () => !!c() && [...state.drafts.keys()].some(key => key.startsWith(`${c().path}:`));
function forget(prefix) {for (const key of [...state.drafts.keys()]) if (key.startsWith(prefix)) state.drafts.delete(key);}

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'text') el.textContent = String(value);
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key === 'value' || key === 'checked' || key === 'disabled') el[key] = value;
    else el.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child !== null && child !== undefined && child !== false) el.append(child instanceof Node ? child : String(child));
  }
  if (tag === 'form') el.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.tagName === 'INPUT') {
      event.preventDefault(); submitLocally(el);
    }
  });
  return el;
}
// Sandboxed MCP hosts may disallow native form submission before a submit
// listener runs. Validate locally and dispatch only our JS handler; never navigate.
function submitLocally(form) {
  if (!state.busy && form.reportValidity()) form.dispatchEvent(new Event('submit', {bubbles: true, cancelable: true}));
}
const submitButton = text => h('button', {type: 'button', class: 'primary', text, disabled: state.busy,
  onclick: event => submitLocally(event.currentTarget.form)});
const button = (text, onclick, primary = false, disabled = false) => h('button', {type: 'button', class: primary ? 'primary' : 'secondary', text, onclick, disabled: disabled || state.busy});
const line = (text, cls = 'muted') => h('p', {class: cls, text});
const heading = text => h('h1', {text});
const section = (title, ...children) => h('section', {class: 'panel'}, h('h3', {text: title}), ...children);
let fieldId = 0;
const label = (text, input) => {
  input.id ||= input.name ? `field-${input.name}` : `field-${++fieldId}`;
  return h('div', {class: 'field'}, h('label', {for: input.id, text}), input);
};
const input = (name, value = '', props = {}) => h('input', {class: 'input', name, value, ...props});
const textarea = (name, value = '', props = {}) => h('textarea', {class: 'input', name, rows: 4, ...props}, value);
const time = value => value ? new Date(value).toLocaleString(undefined, {dateStyle: 'medium', timeStyle: 'short'}) : '';
const phase = card => card?.phase === 'building' ? (card.status?.lease?.holder === 'app' ? 'Waiting to start in chat' : 'Work in progress') : card?.phase_label || card?.label || '';
const formValues = form => Object.fromEntries(new FormData(form).entries());

async function call(name, args = {}) {return unpack(await app.callServerTool({name, arguments: args}));}
function accept(payload, navigate = true) {
  if (!payload?.catalog) return;
  state.payload = payload;
  if (navigate) state.page = payload.matter ? 'matter' : 'home';
  if (state.pending && payload.matter?.status?.lease?.run_id !== state.pending.run_id) state.pending = null;
  syncContext();
}
function syncContext() {
  if (!state.connected) return;
  const card = state.page === 'matter' ? c() : null;
  // Only the selected matter enters the model's context; never the entire list.
  const text = card ? `Senior Associate selected matter: ${JSON.stringify({path: card.path, case: card.case_line, status: phase(card)})}` : 'Senior Associate: no matter selected.';
  app.updateModelContext({content: [{type: 'text', text}]}).catch(() => {});
}
async function busy(fn) {
  if (state.busy) return;
  state.busy = true; state.error = ''; state.notice = ''; render();
  try {await fn();} catch (error) {state.error = error.message || 'The request failed.'; if (error.fallback) state.fallback = error.fallback;}
  finally {state.busy = false; render();}
}
async function load(path = '', quiet = false) {
  const generation = ++readGeneration;
  const {view} = await call('matters_view', {matter_path: path, include_archived: state.archived});
  if (generation !== readGeneration) return;
  accept(view, !quiet);
  // Avoid replacing a form while the attorney is typing or has unsaved text.
  if (!quiet || (!editing() && !matterDrafts())) render();
}
async function act(op, extra = {}, message = 'Saved.', navigate = false) {
  return busy(async () => {
    ++readGeneration;
    const {view} = await call('matters_action', {request: {op, ...(c() ? {matter_path: c().path} : {}), ...extra}});
    accept(view, navigate);
    state.notice = view?.warning || message;
  });
}
async function start(kind, stage_id = '', note = '') {
  return busy(async () => {
    const {data, view} = await handoffRun(app, {matter_path: c().path, kind, stage_id, note});
    accept(view); state.pending = data; state.fallback = '';
    state.notice = view?.warning || 'Requested in the chat. Follow its progress and any permission prompts there.';
  });
}
async function ask(text) {
  return busy(async () => {await sendText(app, text); state.notice = 'Sent to the chat.';});
}
function go(page) {state.page = page; state.error = ''; state.notice = ''; syncContext(); render(); focusHeading();}
function focusHeading() {root.querySelector('h1')?.focus({preventScroll: true}); window.scrollTo(0, 0);}
function tab(id) {state.tab = id; state.notice = ''; render(); root.querySelector('.tab-body')?.focus({preventScroll: true});}
const eyebrow = text => h('p', {class: 'eyebrow', text});
const badge = (text, cls = '') => h('span', {class: `badge ${cls}`, text});
const empty = (symbol, title, text, action = null) => h('div', {class: 'empty-state'}, icon(symbol), h('h3', {text: title}), line(text), action);
const disclosure = (title, ...children) => h('details', {class: 'disclosure'}, h('summary', {text: title}), h('div', {class: 'disclosure-body'}, ...children));
const pageTitle = (title, subtitle, action = null) => h('div', {class: 'title-row'}, h('div', {}, heading(title), subtitle ? line(subtitle) : null), action);
function fileButton(file, op, args) {const b = button('Open', () => act(op, args, 'Opening the file.')); b.setAttribute('aria-label', `Open ${file.name || 'file'}`); return b;}

function draft(key, initial = '') {return state.drafts.has(key) ? state.drafts.get(key) : initial;}
function remember(key) {return e => state.drafts.set(key, e.target.type === 'checkbox' ? e.target.checked : e.target.value);}

function toolbar() {
  const nav = (title, page, symbol, action) => h('button', {type:'button', class: state.page === page ? 'nav-item selected' : 'nav-item', 'aria-current': state.page === page ? 'page' : null, disabled:state.busy, onclick:action}, icon(symbol), h('span', {text:title}));
  return h('header', {class:'topbar'}, h('div', {class:'brand'}, h('img', {class:'wordmark-light',src:wordmark, alt:'Passim AI', width:124, height:34}),h('img', {class:'wordmark-dark',src:darkWordmark, alt:'Passim AI', width:124, height:34}), h('span', {class:'brand-divider'}), h('span', {class:'product-name', text:'Senior Associate'})),
    h('nav', {'aria-label':'Workspace'}, nav('Matters', 'home', 'folder', () => busy(() => load())), nav('Your details', 'profile', 'person', () => go('profile')), nav('Settings', 'settings', 'settings', () => go('settings'))));
}
function home() {
  const all = state.payload?.matters || [];
  const rows = all.filter(m => `${m.name} ${m.case_line || m.case || ''}`.toLowerCase().includes(state.filter.toLowerCase()));
  const search = input('find', state.filter, {type:'search', placeholder:'Search by client or filing', 'aria-label':'Find a matter', oninput:e => {
    state.filter = e.target.value; render();
  }});
  const sample = button('Explore a fictional matter', () => act('add_sample', {}, 'Fictional sample created.', true));
  const requiredSetup=(state.payload.setup?.checks || []).filter(check=>check.required && !check.ok);
  const welcome = h('section', {class:'welcome'}, eyebrow('YOUR FIRST MATTER'), h('h2', {text:'A clear path from documents to review.'}),
    line('Start with a client and a filing. Senior Associate helps organize the record and prepare work for your review.'),
    h('ol', {class:'getting-started'}, [
      ['01', 'Add the documents', 'Choose files or a folder. Original documents stay where they are.'],
      ['02', 'Review what’s needed', 'See missing evidence and answer the decisions that need your judgment.'],
      ['03', 'Prepare and review', 'Build the draft, read the findings, and decide when it is ready to file.'],
    ].map(([n,title,text]) => h('li', {}, h('span', {class:'step-number', text:n}), h('div', {}, h('h3', {text:title}), line(text))))),
    h('div', {class:'sample-invitation'}, icon('spark'), h('div', {}, h('strong', {text:'See how it works'}), line('The fictional sample lets you explore without client information.')), sample));
  return [pageTitle('Matters', 'Client documents, attorney decisions, and filing work.', button('New matter', () => go('new'), true)),
    requiredSetup.length ? h('div',{class:'setup-note'},icon('info'),h('span',{text:'A setup step is needed before packet preparation.'}),button('Review setup',()=>go('settings'))) : null,
    all.length || state.archived || state.filter ? h('div', {class:'filters'}, h('div', {class:'search-field'}, icon('search'), search), h('label', {class:'check-label'}, input('archived','',{type:'checkbox', checked:state.archived, onchange:e => {state.archived=e.target.checked;busy(() => load());}}), 'Show archived')) : null,
    all.length ? (rows.length ? h('div', {class:'matter-list'}, h('div', {class:'list-heading'}, h('span', {text:`${rows.length} ${rows.length === 1 ? 'matter' : 'matters'}`}), h('span', {text:'STATUS'})), rows.map(m => h('button', {class:'matter-row', disabled:state.busy, onclick:() => {state.tab='overview';busy(() => load(m.path)).then(focusHeading);}},
      h('span', {class:'matter-identity'}, h('strong', {text:m.name}), h('span', {class:'cap', text:m.case_line || m.case || 'Matter'})),
      h('span', {class:'matter-status'}, badge(phase(m)), m.counts?.needed_before_filing ? h('span',{class:'attention-label',text:`${m.counts.needed_before_filing} needed before filing`}) : h('span',{class:'cap',text:m.next_line || ''})), icon('chevron'))))
      : empty('search','No matching matters','Try a different client name or filing.',button('Clear search',()=>{state.filter='';render();}))) : welcome,
    h('footer', {class:'workspace-footer'}, icon('shield'), h('span', {text:'Documents stay in your local Matters folder. The chat reads the files needed for the work.'}), all.length ? sample : null)];
}
function newMatter() {
  const catalog = state.payload.catalog;
  const name = input('name', draft('new.name'), {required: true, maxlength: 60, placeholder: 'Client name', oninput: remember('new.name')});
  const type = h('select', {name: 'type', class: 'input', required: true, onchange: e => {remember('new.type')(e); render();}}, h('option', {value: '', text: 'Choose a filing'}), catalog.matter_types.map(t => h('option', {value: t.id, text: t.label})), h('option', {value: 'custom', text: 'Describe another filing'}));
  type.value = draft('new.type');
  const posture = h('select', {name: 'posture', class: 'input', onchange: remember('new.posture')}, catalog.filing_postures.map(p => h('option', {value: p.value, text: p.label})));
  posture.value = draft('new.posture', catalog.filing_postures[0]?.value || '');
  const method = h('select', {name: 'method', class: 'input', onchange: remember('new.method')}, h('option', {value: 'paper', text: 'Paper'}), h('option', {value: 'online', text: 'Online'}));
  method.value = draft('new.method', 'paper');
  const form = h('form', {class: 'form-grid', onsubmit: e => {
    e.preventDefault(); const v = formValues(e.target); const chosen = catalog.matter_types.find(t => t.id === v.type);
    const mt = chosen?.matter_type || (v.custom || '').trim();
    if (!mt) {state.error = 'Describe what is being filed.'; render(); return;}
    const folder = chosen?.short && !v.name.toLowerCase().endsWith(chosen.short.toLowerCase()) ? `${v.name.trim()} ${chosen.short}` : v.name.trim();
    act('create', {name: folder, matter_type: mt, filing_posture: v.posture, protected: v.protected === 'on', filing_method: v.method}, 'Matter created. Add the client’s documents next.', true).then(() => {
      if (!state.error) {for (const key of [...state.drafts.keys()]) if (key.startsWith('new.')) state.drafts.delete(key);}
    });
  }}, label('Client name', name), label('What is being filed?', type), type.value === 'custom' ? label('Describe the filing', input('custom', draft('new.custom'), {required:true, placeholder:'For example, I-601A provisional unlawful presence waiver', oninput: remember('new.custom')})) : null,
    label('What stage is this filing at?', posture), label('Filing method', method),
    h('div', {class:'span-all protected-option'}, h('label', {class:'check-label'}, input('protected', '', {type:'checkbox', checked:draft('new.protected',false), onchange:remember('new.protected')}), 'This is a protected matter'), line('For VAWA, T, U, or another matter requiring protected handling.', 'field-help')),
    h('div', {class: 'actions form-actions'}, submitButton('Create matter'), button('Cancel', () => go('home'))));
  return [pageTitle('New matter', 'Start with the client and the filing. You’ll add documents next.'), h('div', {class:'form-surface'}, form), h('p',{class:'footnote',text:'Not sure which filing to choose? Confirm the case strategy before creating the matter.'})];
}
function overview(card) {
  const lease = card.status?.lease;
  const running = !!lease?.fresh;
  let title, description, primary, secondary;
  if (running) {
    title = lease.holder === 'app' ? 'Continue in the chat' : 'Work is in progress';
    description = lease.holder === 'app' ? 'Your request is ready in the chat. Keep the chat open and respond to any prompts there.' : 'Senior Associate is working through the matter. Progress and results appear here as each step finishes.';
    primary = lease.holder === 'app' ? button('Cancel pending start', () => act('cancel_start', {run_id:lease.run_id}, 'Pending request checked. Work already underway will continue.')) : null;
  } else if (!card.documents.count) {
    title='Add the client’s documents'; description='Choose the evidence you have. Senior Associate will identify what is missing during review.';
    primary=button('Add files…',()=>act('add_documents',{},'Document selection finished.'),true);
    secondary=button('Add a folder…',()=>act('add_folder',{},'Folder selection finished.'));
  } else if (card.phase === 'filed') {
    title='Marked as filed'; description='The matter’s documents, work product, and history are available below.';
    primary=button('View packet',()=>tab('packet'),true);
  } else if (card.phase === 'complete') {
    title='Review the completed work'; description='Read the packet and review findings before deciding whether the matter is ready to file.';
    primary=button('Review packet',()=>tab('packet'),true); secondary=button('Update the packet',()=>start('update'));
  } else if ((card.needs_you || []).some(n=>n.who==='system')) {
    title='Resolve a setup issue'; description='A local setup issue needs attention before the work can continue.';
    primary=button('Review questions',()=>tab('questions'),true); secondary=button('Review setup',()=>go('settings'));
  } else if ((card.needs_you || []).some(n=>n.who==='attorney' && !card.answers?.[n.key]?.answer)) {
    title='Your judgment is needed'; description='Review the open decisions. Saved answers will be used the next time you update the packet.';
    primary=button('Review questions',()=>tab('questions'),true); secondary=button(card.progress.started?'Update the packet':'Build packet',()=>start(card.progress.started?'update':'build'));
  } else if (!card.review && !card.progress.started) {
    title='Review the documents'; description='Start with a review to identify missing evidence, inconsistencies, and decisions for you.';
    primary=button('Review documents first',()=>start('review_docs'),true); secondary=button('Build packet',()=>start('build'));
  } else {
    title=card.phase==='paused' ? 'Continue preparing the packet' : 'Prepare the next draft';
    description='Use the documents and saved answers to continue the work. Unresolved items stay visible for your review.';
    primary=button(card.phase==='paused' ? 'Continue building' : card.progress.started ? 'Update the packet' : 'Build packet',()=>start(card.phase==='paused'?'continue':card.progress.started?'update':'build'),true);
    secondary=button('Review documents again',()=>start('review_again'));
  }
  const instructionsKey=`${card.path}:instructions`;
  const instructions=textarea('instructions',draft(instructionsKey,card.attorney_instructions),{oninput:remember(instructionsKey),placeholder:'Case strategy, scope, or drafting preferences…'});
  const queryKey=`${card.path}:question`;
  const query=textarea('question',draft(queryKey),{placeholder:'Ask about the record, a missing document, or the next step…',oninput:remember(queryKey),rows:3});
  const attention=card.open_items?.open || [];
  const languageKey=`${card.path}:language`;
  const jurisdictionFields = [['forum','Forum'],['circuit','Controlling circuit'],['jurisdiction_basis','Jurisdiction basis']].map(([key,title]) => {
    const value = input(key,draft(`${card.path}:${key}`,card.meta[key] || ''),{maxlength:500,oninput:remember(`${card.path}:${key}`)});
    return {key,value,field:label(title,value)};
  });
  const language=input('language',draft(languageKey,card.meta.client_language || 'English'),{oninput:remember(languageKey)});
  return [h('section',{class:`next-step ${running?'is-running':''}`},eyebrow(running?'IN THE CHAT':'NEXT STEP'),h('h2',{text:title}),line(description),h('div',{class:'actions'},primary,secondary),
      !running && card.phase!=='filed' ? h('div',{class:'handoff-hint'},icon('message'),h('span',{text:'Reviews and builds run in the chat. Return here to see the results.'})) : null),
    h('div',{class:'metrics'}, metric(card.documents.count,'Documents',()=>tab('documents')),metric(`${card.progress.done} of ${card.progress.total}`,'Steps complete',()=>tab('packet')),metric(card.open_items?.blocking ?? card.needs_you?.length ?? 0,'Needed before filing',()=>tab('questions'))),
    h('div',{class:'overview-columns'},section('Needs attention', attention.length ? [h('ul',{class:'attention-list'},attention.slice(0,3).map(item=>h('li',{},h('span',{class:'attention-dot'}),h('div',{},h('strong',{text:item.title}),line(`${item.who==='client'?'From the client':item.who==='attorney'?'Attorney decision':'For review'}${item.blocks_filing?' · Before filing':''}`,'cap'))))),button(`View ${attention.length === 1 ? 'open item' : `all ${attention.length} open items`}`,()=>tab('questions'))] : line(card.review?'No open items are currently recorded.':'Missing evidence and attorney decisions will appear after review.')),
      section('Ask about this matter',label('Your question',query),button('Ask in chat',()=>{if(query.value.trim()) ask(`Ask Senior Associate about ${JSON.stringify(card.name)}: ${query.value}\nMatter folder: ${JSON.stringify(card.path)}`);}))),
    disclosure('Attorney instructions',line('Case strategy and drafting preferences for future work.'),label('Instructions',instructions),button('Save instructions',()=>act('set_instructions',{text:instructions.value},'Instructions saved.').then(()=>{if(!state.error)state.drafts.delete(instructionsKey);}))),
    disclosure('Jurisdiction',line('Record the matter’s forum and basis for controlling law. Circuit: ca1–ca11, dc, federal, or none.'),jurisdictionFields.map(f=>f.field),button('Save jurisdiction',()=>act('set_meta',Object.fromEntries(jurisdictionFields.map(f=>[f.key,f.value.value])),'Jurisdiction saved.').then(()=>{if(!state.error)jurisdictionFields.forEach(f=>state.drafts.delete(`${card.path}:${f.key}`));}))),
    disclosure('Matter details',h('div',{class:'detail-grid'},label('Client request language',language),h('div',{},line('Filing method','cap'),line(card.meta.filing_method==='online'?'Online':'Paper','detail-value')),card.meta.protected?badge('Protected matter'):null),
      h('div',{class:'actions'},button('Save language',()=>act('set_meta',{client_language:language.value},'Client request language saved.').then(()=>{if(!state.error)state.drafts.delete(languageKey);})),button('Open matter folder',()=>act('open_folder',{},'Opening the folder.')),
      card.phase==='complete'?button('Mark as filed',()=>confirmAction('Mark this matter as filed?','Use this only after you have submitted the filing. This records its status; it does not submit anything.','Mark as filed',()=>act('mark_filed',{},'Marked as filed.'))):null,
      card.phase==='filed'?button('Undo marked as filed',()=>act('unmark_filed',{},'Filing mark removed.')):null))];
}
const metric = (value,title,onclick) => h('button',{class:'metric',onclick,disabled:state.busy},h('strong',{text:value}),h('span',{text:title}),icon('chevron'));
function documents(card) {
  return [section('Source documents',h('div',{class:'section-intro'},line('Add copies of the evidence you have. Your originals stay where they are.'),h('div',{class:'actions'},button('Add files…',()=>act('add_documents',{},'Document selection finished.'),true),button('Add a folder…',()=>act('add_folder',{},'Folder selection finished.')))),
    card.documents.count ? h('div',{class:'file-list'},(card.documents.files || []).map(file=>h('div',{class:'file-row'},icon('file'),h('div',{class:'file-name'},h('strong',{text:file.name}),h('span',{class:'cap',text:'Source document'})),fileButton(file,'open_document',{path:file.path})))) : empty('folder','The record starts here','Add the client’s notices, forms, civil documents, and supporting evidence.'))];
}
function confirmAction(title,description,label,action) {const focusIndex=[...root.querySelectorAll('button')].indexOf(document.activeElement);state.confirm={title,description,label,action,focusIndex};render(); root.querySelector('[role=dialog] button')?.focus();}
function packet(card) {
  const files=Object.entries(card.outputs || {}).filter(([,value])=>value?.path && !Array.isArray(value));
  const readiness=card.filing_readiness;
  const riskKey=`${card.path}:filing-risk`;
  const risk=textarea('filing-risk',draft(riskKey),{oninput:remember(riskKey)});
  const approval=readiness ? section('Attorney filing review',
    line(readiness.approved ? `Approved for filing by ${readiness.attorney}. Approval applies only to this version.` : 'Draft for attorney review. Completing the build does not approve it for filing.'),
    (readiness.blockers || []).map(text=>line(text)),
    (readiness.risks || []).map(text=>line(`Review risk: ${text}`)),
    !readiness.approved && readiness.risks?.length ? label('Reason for filing with these risks',risk) : null,
    !card.status?.lease?.fresh && readiness.eligible && !readiness.approved ? button('I reviewed this version and approve it for filing',()=>act('approve_filing',{digest:readiness.digest,risk_note:risk.value},'This version is approved for filing.').then(()=>{if(!state.error)state.drafts.delete(riskKey);}),true) : null,
    readiness.approved ? button('Show approved filing copies',()=>act('open_output',{which:'approved_packet'},'Opening the approved filing copies.'),true) : null) : null;
  return [approval,section('Work product',line('Drafts and review materials prepared for this matter.'),files.length ? h('div',{class:'file-list'},files.map(([key,file])=>h('div',{class:'file-row'},icon('file'),h('div',{class:'file-name'},h('strong',{text:file.name || key.replaceAll('_',' ')})),fileButton(file,'open_output',{which:key})))) : empty('file','No work product yet','Run a document review or build the packet from Overview.',button('Go to Overview',()=>tab('overview')))),
    section('Preparation progress',line(`${card.progress.done} of ${card.progress.total} steps complete. Completion of a step does not establish filing readiness.`),h('ol',{class:'stage-list'},card.progress.stages.map((stage,index)=>h('li',{class:`stage stage-${stage.status}`},h('span',{class:'stage-marker'},stage.status==='passed'?icon('check'):String(index+1)),h('div',{class:'stage-description'},h('strong',{text:stage.label}),h('span',{class:'cap',text:({passed:(card.review_notes || []).some(n=>n.stage_label===stage.label)?'Completed with findings':'Completed',skipped:'Skipped',pending:'Not started',in_progress:'In progress',blocked:'Needs attention',failed:'Stopped'})[stage.status] || stage.status})),
      !card.status?.lease?.fresh && card.progress.started ? button('Redo',()=>confirmAction(`Redo from ${stage.label}?`,'This starts a new run from this step and may regenerate later work. Review the results when the run finishes.','Redo from here',()=>start('redo',stage.id))) : null)))),
    disclosure('Review findings', (card.review_notes || []).length ? card.review_notes.map(n=>h('div',{class:'note-row'},h('strong',{text:n.title}),line([n.severity_word,n.stage_label].filter(Boolean).join(' · '),'cap'))) : line('Findings from the review stages will appear here.'))];
}
function questions(card) {
  const needs=card.needs_you || [];
  const decisions=needs.filter(n=>n.who==='attorney');
  const seen=new Set(decisions.flatMap(n=>[n.id,n.key]).filter(Boolean));
  const remaining=(card.open_items?.open || []).filter(item=>!seen.has(item.id) && !seen.has(item.key));
  const groups=[['From the client',remaining.filter(n=>n.who==='client')],['Other open items',remaining.filter(n=>n.who!=='client')]];
  return [h('div',{class:'section-intro'},h('div',{},h('h2',{text:'Questions & missing evidence'}),line('Save your decisions here, then update the packet to apply them.')),badge(`${card.open_items?.blocking || 0} needed before filing`,'attention')),
    decisions.length ? section('Attorney decisions',decisions.map((n,index)=>{
      const question=n.question || n.text;
      const key=`${card.path}:answer:${n.key}`;
      const saved=card.answers?.[n.key]?.answer || '';
      const answer=textarea(`answer-${n.key}`,draft(key,saved),{oninput:remember(key),rows:3,placeholder:'Record your decision and any conditions…'});
      return h('div',{class:'decision'},h('div',{class:'decision-heading'},h('span',{class:'decision-number',text:String(index+1).padStart(2,'0')}),h('h3',{text:question}),saved?badge('Answer saved'):null), n.detail?line(n.detail):null,
        n.recommendation?h('div',{class:'recommendation'},h('strong',{text:'Suggested approach'}),line(n.recommendation),button('Use the recommendation',()=>{state.drafts.set(key,n.recommendation);render();root.querySelector(`[name="answer-${CSS.escape(n.key)}"]`)?.focus();})):null,
        label('Your answer',answer),h('div',{class:'actions'},button('Save answer',()=>act('save_answer',{key:n.key,question,answer:answer.value},'Answer saved. Update the packet to work it in.').then(()=>{if(!state.error)state.drafts.delete(key);}),true),saved?line('Saved for the next update.','cap'):null));
    })) : empty('check','No attorney decisions recorded',card.review?'Any new decisions will appear after the next review.':'Run a document review to identify questions for you.'),
    ...groups.filter(([,items])=>items.length).map(([title,items])=>section(title,items.map(item=>h('div',{class:'note-row'},h('div',{class:'item-heading'},h('strong',{text:item.title}),item.blocks_filing?badge('Before filing','attention'):null),item.detail?line(item.detail):null)))),
    needs.filter(n=>n.who!=='attorney' && ![...(card.open_items?.open||[])].some(i=>i.id===n.id || i.key && i.key===n.key)).map(n=>section(n.question||n.text,n.detail?line(n.detail):null)),
    h('div',{class:'update-bar'},h('div',{},h('strong',{text:'Ready to use your answers?'}),line('Saved answers are applied during the next packet update.','cap')),button('Update the packet with saved answers',()=>start('update'),true,!!card.status?.lease?.fresh))];
}
function memo(card) {
  const isRequest=state.memoTab==='request';
  const text=isRequest?card.client_request_text:card.memo_text;
  return [h('div',{class:'reader-toolbar'},h('div',{class:'segmented','aria-label':'Read document'},['memo','request'].map(id=>h('button',{class:state.memoTab===id?'selected':'','aria-pressed':state.memoTab===id,text:id==='memo'?'Attorney memo':'Client request',onclick:()=>{state.memoTab=id;render();}}))), text?button(isRequest?'Copy client request':'Copy memo',()=>busy(async()=>{try{await navigator.clipboard.writeText(text);}catch{throw new Error('Copy is unavailable in this panel. Select the document text below to copy it.');}state.notice=isRequest?'Copied. Review it before sending to the client.':'Memo copied.';})):null),
    text?h('section',{class:'document-reader'},eyebrow(isRequest?'CLIENT COMMUNICATION · DRAFT':'ATTORNEY WORK PRODUCT'),isRequest?line('Review the request before sharing it with your client.','reader-note'):null,prose(text,href=>busy(async()=>{const result=await app.openLink({url:href});if(result.isError)throw new Error('The chat could not open this link. You can copy its address from the document.');}))):
      empty('file',isRequest?'No client request yet':'No attorney memo yet',isRequest?'The request appears when the workflow identifies missing evidence.':'The memo appears after a document review or packet build.')];
}
function matter() {
  const card=c();
  if(!card || card.problem) return [heading('Matter unavailable'),line(card?.problem || 'Select a matter again.'),button('Back to Matters',()=>busy(()=>load()))];
  const tabs=[['overview','Overview'],['documents','Documents'],['questions','Questions'],['packet','Packet'],['memo','Memo & request'],['timeline','Timeline']];
  const body=state.tab==='documents'?documents(card):state.tab==='packet'?packet(card):state.tab==='questions'?questions(card):state.tab==='memo'?memo(card):state.tab==='timeline'?
    [section('Matter activity',card.timeline.length?h('ol',{class:'timeline'},card.timeline.map(e=>h('li',{},h('span',{class:'timeline-dot'}),h('div',{},line(e.text,''),h('time',{class:'cap',datetime:e.at,text:time(e.at)}))))):empty('clock','No activity yet','Your actions and completed work will appear here.'))]:overview(card);
  return [h('div',{class:'breadcrumb'},h('button',{onclick:()=>busy(()=>load()),text:'Matters'}),icon('chevron'),h('span',{text:'Matter workspace'})),
    h('div',{class:'matter-heading'},h('div',{},heading(card.name),line(card.case_line || 'Matter')),h('div',{class:'matter-heading-actions'},badge(phase(card)),button('Refresh',()=>busy(()=>load(card.path))))),
    h('nav',{class:'tabs','aria-label':'Matter sections'},tabs.map(([id,text])=>h('button',{class:state.tab===id?'active':'','aria-label':text,'aria-current':state.tab===id?'page':null,onclick:()=>tab(id)},text,id==='questions' && card.open_items?.blocking?h('span',{class:'tab-count',text:card.open_items.blocking}):null))),
    h('div',{class:'tab-body',tabindex:'-1'},...body)];
}
function profile() {
  const data = state.payload.profile || {};
  const fields = [['attorney_name', 'Attorney name'], ['firm_name', 'Firm'], ['mailing_address', 'Mailing address'], ['phone', 'Phone'], ['email', 'Email'], ['bar_number', 'Bar number'], ['licensing_authority', 'Licensing authority'], ['uscis_online_account_number', 'USCIS online account number']];
  const form = h('form', {class: 'form-grid', onsubmit: e => {e.preventDefault(); act('save_profile', {profile: formValues(e.target)}, 'Your details are saved.').then(() => {if (!state.error) {forget('profile.'); render();}});}},
    fields.map(([key, title]) => label(title, input(key, draft(`profile.${key}`, data[key]), {type:key==='email'?'email':key==='phone'?'tel':'text',oninput: remember(`profile.${key}`)}))),
    ['has_uscis_online_account', 'subject_to_discipline_order'].map(key => {
      const select = h('select', {name: key, class: 'input', onchange: remember(`profile.${key}`)}, h('option', {value: '', text: 'Choose an answer'}), h('option', {value: 'no', text: 'No'}), h('option', {value: 'yes', text: 'Yes'}));
      select.value = draft(`profile.${key}`, data[key] || '');
      return label(key === 'has_uscis_online_account' ? 'Do you have a USCIS online account?' : 'Are you subject to an order restricting your practice?', select);
    }), label('If yes, discipline order details', textarea('discipline_order_details', draft('profile.discipline_order_details', data.discipline_order_details || ''), {oninput: remember('profile.discipline_order_details')})),
    h('div',{class:'form-actions'},submitButton('Save your details')));
  return [pageTitle('Your details', 'Your professional details for the G-28, preparer sections, and cover letters.'), h('div',{class:'form-surface'},form), line('Saved locally. You can review these details in each prepared document.','footnote')];
}
function settings() {
  const form = h('form', {class: 'form-grid', onsubmit: e => {e.preventDefault(); const values = formValues(e.target); busy(async () => {
    const {view} = await call('configure_matters', values); accept(view, false); forget('settings.'); state.notice = 'Folders saved. No documents were moved.';
  });}}, label('Matters folder', input('matters_root', draft('settings.root', state.payload.matters_root), {required: true, oninput: remember('settings.root')})), label('Model letters folder (optional)', input('exemplars_dir', draft('settings.letters', state.payload.chatgpt?.exemplars_dir || ''), {oninput: remember('settings.letters')})),
    h('div',{class:'form-actions'},submitButton('Save folders')));
  return [pageTitle('Settings', 'Your local workspace and preferences.'), section('Workspace folders', line('Use a dedicated Matters folder. You may share it with the Claude version; work is coordinated between both apps.'),form),
    section('Workspace readiness', (state.payload.setup?.checks || []).map(check => h('div', {class: 'file-row'}, h('span', {text: ({uv:'Local workflow',ghostscript:'USCIS form preparation',libreoffice:'Word-to-PDF conversion',poppler:'PDF text reading'})[check.id] || check.label}), badge(check.ok ? 'Ready' : check.required ? 'Setup needed' : check.level==='recommended' ? 'Recommended' : 'Optional',!check.ok && check.required?'attention':''))), h('div',{class:'actions'},button('Check again', () => busy(() => load('', true))),button('Set up in chat',()=>ask('Set up Senior Associate / Matters for ChatGPT using its packaged setup skill. Check missing local tools and explain any required installation before making changes.')))),
    disclosure('Research privacy & advanced setup', disclosure('Local tools',(state.payload.setup?.checks||[]).filter(check=>['uv','ghostscript','poppler','libreoffice'].includes(check.id)).map(check=>h('div',{class:'file-row'},h('span',{text:check.label}),badge(check.ok?'Installed':'Not installed')))),line('Research queries must pass the matter privacy check before leaving this Mac. The optional local privacy hook covers supported local research tools; hosted web calls are outside its coverage.'),
      button('Review setup in chat', () => ask('Set up Senior Associate / Matters for ChatGPT using its packaged setup skill. Verify the local tools and show me its privacy hook for review.'))),
    line(`Version ${state.payload.version || '0.1.0'} · On this Mac`, 'footnote')];
}
function render() {
  const active=document.activeElement;
  const focusName=root.contains(active)?active.name:null;
  const focusText=root.contains(active) && active.tagName==='BUTTON'?active.textContent:null;
  const selection=focusName && typeof active.selectionStart==='number'?[active.selectionStart,active.selectionEnd]:null;
  const openDetails=[...root.querySelectorAll('details[open] summary')].map(el=>el.textContent);
  const body=!state.payload?[heading('Matters'),line(state.error?'Your workspace could not load.':'Opening your workspace…'),state.error?button('Try again',()=>busy(()=>load())):h('div',{class:'loading-lines','aria-hidden':true},h('span'),h('span'),h('span'))]
    :state.page==='new'?newMatter():state.page==='matter'?matter():state.page==='profile'?profile():state.page==='settings'?settings():home();
  root.setAttribute('aria-busy',String(state.busy));
  root.replaceChildren(toolbar(),h('main',{class:`content page-${state.page}`,id:'main'},
    state.error?h('div',{class:'banner error',role:'alert'},icon('info'),h('span',{text:state.error}),button('Dismiss',()=>{state.error='';render();})):null,
    state.notice?h('div',{class:'banner success',role:'status'},icon('check'),h('span',{text:state.notice})):null,
    state.fallback?section('Continue in the chat',line('Copy this request into your chat to continue.'),textarea('fallback',state.fallback,{readonly:true,'aria-label':'Chat request'}),button('Copy request',()=>busy(async()=>{await navigator.clipboard.writeText(state.fallback);state.notice='Copied.';}))):null,
    ...body),h('div',{class:'busy-indicator',role:state.busy?'status':null,'aria-label':state.busy?'Working':null,hidden:!state.busy}));
  root.querySelector('h1')?.setAttribute('tabindex','-1');
  root.querySelectorAll('details').forEach(el=>{if(openDetails.includes(el.querySelector('summary')?.textContent))el.open=true;});
  if(state.confirm) {
    const cfg=state.confirm;
    const cancel=()=>{state.confirm=null;render();root.querySelectorAll('button')[cfg.focusIndex]?.focus({preventScroll:true});};
    const dialog=h('div',{role:'dialog','aria-modal':'true','aria-labelledby':'confirmation-title',class:'confirm-dialog',onkeydown:e=>{
      if(e.key==='Escape'){e.preventDefault();cancel();}
      if(e.key==='Tab'){const buttons=[...e.currentTarget.querySelectorAll('button')];const i=buttons.indexOf(document.activeElement);if(e.shiftKey && i===0){e.preventDefault();buttons.at(-1).focus();}else if(!e.shiftKey && i===buttons.length-1){e.preventDefault();buttons[0].focus();}}
    }},h('h2',{id:'confirmation-title',text:cfg.title}),line(cfg.description),h('div',{class:'actions'},button('Cancel',cancel),button(cfg.label,()=>{state.confirm=null;cfg.action();},true)));
    root.querySelector('main').inert=true;root.querySelector('header').inert=true;
    root.append(h('div',{class:'dialog-backdrop'},dialog));
  }
  if(!state.confirm) {
    const next=focusName?root.querySelector(`[name="${CSS.escape(focusName)}"]`):focusText?[...root.querySelectorAll('button')].find(b=>b.textContent===focusText && !b.disabled):null;
    if(next){next.focus({preventScroll:true});if(selection)try{next.setSelectionRange(...selection);}catch{}}
  }
}
function hostContext(ctx) {if (!ctx) return; if (ctx.theme) applyDocumentTheme(ctx.theme); if (ctx.styles?.variables) applyHostStyleVariables(ctx.styles.variables); if (ctx.styles?.css?.fonts) applyHostFonts(ctx.styles.css.fonts);}
app.onhostcontextchanged = hostContext;
app.ontoolresult = result => {try {const {view} = unpack(result); if (view) {++readGeneration; accept(view); render();}} catch (error) {state.error = error.message; render();}};
app.ontoolcancelled = () => {state.error = 'The request was cancelled.'; render();};
render();
try {await app.connect(); state.connected = true; hostContext(app.getHostContext()); if (!state.payload) await load();}
catch {state.error = 'Could not connect to Matters. Reopen the plugin in a local desktop chat.'; render();}
setInterval(() => {
  if (state.connected && state.page === 'matter' && !state.busy && !document.hidden && !editing() && !matterDrafts()) load(c().path, true).catch(() => {});
}, 15000);
