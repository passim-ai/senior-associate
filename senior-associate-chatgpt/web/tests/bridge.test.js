import {test} from 'node:test';
import assert from 'node:assert/strict';
import {handoffRun, sendText, unpack} from '../src/bridge.js';

test('reads UI-only metadata separately from model data', () => {
  assert.deepEqual(unpack({structuredContent: {status: 'ok'}, _meta: {view: {matters: [1]}}}), {data: {status: 'ok'}, view: {matters: [1]}});
});
test('MCP errors cannot be treated as success', () => {
  assert.throws(() => unpack({isError: true, content: [{type: 'text', text: 'Lease held'}]}), /Lease held/);
});
test('successful message hands off the reserved run exactly once', async () => {
  const calls = [];
  const app = {callServerTool: async q => {calls.push(q); return {structuredContent: {run_id: 'r1', prompt: 'verified brief'}, _meta: {view: {matter: {}}}};}, sendMessage: async q => {calls.push(q); return {};} };
  await handoffRun(app, {matter_path: '/fictional/matter', kind: 'build'});
  assert.equal(calls.length, 2);
  assert.equal(calls[1].content[0].text, 'verified brief');
});
test('host rejection cancels only the exact pending reservation', async () => {
  const calls = [];
  const app = {callServerTool: async q => {calls.push(q); return q.name === 'prepare_matter_run' ? {structuredContent: {run_id: 'r2', prompt: 'brief'}} : {_meta: {view: {start: 'cancelled'}}};}, sendMessage: async () => ({isError: true})};
  await assert.rejects(() => handoffRun(app, {matter_path: '/fictional/matter', kind: 'review_docs'}), error => {
    assert.match(error.message, /No pending start/); assert.match(error.fallback, /prepare_matter_run/); assert.doesNotMatch(error.fallback, /r2/); return true;
  });
  assert.deepEqual(calls[1], {name: 'cancel_matter_start', arguments: {matter_path: '/fictional/matter', run_id: 'r2'}});
});
test('ambiguous send failure preserves an adopted run and avoids duplicate fallback', async () => {
  const app = {callServerTool: async q => q.name === 'prepare_matter_run' ? {structuredContent: {run_id: 'r3', prompt: 'brief'}} : {_meta: {view: {start: 'taken_up'}}}, sendMessage: async () => {throw Error('lost connection');}};
  await assert.rejects(() => handoffRun(app, {matter_path: '/fictional/matter', kind: 'build'}), error => {
    assert.match(error.message, /may have started/); assert.equal(error.fallback, ''); return true;
  });
});
test('OpenAI message extension is capability-detected and targets the active chat', async () => {
  let sent;
  await sendText({getHostCapabilities: () => ({experimental: {'openai/message': {}}}), sendMessage: async q => {sent = q; return {}; }}, 'request');
  assert.deepEqual(sent._meta, {'openai/message': {target: 'active', send: true}});
});
