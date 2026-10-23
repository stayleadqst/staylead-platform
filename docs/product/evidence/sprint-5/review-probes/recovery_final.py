"""Final independent recovery checks. Retains earlier failed-observation artifacts."""
import json,os,runpy,uuid
from unittest.mock import patch
from sqlalchemy.exc import OperationalError
import staylead_platform.composition.dependencies.guest_chat as composition
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py');e=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL'])
p=m['BriefConsumerProvider']();client,_=m['_client'](e,p)
s=client.post('/v1/guest/sessions',json={'hotel_slug':'lagoon-family-demo'}).json();original=composition.apply_guest_brief_patch
rid=str(uuid.uuid4());body={'request_id':rid,'question':m['EDIT']}
def lost(*a,**kw):
 original(*a,**kw)
 raise OperationalError('synthetic lost acknowledgement',None,Exception('synthetic'))
with patch.object(composition,'apply_guest_brief_patch',lost):
 first=m['_post'](client,s,body)
f=first.json();assert f['status']=='partial_success' and len(f['guest_brief']['party']['children'])==1,f
assert f['brief_receipt']['request_id']==rid and f['answer_status']=='failed'
calls=p.calls
replay=m['_post'](client,s,body);assert replay.status_code==200 and p.calls==calls
resume=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'answer_only_receipt_id':rid});assert resume.status_code==200,resume.text
assert len(resume.json()['guest_brief']['party']['children'])==1
# Replay lookup failure after a completed edit must preserve same-ID recovery.
s2=client.post('/v1/guest/sessions',json={'hotel_slug':'lagoon-family-demo'}).json();rid2=str(uuid.uuid4());body2={'request_id':rid2,'question':m['EDIT']}
r2=m['_post'](client,s2,body2);assert r2.status_code==200,r2.text;calls2=p.calls
with patch.object(composition,'get_guest_brief',side_effect=OperationalError('synthetic replay lookup failure',None,Exception('synthetic'))):
 lookup=m['_post'](client,s2,body2)
assert lookup.status_code==503,lookup.text
assert p.calls==calls2
recovered=m['_post'](client,s2,body2);assert recovered.status_code==200 and p.calls==calls2
assert len(recovered.json()['guest_brief']['party']['children'])==1
print(json.dumps({'lost_ack':{'http':first.status_code,'status':f['status'],'error':f['error']['code'],'receipt_returned':True,'replay_extra_provider_calls':0,'answer_only_resume_http':resume.status_code,'children_after_resume':1},'completed_replay_lookup_failure':{'http':lookup.status_code,'error':lookup.json()['error'],'same_id_recovery_http':recovered.status_code,'replay_extra_provider_calls':0,'children_after_same_id_recovery':1}},indent=2));e.dispose()
