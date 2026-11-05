import asyncio,json,threading,uuid,hashlib,os
from pathlib import Path
from datetime import UTC,datetime,timedelta
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select,func
from staylead_platform.composition.configuration.settings import Settings
from staylead_platform.entrypoints.app import create_app
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence import store
from staylead_platform.infrastructure.source_connectors.knowledge_v1 import import_fixture_pack
from test_b10_trace_postgres import OfflineB10Provider
from staylead_platform.platform.contracts.ai_provider import GenerationResult
repo=Path('/Users/ccvn/Documents/project/Staylead/github/staylead-platform')
out=Path('/Users/ccvn/Documents/project/Staylead/validation/sprint-12-20261029')
manifest=json.loads((repo/'docs/product/evidence/sprint-12/candidate-v1.json').read_text())
def pins():
 return {p:hashlib.sha256((repo/p).read_bytes()).hexdigest() for p in manifest['files']}
before=pins(); assert before==manifest['files']
engine=create_database_engine('postgresql+psycopg://ccvn@127.0.0.1:55442/staylead_s12_q')
store.apply_migrations(engine)
import_fixture_pack(engine,repo/'fixtures/hospitality/knowledge-v1')
class PausingLanguageProvider(OfflineB10Provider):
 def __init__(self):
  super().__init__();self.started=threading.Event();self.release=threading.Event()
 async def generate(self,request):
  self.started.set()
  await asyncio.to_thread(self.release.wait,10)
  result=await super().generate(request)
  payload=json.loads(result.text);payload['explicit_language_tag']='fr';payload['inferred_language_tag']=None
  return GenerationResult(text=json.dumps(payload),provider=result.provider,deployment=result.deployment,model=result.model,request_id=result.request_id,usage=result.usage)
provider=PausingLanguageProvider()
settings=Settings(_env_file=None,environment='test',database_url='postgresql+psycopg://ccvn@127.0.0.1:55442/staylead_s12_q',ai_provider='disabled',session_signing_secret=SecretStr('q-s12-synthetic-secret'))
observed={}
try:
 with TestClient(create_app(settings,engine=engine,provider=provider)) as client:
  opened=client.post('/v1/guest/sessions',json={'hotel_slug':'harbor-city-demo'});assert opened.status_code==201,opened.text
  session=opened.json();sid=session['session_id'];headers={'Authorization':f"Bearer {session['access_token']}"};results=[]
  def post():
   results.append(client.post(f'/v1/guest/sessions/{sid}/messages',headers=headers,json={'request_id':str(uuid.uuid4()),'question':'Please answer in French. What are the breakfast hours?'}))
  worker=threading.Thread(target=post,daemon=True);worker.start();assert provider.started.wait(5)
  deleted=client.delete(f'/v1/guest/sessions/{sid}',headers=headers);assert deleted.status_code==204,deleted.text
  with engine.connect() as conn:
   observed['rows_at_delete_completion']={t.name:conn.scalar(select(func.count()).select_from(t).where(t.c.session_id==sid)) for t in (store.sessions,store.guest_language_preferences,store.requests)}
  provider.release.set();worker.join(15);assert not worker.is_alive()
  observed.update({'delete_status':deleted.status_code,'late_http_status':results[0].status_code,'provider_calls':provider.calls})
  with engine.connect() as conn:
   observed['rows_after_late_completion']={t.name:conn.scalar(select(func.count()).select_from(t).where(t.c.session_id==sid)) for t in (store.sessions,store.guest_language_preferences,store.requests,store.messages,store.guest_briefs)}
   row=conn.execute(select(store.guest_language_preferences).where(store.guest_language_preferences.c.session_id==sid)).mappings().first()
   observed['late_language_row']=dict(row) if row else None
  observed['later_purge_count']=store.purge_expired_sessions(engine,now=datetime.now(UTC)+timedelta(days=8))
  with engine.connect() as conn:
   observed['language_rows_after_8day_cleanup']=conn.scalar(select(func.count()).select_from(store.guest_language_preferences).where(store.guest_language_preferences.c.session_id==sid))
finally:
 provider.release.set();engine.dispose()
observed['pins_before_match']=before==manifest['files'];observed['pins_after_match']=pins()==manifest['files']
(out/'q-retention-probe.json').write_text(json.dumps(observed,indent=2,default=str)+'\n')
print(json.dumps(observed,indent=2,default=str))
