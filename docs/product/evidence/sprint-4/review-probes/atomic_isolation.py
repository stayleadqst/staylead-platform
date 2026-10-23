import os
import copy,json,tempfile,runpy,threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,UTC
from sqlalchemy import event,select
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import *
from staylead_platform.infrastructure.source_connectors.hospitality_pack import import_hospitality_pack
from staylead_platform.domains.hospitality.registration.pack_schema import validate_pack
from staylead_platform.infrastructure.persistence.pack_repository import PostgresMediaRepository
from staylead_platform.infrastructure.persistence.knowledge_repository import PostgresKnowledgeFactRepository
helpers=runpy.run_path('tests/integration/test_sprint4_lifecycle_postgres.py')
root,manifest=helpers['_prepare'](Path(tempfile.mkdtemp(prefix='s4-review-atomic-'))/'original','REVIEWATOM')
replacement=helpers['_selected_a'](root,manifest)
m=json.loads((replacement/'manifest.json').read_text());m['sources'][0]['version']='2'
for f in m['facts']:f['source_refs'][0]['version']='2'
for x in m['media']:x['source_version']='2'
(replacement/'manifest.json').write_text(json.dumps(m));pack=validate_pack(replacement)
e=create_database_engine(os.environ["STAYLEAD_REVIEW_DATABASE_URL"])
import_hospitality_pack(e,root,allowed_root=root.parent)
s=get_active_snapshot(e,manifest['hotel']['hotel_id']);a,b=s.sources
if a.source_id.endswith('-B'):a,b=b,a
repo=PostgresMediaRepository(e);fr=PostgresKnowledgeFactRepository(e)
facts=fr.list_guest_facts(s.hotel_id);descriptors=repo.list_eligible_media(s.hotel_id,{f.fact_id for f in facts},datetime.now(UTC))
def change(packvalue,operation='review-atomic-refresh'):
 return replace_source_snapshot(e,hotel_id=s.hotel_id,source_id=a.source_id,expected_generation=s.generation,expected_version=a.source_version,expected_source_hash=a.source_hash,operation_id=operation,pack=packvalue)
# Foreign source-owned ID and authoritative config reject before publication.
foreign=copy.deepcopy(pack);foreign['facts'][0]['fact_id']=next(f.fact_id for f in facts if f.provenance['source_id']==b.source_id)
wrongconfig=copy.deepcopy(pack);wrongconfig['hotel']['public_config']['name']='Changed'
for value,name in [(foreign,'foreign-fact-id'),(wrongconfig,'config-change')]:
 try:change(value,'review-'+name);raise AssertionError(name+' unexpectedly published')
 except ScopeError:print(json.dumps({'probe':name,'result':'rejected_without_publication'}))
# Interrupt after both source deletes but before new rows finish; assert rollback.
def interrupt(conn,cursor,statement,parameters,context,executemany):
 if statement.startswith('INSERT INTO knowledge_facts'):raise RuntimeError('review injected publication interruption')
event.listen(e,'before_cursor_execute',interrupt)
try:
 try:change(pack);raise AssertionError('interruption did not trigger')
 except RuntimeError as ex:assert 'review injected' in str(ex)
finally:event.remove(e,'before_cursor_execute',interrupt)
after=get_active_snapshot(e,s.hotel_id)
assert after==s
assert {f.fact_id for f in fr.list_guest_facts(s.hotel_id)}=={f.fact_id for f in facts}
for d in descriptors:
 assert repo.read_eligible_asset(s.hotel_id,d.media_id,datetime.now(UTC),expected_source_hash=d.source_hash,expected_media_sha256=d.sha256)
print(json.dumps({'probe':'interrupted-after-source-deletes','result':'all_original_facts_media_metadata_preserved'}))
# Concurrent same operation after rollback: second must return durable no-op.
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:change(pack),range(2)))
assert sorted(r['status'] for r in results)==['applied','noop']
print(json.dumps({'probe':'same-operation-concurrent-retry','statuses':sorted(r['status'] for r in results)}))
current=get_active_snapshot(e,s.hotel_id);a2=next(x for x in current.sources if x.source_id==a.source_id)
# Wrong hotel and obsolete descriptor read never return bytes.
for d in descriptors:
 assert repo.read_eligible_asset('HTL-WRONG',d.media_id,datetime.now(UTC),expected_source_hash=d.source_hash) is None
 assert repo.read_eligible_asset(s.hotel_id,d.media_id,datetime.now(UTC),expected_source_version=d.source_version,expected_source_hash=d.source_hash) is None
print(json.dumps({'probe':'wrong-hotel-and-obsolete-media','result':'no_bytes'}))
res=transition_source(e,hotel_id=s.hotel_id,source_id=a2.source_id,expected_generation=current.generation,expected_version=a2.source_version,expected_source_hash=a2.source_hash,operation_id='review-delete',action='delete')
assert {f.provenance['source_id'] for f in fr.list_guest_facts(s.hotel_id)}=={b.source_id}
for d in descriptors:assert repo.read_eligible_asset(s.hotel_id,d.media_id,datetime.now(UTC)) is None
retry=transition_source(e,hotel_id=s.hotel_id,source_id=a2.source_id,expected_generation=current.generation,expected_version=a2.source_version,expected_source_hash=a2.source_hash,operation_id='review-delete',action='delete')
assert retry['status']=='noop'
receipt=import_hospitality_pack(e,root,allowed_root=root.parent)
assert receipt['status']=='noop' and receipt['generation']==res['generation']
assert next(x for x in receipt['sources'] if x['source_id']==a2.source_id)['status']=='deleted'
print(json.dumps({'probe':'delete-consumer-and-original-import-replay','result':'A_unavailable_B_preserved_no_resurrection','generation':res['generation']}))
e.dispose()
