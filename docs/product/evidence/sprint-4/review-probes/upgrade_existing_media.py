import os
import runpy,json,uuid
from datetime import datetime,UTC,timedelta
from fastapi.testclient import TestClient
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.domains.hospitality.registration.pack_schema import validate_pack
from staylead_platform.infrastructure.persistence import store
from staylead_platform.entrypoints.app import create_app
from staylead_platform.platform.guest_context.sessions.signing import issue_token
old=runpy.run_path(os.environ["STAYLEAD_SCHEMA3_STORE_FILE"]);helpers=runpy.run_path('tests/integration/test_sprint1_postgres.py')
dsn=os.environ["STAYLEAD_REVIEW_DATABASE_URL"];e=create_database_engine(dsn)
old['apply_migrations'](e);pack=validate_pack('fixtures/hospitality/media-pack-v1');old['import_complete_pack'](e,pack)
hotel=pack['hotel']['hotel_id'];media=next(m for m in pack['media'] if m['kind']=='image');fact=next(f for f in pack['facts'] if f['fact_id'] in media['fact_ids']);source=pack['sources'][0]
session=str(uuid.uuid4());rid='old-media-response';expiry=datetime.now(UTC)+timedelta(hours=1);question='Does the room have a balcony?'
old['create_session'](e,session,hotel,expiry);old['reserve_request'](e,session_id=session,hotel_id=hotel,request_id=rid,question=question)
descriptor={k:media[k] for k in ('media_id','kind','mime_type','byte_size','sha256','caption','alt_text','source_id','source_version','fact_ids')}
descriptor['hotel_id']=hotel
evidence=[{'fact_id':fact['fact_id'],'hotel_id':hotel,'source_id':source['source_id'],'source_version':source['version'],'section':fact['section'],'fact_version':fact['fact_version'],'imported_at':datetime.now(UTC).isoformat()}]
old['complete_request'](e,session_id=session,hotel_id=hotel,request_id=rid,question=question,answer='The room has a balcony.',evidence=evidence,response_fields={'unknowns':[],'trace':{},'media':[descriptor]})
store.apply_migrations(e)
provider=helpers['FakeProvider']();app=create_app(helpers['settings_for'](dsn),engine=e,provider=provider)
token=issue_token(secret='offline-test-signing-secret',session_id=session,hotel_id=hotel,expires_at=int(expiry.timestamp()));headers={'Authorization':'Bearer '+token}
with TestClient(app) as client:
 r=client.post(f'/v1/guest/sessions/{session}/messages',headers=headers,json={'request_id':rid,'question':question})
 md=r.json()['media'][0];params={'generation':str(md.get('source_generation','undefined')),'source_id':md['source_id'],'source_version':md['source_version'],'source_hash':md.get('source_hash','undefined'),'sha256':md['sha256']}
 fetch=client.get(f"/v1/guest/sessions/{session}/media/{md['media_id']}",headers=headers,params=params)
 print(json.dumps({'probe':'schema3-existing-pack-response-media-replay','replay_http':r.status_code,'offline_provider_calls':provider.calls,'descriptor_generation':md.get('source_generation'),'descriptor_source_hash':md.get('source_hash'),'media_http':fetch.status_code,'media_content_type':fetch.headers['content-type']}))
 print(json.dumps({'probe':'schema3-existing-pack-first-import-replay','result':store.import_complete_pack(e,pack)['status'],'current_generation':store.get_active_snapshot(e,hotel).generation}))
e.dispose()
