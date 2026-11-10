// Small transport helpers shared by the UI and failure-path tests.
export function unpack(result) {
  if (result?.isError) throw new Error((result.content || []).map(c => c.text || '').join('\n') || 'The request failed.');
  return {data: result?.structuredContent || {}, view: result?._meta?.view || null};
}

export async function sendText(app, text) {
  const extended = app.getHostCapabilities?.()?.experimental?.['openai/message'] !== undefined;
  const result = await app.sendMessage({role: 'user', content: [{type: 'text', text}],
    ...(extended ? {_meta: {'openai/message': {target: 'active', send: true}}} : {})});
  if (result?.isError) throw new Error('ChatGPT did not accept the request.');
}

export async function handoffRun(app, args) {
  const {data, view} = unpack(await app.callServerTool({name: 'prepare_matter_run', arguments: args}));
  if (!data.run_id || !data.prompt) throw new Error('The server did not return an execution brief.');
  try {
    await sendText(app, data.prompt);
  } catch (error) {
    // cancel_start is fenced: an ambiguously delivered request adopted by a worker
    // keeps its lease. Never release a worker's lease based on a transport error.
    let cancelled = false;
    try {
      const result = unpack(await app.callServerTool({name: 'cancel_matter_start', arguments: {matter_path: args.matter_path, run_id: data.run_id}}));
      cancelled = result.view?.start === 'cancelled' || result.view?.start === 'gone';
    } catch { /* retain the lease until its owner or attorney resolves it */ }
    const failure = new Error(cancelled
      ? 'The request could not reach the chat. No pending start is reserved; try again or copy the request below.'
      : 'The connection was interrupted. Check the chat before retrying; the run may have started.');
    failure.fallback = cancelled
      ? `Use Senior Associate / Matters to ${args.kind.replaceAll('_', ' ')} for matter ${JSON.stringify(args.matter_path)}. Call prepare_matter_run with kind ${JSON.stringify(args.kind)}${args.stage_id ? ` and stage_id ${JSON.stringify(args.stage_id)}` : ''}${args.note ? `. My instructions: ${args.note}` : ''}, then follow its brief.`
      : '';
    throw failure;
  }
  return {data, view};
}
