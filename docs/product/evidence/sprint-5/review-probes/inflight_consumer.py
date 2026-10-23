"""Actual API + PostgreSQL, paused offline provider, concurrent brief/source mutation."""
import asyncio,hashlib,json,os,runpy,uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from staylead_platform.domains.hospitality.schemas.guest_brief import validate_guest_brief_proposal
from staylead_platform.platform.contracts.guest_brief import GuestBriefContext,GuestBriefProposal
from staylead_platform.infrastructure.persistence.store import get_guest_brief,apply_guest_brief_patch,get_active_snapshot,transition_source,get_guest_brief_receipt
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py')
e=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL']);m['apply_migrations'](e);m['import_fixture_pack'](e,m['FIXTURE_ROOT'])
class PausedProvider(m['BriefConsumerProvider']):
 def __init__(self):super().__init__();self.entered=Event();self.release=Event()
 async def generate(self,request):
  data=json.loads(request.input_text)
  if data.get('guest_brief_patch_enabled') is False and 'facts' in data:
   self.entered.set()
   assert await asyncio.to_thread(self.release.wait,8),'review probe release timed out'
  return await super().generate(request)
results={}
for kind in ['brief','source']:
 p=PausedProvider();client,s=m['_client'](e,p);rid=str(uuid.uuid4());q=m['EDIT']+' How many nights is my stay?'
 with ThreadPoolExecutor(max_workers=1) as pool:
  f=pool.submit(m['_post'],client,s,{'request_id':rid,'question':q})
  assert p.entered.wait(5),'answer did not reach pause'
  saved=get_guest_brief(e,session_id=s['session_id'],hotel_id='HTL-CITY01');assert saved.brief_version==1
  if kind=='brief':
   context=GuestBriefContext(s['session_id'],'HTL-CITY01',str(uuid.uuid4()),1,str(uuid.uuid4()),'Actually three adults.')
   validated=validate_guest_brief_proposal(saved,GuestBriefProposal(({'op':'set_adults','count':3},)))
   apply_guest_brief_patch(e,context=context,mutation=validated,payload_hash=hashlib.sha256(context.source_utterance.encode()).hexdigest())
  else:
   snapshot=get_active_snapshot(e,'HTL-CITY01');source=snapshot.sources[0]
   transition_source(e,hotel_id='HTL-CITY01',source_id=source.source_id,expected_generation=snapshot.generation,expected_version=source.source_version,expected_source_hash=source.source_hash,operation_id=str(uuid.uuid4()),action='revoke')
  p.release.set();r=f.result(timeout=10)
 data=r.json();assert data['status']=='partial_success' and data['answer_status']=='failed',data
 assert 'answer' not in data,data
 expected='brief_version_conflict' if kind=='brief' else 'stale_source';assert data['error']['code']==expected,data
 before=p.calls;replayed=m['_post'](client,s,{'request_id':rid,'question':q});assert replayed.status_code==200 and p.calls==before
 receipt=get_guest_brief_receipt(e,session_id=s['session_id'],hotel_id='HTL-CITY01',receipt_id=rid)['receipt']
 assert receipt.brief_version_before==0 and receipt.brief_version_after==1 and len(data['guest_brief']['party']['children'])==1
 results[kind]={'http':r.status_code,'error':expected,'current_brief_version':data['guest_brief']['brief_version'],'historical_receipt_version':receipt.brief_version_after,'answer_published':False,'provider_calls':p.calls,'replay_extra_calls':p.calls-before}
print(json.dumps(results,indent=2));e.dispose()
