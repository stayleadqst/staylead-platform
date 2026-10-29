import threading,time,uuid,json
from pathlib import Path
from datetime import UTC,datetime,timedelta
from sqlalchemy import select,update,event
from fastapi.testclient import TestClient
from pydantic import SecretStr
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence import store
from staylead_platform.entrypoints.app import create_app
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.platform.guest_context.sessions.signing import issue_token
out=Path('/Users/ccvn/Documents/project/Staylead/validation/sprint-12-20261029');dsn='postgresql+psycopg://ccvn@127.0.0.1:55442/staylead_s12_q';e=create_database_engine(dsn);hid='HTL-CITY01';sid=str(uuid.uuid4());store.create_session(e,sid,hid,datetime.now(UTC)+timedelta(hours=1));h=store.get_hotel(e,hid)
r=store.save_room_advice_result(e,session_id=sid,hotel_id=hid,request_id=str(uuid.uuid4()),payload={'options':[{'option_id':'synthetic-option'}]},brief_version=0,source_generation=h['knowledge_generation'],config_version=h['config_version'],source_refs=[],expected_state_version=0)
settings=Settings(_env_file=None,environment='test',database_url=dsn,ai_provider='disabled',session_signing_secret=SecretStr('q-s12-synthetic-secret'));app=create_app(settings,engine=e)
# The original bearer remains unexpired, so this tests the database expiry gate.
token=issue_token(secret='q-s12-synthetic-secret',session_id=sid,hotel_id=hid,expires_at=int((datetime.now(UTC)+timedelta(hours=1)).timestamp()))
locked=threading.Event();responses=[]
def mark(conn,cursor,sql,params,ctx,many):
 if sql.lstrip().startswith('SELECT guest_sessions.session_id') and 'FOR UPDATE' in sql:locked.set()
event.listen(e,'after_cursor_execute',mark)
# Lock the hotel after initial result creation. Selection locks the parent first,
# then waits for the hotel. Advance the real clock across the controlled expiry.
block=e.connect();tx=block.begin();block.execute(select(store.hotels).where(store.hotels.c.hotel_id==hid).with_for_update())
expiry=datetime.now(UTC)+timedelta(seconds=.6)
with e.begin() as c:c.execute(update(store.sessions).where(store.sessions.c.session_id==sid).values(expires_at=expiry))
client=TestClient(app)
def choose():
 responses.append(client.post(f"/v1/guest/sessions/{sid}/room-advice/{r['result_id']}/selection",headers={'Authorization':f'Bearer {token}'},json={'result_version':r['result_version'],'option_id':'synthetic-option'}))
w=threading.Thread(target=choose,daemon=True);w.start();assert locked.wait(3);time.sleep(.9);tx.commit();block.close();w.join(5);event.remove(e,'after_cursor_execute',mark);assert not w.is_alive()
with e.connect() as c:
 sel=c.execute(select(store.room_advice_selections).where(store.room_advice_selections.c.session_id==sid)).mappings().first()
result={'http_status':responses[0].status_code,'http_body':responses[0].json(),'controlled_expiry':expiry.isoformat(),'completion_time':datetime.now(UTC).isoformat(),'selection_persisted':bool(sel),'selection_timestamp':str(sel['updated_at']) if sel else None,'request_finished':True}
(out/'q-selection-expiry-probe.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));client.close();store.delete_guest_session(e,session_id=sid,hotel_id=hid);e.dispose()
