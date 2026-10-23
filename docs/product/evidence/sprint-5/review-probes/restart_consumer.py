"""Independent actual-API/PostgreSQL restart and scoped resume probe. Offline provider."""
import json,os,runpy,uuid
from pathlib import Path
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py')
engine=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL'])
m['apply_migrations'](engine);m['import_fixture_pack'](engine,m['FIXTURE_ROOT'])
p=m['BriefConsumerProvider']();client,session=m['_client'](engine,p)
post=m['_post'];initial_id=str(uuid.uuid4())
first=post(client,session,{'request_id':initial_id,'question':m['EDIT']});assert first.status_code==200
first_data=first.json();child_id=first_data['guest_brief']['party']['children'][0]['member_id']
for _ in range(5):
 r=post(client,session,{'request_id':str(uuid.uuid4()),'question':'What are the breakfast hours?'});assert r.status_code==200
# Build a new application/provider and use only the existing authenticated session.
replacement=m['BriefConsumerProvider']();new_client,_=m['_client'](engine,replacement)
r=post(new_client,session,{'request_id':str(uuid.uuid4()),'question':'How many nights is my stay?'});assert r.status_code==200
body=r.json();assert body['brief_version_used']==1 and body['guest_brief']['dates']['nights']==3
assert body['guest_brief']['party']['children'][0]['member_id']==child_id
input=next(x for x in reversed(replacement.inputs) if x.get('question')=='How many nights is my stay?')
assert not any(x['content']==m['EDIT'] for x in input['recent_context'])
other_provider=m['BriefConsumerProvider']();foreign_client,foreign=m['_client'](engine,other_provider)
foreign_response=post(foreign_client,foreign,{'request_id':str(uuid.uuid4()),'answer_only_receipt_id':initial_id})
assert foreign_response.status_code==404 and other_provider.calls==0
print(json.dumps({'restart_read_from_storage':True,'origin_outside_context':True,'stable_member_preserved':True,'brief_version_after_five_faqs':body['guest_brief']['brief_version'],'foreign_receipt_http':foreign_response.status_code,'foreign_provider_calls':other_provider.calls,'consumer_trace_calls':body['trace']['calls']},indent=2))
engine.dispose()
