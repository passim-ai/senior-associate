#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.30,<2", "pypdf>=6.0", "reportlab>=4.0"]
# ///
"""Real CLI/stdio lifecycle tests. Stage content is synthetic, not model authored."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from contextlib import asynccontextmanager
from pypdf import PdfReader
from packet_fixture import reviewed_packet

ROOT=Path(__file__).resolve().parents[1]

@asynccontextmanager
async def client(kind,plugin,env):
    if kind=='claude':
        async def call(op,**args):
            process=subprocess.run([sys.executable,str(plugin/'server/cli.py'),json.dumps({'op':op,**args})],env=env,capture_output=True,text=True)
            value=json.loads(process.stdout)
            if process.returncode: raise ValueError(value.get('error',process.stderr))
            return value
        yield call
    else:
        from mcp import ClientSession,StdioServerParameters
        from mcp.client.stdio import stdio_client
        async with stdio_client(StdioServerParameters(command='sh',args=[str(plugin/'chatgpt/run.sh')],env=env)) as (r,w):
            async with ClientSession(r,w) as session:
                await session.initialize()
                async def call(op,**args):
                    if op=='state':
                        name='matters_view';arguments=args
                    elif op=='start_run':
                        name='prepare_matter_run';arguments=args
                    else:
                        name='matters_action';arguments={'request':{'op':op,**args}}
                    result=await session.call_tool(name,arguments)
                    if result.isError: raise ValueError(' '.join(x.text for x in result.content))
                    return result.structuredContent if op=='start_run' else (result.meta or {}).get('view') or result.structuredContent
                yield call

async def exercise(kind):
    plugin=ROOT/'senior-associate-claude' if kind=='claude' else Path((ROOT/'senior-associate-chatgpt/dist/latest.txt').read_text().strip())
    with tempfile.TemporaryDirectory(prefix=f'packet-{kind}-e2e-') as folder:
        folder=Path(folder).resolve();env=dict(os.environ,SENIOR_ASSOCIATE_MATTERS_ROOT=str(folder/'Matters'),SENIOR_ASSOCIATE_CHATGPT_DATA=str(folder/'settings'),SENIOR_ASSOCIATE_LOG_FILE=str(folder/'server.log'),PYTHONDONTWRITEBYTECODE='1')
        async with client(kind,plugin,env) as call:
            empty=await call('state');assert not empty['matters']
            created=await call('create',name='Fictional Integration',matter_type='n400',filing_posture='new filing packet')
            matter=Path(created['matter']['path'])
            source=matter/'Fictional evidence.txt';source.write_text('Fictional identity evidence')
            await call('save_profile',profile={'attorney_name':'Fictional Test Attorney'})
            await call('set_meta',matter_path=str(matter),forum='USCIS',circuit='ca5',jurisdiction_basis='Fictional residence')
            await call('save_answer',matter_path=str(matter),key='strategy',question='Scope?',answer='Synthetic integration only')
            packet=reviewed_packet(matter,plugin)
            view=await call('state',matter_path=str(matter));ready=view['matter']['filing_readiness']
            assert ready['eligible'],ready
            assert not ready['approved'] and ready['risks']
            assert 'DRAFT' in PdfReader(packet).pages[0].extract_text()
            try: await call('approve_filing',matter_path=str(matter),digest=ready['digest'])
            except ValueError as exc: assert 'Explain your decision' in str(exc)
            else: raise AssertionError('approval without a reason for the open points accepted')
            approved=await call('approve_filing',matter_path=str(matter),digest=ready['digest'],risk_note='Synthetic test acknowledges the fictional risk.')
            assert approved['matter']['filing_readiness']['approved']
            exports=list((matter/'output/deliverables/Approved for filing').rglob('Filing Packet.pdf'))
            assert len(exports)==1
            pdf=PdfReader(exports[0]);assert 'DRAFT' not in pdf.pages[0].extract_text()
            assert pdf.outline[0].title=='Synthetic evidence'
            assert 'FICTIONAL TEST ONLY' in pdf.pages[0].extract_text()
            source.write_text('Changed fictional evidence')
            stale=await call('state',matter_path=str(matter));assert not stale['matter']['filing_readiness']['approved']
            try: await call('approve_filing',matter_path=str(matter),digest=ready['digest'],risk_note='Synthetic test')
            except ValueError: pass
            else: raise AssertionError('stale approval accepted')
            await call('mark_filed',matter_path=str(matter))
            await call('unmark_filed',matter_path=str(matter))
            await call('archive',matter_path=str(matter))
            await call('unarchive',matter_path=str(matter))
            assert (await call('state',matter_path=str(matter)))['matter']['answers']['strategy']['answer']=='Synthetic integration only'
        print(f'{kind}: real transport lifecycle passed; draft, risk gate, approved export, bookmarks, changed-source rejection, saved answer, archive/unarchive')

async def coordination():
    claude=ROOT/'senior-associate-claude'
    chatgpt=Path((ROOT/'senior-associate-chatgpt/dist/latest.txt').read_text().strip())
    with tempfile.TemporaryDirectory(prefix='packet-cross-client-e2e-') as directory:
        folder=Path(directory).resolve()
        env=dict(os.environ,SENIOR_ASSOCIATE_MATTERS_ROOT=str(folder/'Matters'),SENIOR_ASSOCIATE_CHATGPT_DATA=str(folder/'settings'),SENIOR_ASSOCIATE_LOG_FILE=str(folder/'server.log'),PYTHONDONTWRITEBYTECODE='1')
        async with client('claude',claude,env) as c, client('chatgpt',chatgpt,env) as g:
            made=await c('create',name='Fictional Shared Matter',matter_type='n400',filing_posture='new filing packet')
            matter=made['matter']['path']
            for owner,other in ((c,g),(g,c)):
                start=await owner('start_run',matter_path=matter,kind='build')
                run_id=start['run_id']
                try: await other('start_run',matter_path=matter,kind='build')
                except ValueError: pass
                else: raise AssertionError('other client started over an active lease')
                # A different reservation must not release this client's lease.
                await other('cancel_start',matter_path=matter,run_id='wrong-run')
                active=await other('state',matter_path=matter)
                assert active['matter']['status']['lease']['run_id']==run_id
                await owner('cancel_start',matter_path=matter,run_id=run_id)
            print('both: shared-matter lease exclusion and exact-run cancellation passed through both real transports')

if __name__=='__main__':
    if len(sys.argv)>1:
        asyncio.run(coordination() if sys.argv[1]=='coordination' else exercise(sys.argv[1]))
    else:
        for kind in ('claude','chatgpt','coordination'):
            subprocess.run([sys.executable,__file__,kind],check=True)
