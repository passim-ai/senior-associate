#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.30,<2", "pypdf>=6.0", "reportlab>=4.0"]
# ///
"""Local protocol test host. Every file action is confined to fictional temp data.

Not shipped in the plugin. No live client root is ever read, and native file
pickers/open commands are replaced by test fixture choices.
"""
import asyncio
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

HERE = Path(__file__).resolve().parents[1]
PACKAGE = Path((HERE / 'dist/latest.txt').read_text().strip())
TEMP = tempfile.TemporaryDirectory(prefix='sa-browser-fictional-')
SANDBOX = Path(TEMP.name).resolve()
os.environ['SENIOR_ASSOCIATE_MATTERS_ROOT'] = str(SANDBOX / 'Matters')
os.environ['SENIOR_ASSOCIATE_CHATGPT_DATA'] = str(SANDBOX / 'settings')
os.environ['SENIOR_ASSOCIATE_LOG_FILE'] = str(SANDBOX / 'server.log')
TOKEN = secrets.token_hex(24)
source = SANDBOX / 'Fictional evidence.txt'
source.write_text('FICTIONAL TEST ONLY. A client evidence document for import testing.')
sys.path.insert(0, str(PACKAGE / 'chatgpt'))
import adapter
import server
from sa_server import actions
from scripts.matter_state import write_json_atomic, OPEN_ITEMS_FILE
# Shared actions import picker functions directly: patch that exact boundary.
actions.pick_files = lambda: [source]
actions.pick_folder = lambda: None
actions.open_path = lambda path: None
actions.reveal_path = lambda path: None
# The lease watcher itself is covered separately; browser tests do not hold the Mac awake.
from scripts import keep_awake
keep_awake.start = lambda matter, run_id: None
MCP = server.build_server()

HOST = '''<!doctype html><html><head><title>Matters protocol test host</title><style>body{margin:0;background:#fff}iframe{width:100%;height:100vh;border:0}</style></head><body>
<iframe id="widget" src="/widget" title="Matters" sandbox="allow-scripts allow-same-origin"></iframe>
<script>
window.messages=[];window.links=[];window.contexts=[];window.toolCalls=[];window.rejectMessages=false;
const frame=document.getElementById('widget');
window.pushResult = result => frame.contentWindow.postMessage({jsonrpc:'2.0',method:'ui/notifications/tool-result',params:result},location.origin);
window.fixture = async args => {const r=await fetch('/fixture',{method:'POST',headers:{'Content-Type':'application/json','X-Test-Token':'__TOKEN__'},body:JSON.stringify(args)});return r.json();};
window.addEventListener('message',async event=>{
 if(event.source!==frame.contentWindow||event.origin!==location.origin)return;
 const m=event.data;if(m.jsonrpc!=='2.0'||m.id===undefined)return;
 let result={};try{
  if(m.method==='ui/initialize') result={protocolVersion:'2026-01-26',hostInfo:{name:'Senior Associate test host',version:'1.0.0'},hostCapabilities:{serverTools:{},message:{text:{}},updateModelContext:{text:{}},experimental:{'openai/message':{}}},hostContext:{theme:'light',displayMode:'inline',availableDisplayModes:['inline','fullscreen']}};
  else if(m.method==='tools/call'){window.toolCalls.push(m.params.name);const r=await fetch('/rpc',{method:'POST',headers:{'Content-Type':'application/json','X-Test-Token':'__TOKEN__'},body:JSON.stringify(m.params)});result=await r.json();}
  else if(m.method==='ui/message'){window.messages.push(m.params);result={isError:window.rejectMessages};}
  else if(m.method==='ui/open-link'){window.links.push(m.params.url);result={isError:false};}
  else if(m.method==='ui/update-model-context')window.contexts.push(m.params);
  frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,result},location.origin);
 }catch(e){frame.contentWindow.postMessage({jsonrpc:'2.0',id:m.id,error:{code:-32603,message:e.message}},location.origin);}
});
</script></body></html>'''.replace('__TOKEN__', TOKEN)

class Handler(BaseHTTPRequestHandler):
    def send(self, data, content_type='application/json', status=200):
        data = data.encode() if isinstance(data, str) else data
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == '/': return self.send(HOST, 'text/html')
        if self.path == '/widget': return self.send((PACKAGE / 'web/dist/index.html').read_bytes(), 'text/html')
        self.send('not found', 'text/plain', 404)

    def do_POST(self):
        if self.headers.get('X-Test-Token') != TOKEN: return self.send('{}', status=403)
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        try:
            if self.path == '/rpc':
                result = asyncio.run(MCP.call_tool(body['name'], body.get('arguments', {})))
                return self.send(result.model_dump_json(by_alias=True, exclude_none=True))
            if self.path == '/fixture' and body.get('change_source'):
                matter=Path(body['path']).resolve()
                matter.relative_to(SANDBOX / 'Matters')
                (matter / 'Fictional evidence.txt').write_text('Changed fictional source')
                return self.send(json.dumps({'result':{'_meta':{'view':adapter.view(adapter.context(),str(matter))}}}))
            if self.path == '/fixture':
                ctx = adapter.context()
                result = adapter.action(ctx, {'op': 'create', 'name': body['name'], 'matter_type': 'n400', 'filing_posture': 'new filing packet'})
                matter = Path(result['matter']['path'])
                (matter / 'Fictional evidence.txt').write_text('FICTIONAL TEST ONLY')
                write_json_atomic(matter / OPEN_ITEMS_FILE, {'schema_version': 2, 'packet_status': 'draft', 'items': [
                    {'id':'mailing-address', 'type':'attorney_decision', 'who':'attorney', 'title':'Confirm the mailing address',
                     'question':'Which mailing address should we use?', 'recommendation':'Use counsel’s address.',
                     'detail':'A fictional question for interface testing.', 'blocks_filing':True, 'status':'open', 'stage':'docs_review'}]})
                memo = matter / 'output/deliverables/Attorney Memo.md'
                memo.parent.mkdir(parents=True,exist_ok=True)
                memo.write_text('# Fictional attorney memo\n\nThis is a UI fixture, not legal work.\n<script>window.fixtureXss = true</script>')
                (matter / 'output/deliverables/Client Request.md').write_text('Please confirm the mailing address. Fictional fixture only.')
                if body.get('reviewed_packet'):
                    sys.path.insert(0,str(HERE.parent / 'tests'))
                    from packet_fixture import reviewed_packet
                    reviewed_packet(matter,PACKAGE)
                    adapter.action(ctx,{'op':'save_profile','profile':{'attorney_name':'Fictional Browser Attorney'}})
                return self.send(json.dumps({'path': str(matter), 'result': {'structuredContent': {'app':'senior-associate-chatgpt'}, '_meta': {'view': adapter.view(ctx, str(matter))}}}))
            self.send('{}', status=404)
        except Exception as exc:
            self.send(json.dumps({'isError': True, 'content': [{'type':'text','text':str(exc)}]}))

    def log_message(self, *args): pass

if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', 4178), Handler).serve_forever()
