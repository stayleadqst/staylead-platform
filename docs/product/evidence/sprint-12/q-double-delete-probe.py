import json,threading,uuid
from pathlib import Path
from datetime import UTC,datetime,timedelta
from sqlalchemy import select,func,event,delete
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence import store
from staylead_platform.platform.contracts.admission import GuestAdmissionLimits
engine=create_database_engine('postgresql+psycopg://ccvn@127.0.0.1:55442/staylead_s12_q')
hid='QDOUBLE-'+uuid.uuid4().hex[:12];sid=str(uuid.uuid4());rid=str(uuid.uuid4())
store.create_session(engine,sid,hid,datetime.now(UTC)+timedelta(hours=1))
store.reserve_request(engine,session_id=sid,hotel_id=hid,request_id=rid,question='synthetic',limits=GuestAdmissionLimits(),lease_owner=str(uuid.uuid4()),lease_until=datetime.now(UTC)+timedelta(seconds=40))
# This barrier only schedules both cleanup transactions after their SELECT has
# obtained the same existing reservation; it does not modify any candidate function.
barrier=threading.Barrier(2); seen=[]
def after(conn,cursor,statement,params,context,many):
 if statement.startswith('SELECT guest_requests.created_at, guest_requests.lease_owner'):
  seen.append(threading.get_ident());barrier.wait(timeout=5)
event.listen(engine,'after_cursor_execute',after)
results=[]
def remove():
 try:results.append({'deleted':store.delete_guest_session(engine,session_id=sid,hotel_id=hid)})
 except Exception as exc:results.append({'error':type(exc).__name__+':'+str(exc)})
workers=[threading.Thread(target=remove) for _ in range(2)]
for w in workers:w.start()
for w in workers:w.join(10)
event.remove(engine,'after_cursor_execute',after)
with engine.connect() as conn:
 n=conn.scalar(select(func.count()).select_from(store.requests).where(store.requests.c.hotel_id==hid))
 s=conn.scalar(select(func.count()).select_from(store.sessions).where(store.sessions.c.session_id==sid))
observed={'same_original_reservations':1,'concurrent_deletes':results,'synchronized_recent_reads':len(seen),'retained_quota_rows':n,'remaining_sessions':s,'workers_alive':sum(w.is_alive() for w in workers)}
Path('/Users/ccvn/Documents/project/Staylead/validation/sprint-12-20261029/q-double-delete-probe.json').write_text(json.dumps(observed,indent=2)+'\n');print(json.dumps(observed,indent=2))
with engine.begin() as conn:
 conn.execute(delete(store.requests).where(store.requests.c.hotel_id==hid));conn.execute(delete(store.sessions).where(store.sessions.c.hotel_id==hid))
engine.dispose()
