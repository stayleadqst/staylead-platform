"""Reproduce a committed patch whose acknowledgement is lost before the caller sees it."""
import json,os,runpy,uuid
from unittest.mock import patch
from sqlalchemy.exc import OperationalError
import staylead_platform.composition.dependencies.guest_chat as composition
m=runpy.run_path('tests/integration/test_sprint5_consumer_postgres.py')
e=m['create_database_engine'](os.environ['STAYLEAD_TEST_DATABASE_URL'])
m['apply_migrations'](e);m['import_fixture_pack'](e,m['FIXTURE_ROOT'])
p=m['BriefConsumerProvider']();client,s=m['_client'](e,p);original=composition.apply_guest_brief_patch

def lost(*args,**kwargs):
 original(*args,**kwargs)
 raise OperationalError('synthetic commit acknowledgement unavailable',None,Exception('synthetic'))
with patch.object(composition,'apply_guest_brief_patch',lost):
 r=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'question':m['EDIT']})
first=r.json();assert r.status_code==503
from staylead_platform.infrastructure.persistence.store import get_guest_brief
brief1=get_guest_brief(e,session_id=s['session_id'],hotel_id='HTL-CITY01')
assert len(brief1.data['party']['children'])==1
# Follow the actual UI classifier's new-request retry for this rejection.
r2=m['_post'](client,s,{'request_id':str(uuid.uuid4()),'question':m['EDIT']})
assert r2.status_code==200
brief2=r2.json()['guest_brief']
assert len(brief2['party']['children'])==2
print(json.dumps({'initial_http':r.status_code,'initial_error':first['error'],'child_count_after_lost_ack':1,'raw_new_id_retry_http':r2.status_code,'child_count_after_ui_new_id_retry':2},indent=2))
e.dispose()
