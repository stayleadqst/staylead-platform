import os
import runpy,json,uuid
from pathlib import Path
from datetime import datetime,UTC,timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence import store
from staylead_platform.entrypoints.app import create_app
from staylead_platform.platform.guest_context.sessions.signing import issue_token
old=runpy.run_path(os.environ["STAYLEAD_SCHEMA3_STORE_FILE"]);helpers=runpy.run_path('tests/integration/test_sprint1_postgres.py')
dsn=os.environ["STAYLEAD_REVIEW_DATABASE_URL"];e=create_database_engine(dsn)
assert old['schema_version'](e)==3
with e.connect() as c:fact=c.execute(select(old['knowledge_facts']).where(old['knowledge_facts'].c.hotel_id=='HTL-CITY01')).mappings().first()
session_id=str(uuid.uuid4());request_id='old-valid-response';expiry=datetime.now(UTC)+timedelta(hours=1);question='What are breakfast hours?';answer='Legacy current response ['+fact['fact_id']+']'
old['create_session'](e,session_id,'HTL-CITY01',expiry)
old['reserve_request'](e,session_id=session_id,hotel_id='HTL-CITY01',request_id=request_id,question=question)
evidence=[{'fact_id':fact['fact_id'],'hotel_id':'HTL-CITY01','source_id':fact['source_id'],'source_version':fact['source_version'],'section':fact['section'],'fact_version':fact['fact_version'],'imported_at':fact['imported_at'].isoformat()}]
old['complete_request'](e,session_id=session_id,hotel_id='HTL-CITY01',request_id=request_id,question=question,answer=answer,evidence=evidence,response_fields={'unknowns':[],'trace':{},'media':[]})
print(json.dumps({'stage':'before_upgrade','schema':old['schema_version'](e),'session_state_version':old['get_session'](e,session_id)['state_version'],'city_facts':len(old['facts_for_hotel'](e,'HTL-CITY01'))}))
store.apply_migrations(e)
snap=store.get_active_snapshot(e,'HTL-CITY01')
print(json.dumps({'stage':'after_upgrade','schema':store.schema_version(e),'source_count':len(snap.sources),'session_state_version':store.get_session(e,session_id)['state_version'],'city_facts':len(store.facts_for_hotel(e,'HTL-CITY01'))}))
provider=helpers['FakeProvider']();app=create_app(helpers['settings_for'](dsn),engine=e,provider=provider)
token=issue_token(secret='offline-test-signing-secret',session_id=session_id,hotel_id='HTL-CITY01',expires_at=int(expiry.timestamp()));headers={'Authorization':'Bearer '+token}
with TestClient(app) as client:
 for request in [request_id,'new-after-upgrade']:
  response=client.post(f'/v1/guest/sessions/{session_id}/messages',json={'request_id':request,'question':question},headers=headers)
  print(json.dumps({'probe':'schema3-existing-session-'+request,'status':response.status_code,'error':response.json().get('error',{}).get('code'),'offline_provider_calls':provider.calls}))
source=next(s for s in snap.sources if s.source_id==fact['source_id'])
store.transition_source(e,hotel_id='HTL-CITY01',source_id=source.source_id,expected_generation=snap.generation,expected_version=source.source_version,expected_source_hash=source.source_hash,operation_id='review-legacy-revoke',action='revoke')
history=store.recent_messages(e,session_id,'HTL-CITY01')
print(json.dumps({'probe':'legacy-history-after-revoke','old_assistant_prose_retained':any(x['content']==answer for x in history),'session_state_version':store.get_session(e,session_id)['state_version']}))
e.dispose()
