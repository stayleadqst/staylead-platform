"""Final actual API proof: turn timeout after durable commit returns recoverable receipt."""
import json,os,runpy,time,uuid
from unittest.mock import patch
import staylead_platform.composition.dependencies.guest_chat as composition
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py');e=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL'])
p=m['BriefConsumerProvider']();client,_=m['_client'](e,p);client.app.state.guest_chat._settings.ai_turn_timeout_seconds=1.0
s=client.post('/v1/guest/sessions',json={'hotel_slug':'lagoon-family-demo'}).json();rid=str(uuid.uuid4());body={'request_id':rid,'question':m['EDIT']};original=composition.apply_guest_brief_patch

def delayed(*a,**kw):
 result=original(*a,**kw);time.sleep(1.5);return result
with patch.object(composition,'apply_guest_brief_patch',delayed):
 first=m['_post'](client,s,body)
f=first.json();assert f['status']=='partial_success' and f['brief_receipt']['request_id']==rid,first.text
assert f['answer_status']=='failed' and len(f['guest_brief']['party']['children'])==1
calls=p.calls;replay=m['_post'](client,s,body);assert replay.status_code==200 and p.calls==calls
resume=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'answer_only_receipt_id':rid});assert resume.status_code==200,resume.text
assert len(resume.json()['guest_brief']['party']['children'])==1
print(json.dumps({'timeout_http':first.status_code,'error':f['error']['code'],'partial_returned':True,'receipt_returned':True,'children_after_timeout':1,'same_id_replay_http':replay.status_code,'same_id_extra_calls':0,'answer_only_resume_http':resume.status_code,'children_after_resume':1},indent=2));e.dispose()
