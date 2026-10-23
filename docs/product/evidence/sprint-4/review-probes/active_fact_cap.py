import os
import copy,json,tempfile,shutil,hashlib
from pathlib import Path
from datetime import datetime,UTC
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,event
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import *
from staylead_platform.infrastructure.source_connectors.hospitality_pack import import_hospitality_pack,refresh_hospitality_source
from staylead_platform.domains.hospitality.registration.pack_schema import validate_pack
from staylead_platform.infrastructure.persistence.knowledge_repository import PostgresKnowledgeFactRepository
from staylead_platform.infrastructure.persistence.pack_repository import PostgresMediaRepository
from staylead_platform.platform.contracts.knowledge import EvidenceBinding
engine=create_database_engine(os.environ["STAYLEAD_REVIEW_DATABASE_URL"])
apply_migrations(engine)
base=Path(tempfile.mkdtemp(prefix='s4-review-'))
fixture=Path('fixtures/hospitality/media-pack-v1')
m=json.loads((fixture/'manifest.json').read_text())
m['hotel']['hotel_id']='HTL-REVIEW-CAP';m['hotel']['slug']='review-cap';m['media']=[]
for s in m['sources']:s['source_id']='source-review-A'
template=copy.deepcopy(m['facts'][0]);template['source_refs'][0]['source_id']='source-review-A';template['fact_id']='fact-review-A'
b=copy.deepcopy(m['sources'][0]);b['source_id']='source-review-B';m['sources'].append(b)
m['facts']=[template]
for i in range(396):
 f=copy.deepcopy(template);f['fact_id']=f'fact-review-B-{i}';f['source_refs'][0]['source_id']='source-review-B';m['facts'].append(f)
original=base/'original';original.mkdir();(original/'manifest.json').write_text(json.dumps(m))
import_hospitality_pack(engine,original,allowed_root=base)
snap=get_active_snapshot(engine,m['hotel']['hotel_id']);a,b=snap.sources
transition_source(engine,hotel_id=snap.hotel_id,source_id=b.source_id,expected_generation=snap.generation,expected_version=b.source_version,expected_source_hash=b.source_hash,operation_id='cap-revoke-B',action='revoke')
replacement=copy.deepcopy(m);replacement['sources']=[copy.deepcopy(m['sources'][0])];replacement['sources'][0]['version']='2';replacement['facts']=[]
for i in range(400):
 f=copy.deepcopy(template);f['fact_id']=f'fact-review-A-{i}';f['source_refs'][0]['version']='2';replacement['facts'].append(f)
p=base/'replacement';p.mkdir();(p/'manifest.json').write_text(json.dumps(replacement))
snap=get_active_snapshot(engine,snap.hotel_id);a=next(r for r in snap.sources if r.source_id=='source-review-A')
try:
 result=refresh_hospitality_source(engine,p,allowed_root=base,hotel_id=snap.hotel_id,source_id=a.source_id,expected_generation=snap.generation,expected_version=a.source_version,expected_source_hash=a.source_hash,operation_id='cap-refresh-A')
 print(json.dumps({'probe':'active-fact-cap-after-revoke','observed':result}))
except Exception as exc:
 print(json.dumps({'probe':'active-fact-cap-after-revoke','observed_exception':type(exc).__name__,'message':str(exc),'eligible_before':len(PostgresKnowledgeFactRepository(engine).list_guest_facts(snap.hotel_id)),'replacement_active_facts':400,'unchanged_source_status':'revoked','replacement_root':str(p)}))
engine.dispose()
