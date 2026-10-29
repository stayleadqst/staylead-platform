"""Actual API replay lookup outage must not invite raw-edit new-ID retry."""
import json,os,runpy,uuid
from unittest.mock import patch
from sqlalchemy.exc import OperationalError
import staylead_platform.composition.dependencies.guest_chat as composition
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py');e=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL'])
p=m['BriefConsumerProvider']();client,_=m['_client'](e,p)
s=client.post('/v1/guest/sessions',json={'hotel_slug':'lagoon-family-demo'}).json();rid=str(uuid.uuid4());body={'request_id':rid,'question':m['EDIT']}
first=m['_post'](client,s,body);assert first.status_code==200,first.text
calls=p.calls
with patch.object(composition,'get_guest_brief',side_effect=OperationalError('synthetic replay lookup failure',None,Exception('synthetic'))):
 replay=m['_post'](client,s,body)
assert replay.status_code==503,replay.text
assert p.calls==calls
# This is exactly the current UI classifier's raw new-request action.
retried=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'question':m['EDIT']});assert retried.status_code==200,retried.text
assert len(retried.json()['guest_brief']['party']['children'])==2
print(json.dumps({'initial_http':first.status_code,'replay_http':replay.status_code,'replay_error':replay.json()['error'],'replay_extra_provider_calls':0,'child_count_before_replay':1,'child_count_after_offered_raw_retry':2},indent=2));e.dispose()
