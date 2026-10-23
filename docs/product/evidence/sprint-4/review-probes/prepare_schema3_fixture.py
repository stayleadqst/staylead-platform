import os
import runpy,json,uuid
from pathlib import Path
from datetime import datetime,UTC,timedelta
from fastapi.testclient import TestClient
from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.domains.hospitality.registration.fixture_pack import parse_fixture_pack
from staylead_platform.infrastructure.persistence import store
from staylead_platform.entrypoints.app import create_app
baseline=runpy.run_path(os.environ["STAYLEAD_SCHEMA3_STORE_FILE"])
testhelpers=runpy.run_path('tests/integration/test_sprint1_postgres.py')
dsn=os.environ["STAYLEAD_REVIEW_DATABASE_URL"];e=create_database_engine(dsn)
baseline['apply_migrations'](e)
for item in parse_fixture_pack(Path('fixtures/hospitality/knowledge-v1')):
 rows=[]
 for f in item.facts:
  r=f['source_refs'][0];rows.append({'fact_id':f['fact_id'],'hotel_id':item.hotel_id,'source_id':r['source_id'],'source_version':r['version'],'section':r['section'],'fact_version':f['version'],'status':f['status'],'valid_from':f['valid_from'],'valid_to':f['valid_to'],'fact':f,'imported_at':datetime.now(UTC)})
 baseline['save_bootstrap'](e,hotel_id=item.hotel_id,slug=item.slug,config_version=item.config_version,public_config=item.public_config,synthetic=item.synthetic,facts=rows)
