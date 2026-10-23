"""Actual API + PostgreSQL high-overlap preparation/final-answer and FAQ-only path."""
import json,os,runpy,uuid
from staylead_platform.platform.contracts.ai_provider import GenerationResult,Usage
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py')
e=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL'])
class HighProvider:
 def __init__(self):self.inputs=[];self.patched=False
 async def generate(self,request):
  body=json.loads(request.input_text);self.inputs.append(body)
  assert 'candidate_index' not in body,'High overlap unexpectedly selected evidence'
  facts=body['facts'];assert facts
  answer={'supported_claims':[{'text':'The hotel record confirms breakfast information.','fact_ids':[facts[0]['fact_id']]}],'unknowns':[],'conflicts':[]}
  if not self.patched:
   assert body['guest_brief_patch_enabled'] is True
   answer['guest_patch']={'ops':[{'op':'set_adults','count':2}]};self.patched=True
  elif body['guest_brief_patch_enabled'] is False:
   assert body['guest_brief']['data']['party']['adults']==2
  return GenerationResult(json.dumps(answer),'fake','high-overlap-offline','offline-fake',str(uuid.uuid4()),Usage())
p=HighProvider();client,_=m['_client'](e,p)
r=client.post('/v1/guest/sessions',json={'hotel_slug':'lagoon-family-demo'});assert r.status_code==201;s=r.json()
first=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'question':'breakfast'});assert first.status_code==200,first.text
second=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'question':'breakfast'});assert second.status_code==200,second.text
assert first.json()['trace']['calls']==2 and second.json()['trace']['calls']==1
assert first.json()['guest_brief']['brief_version']==1 and second.json()['guest_brief']['brief_version']==1
assert [x['guest_brief_patch_enabled'] for x in p.inputs]==[True,False,True]
print(json.dumps({'high_overlap_mixed_calls':first.json()['trace']['calls'],'high_overlap_faq_only_calls':second.json()['trace']['calls'],'brief_version_after_faq':second.json()['guest_brief']['brief_version'],'patch_enabled_sequence':[x['guest_brief_patch_enabled'] for x in p.inputs]},indent=2));e.dispose()
