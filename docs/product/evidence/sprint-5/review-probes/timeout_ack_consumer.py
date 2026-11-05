"""Actual API: patch commit succeeds, acknowledgement stalls beyond turn deadline."""
import json,os,runpy,time,uuid
from unittest.mock import patch
import staylead_platform.composition.dependencies.guest_chat as composition
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py');e=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL'])
p=m['BriefConsumerProvider']();client,_=m['_client'](e,p);client.app.state.guest_chat._settings.ai_turn_timeout_seconds=1.0
s=client.post('/v1/guest/sessions',json={'hotel_slug':'lagoon-family-demo'}).json();rid=str(uuid.uuid4());body={'request_id':rid,'question':m['EDIT']};original=composition.apply_guest_brief_patch

def delayed(*a,**kw):
 result=original(*a,**kw)
 time.sleep(1.5)
 return result
with patch.object(composition,'apply_guest_brief_patch',delayed):
 first=m['_post'](client,s,body)
f=first.json();assert first.status_code==504,first.text
from staylead_platform.infrastructure.persistence.store import get_guest_brief
b=get_guest_brief(e,session_id=s['session_id'],hotel_id='HTL-BEACH02');assert len(b.data['party']['children'])==1
# Same-ID would recover safely, but the current UI classifies the received code as new-request.
calls=p.calls;replay=m['_post'](client,s,body);assert replay.status_code==200 and p.calls==calls
new=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'question':m['EDIT']});assert new.status_code==200,new.text
assert len(new.json()['guest_brief']['party']['children'])==2
print(json.dumps({'timeout_http':first.status_code,'timeout_error':f['error'],'partial_returned':f.get('status')=='partial_success','children_after_timed_out_commit':1,'same_id_replay_status':replay.json()['status'],'same_id_extra_calls':0,'children_after_offered_raw_new_id_retry':2},indent=2));e.dispose()
