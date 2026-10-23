"""Explicit isolated acceptance commands; no LLM or credential output."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import os
import subprocess
import sys

from staylead_platform.infrastructure.database import create_database_engine
from staylead_platform.infrastructure.persistence.store import (
    apply_migrations, get_active_snapshot, replace_source_snapshot, transition_source,
)
from staylead_platform.infrastructure.source_connectors.hospitality_pack import import_hospitality_pack
from staylead_platform.domains.hospitality.registration.pack_schema import validate_pack

BASE = Path(__file__).resolve().parent
HOTEL = 'HTL-S4-ACCEPTANCE'
SOURCE = 'source-hotel-guide'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['init', 'snapshot', 'refresh', 'revoke', 'replay', 'restore'])
    action = p.parse_args().action
    cfg = json.loads(Path('/tmp/staylead-sprint4-runtime.json').read_text())
    engine = create_database_engine(cfg['database_url'])
    if action == 'init':
        schema = apply_migrations(engine)
        outcome = import_hospitality_pack(engine, BASE/'packs/v1', allowed_root=BASE/'packs')
        result = {'schema': schema, 'outcome': outcome}
    elif action == 'replay':
        result = import_hospitality_pack(engine, BASE/'packs/v1', allowed_root=BASE/'packs')
    else:
        snapshot = get_active_snapshot(engine, HOTEL)
        source = next(s for s in snapshot.sources if s.source_id == SOURCE)
        if action == 'snapshot':
            result = asdict(snapshot)
        elif action in {'refresh', 'restore'}:
            version = str(int(source.source_version) + 1)
            root = BASE/('packs/source-A-v' + version)
            shutil.copytree(BASE/'packs/v1', root, dirs_exist_ok=True)
            manifest = json.loads((root/'manifest.json').read_text())
            # Preserve immutable hotel public config, including original pack ID.
            manifest['pack_version'] = version
            manifest['sources'] = [s for s in manifest['sources'] if s['source_id'] == SOURCE]
            manifest['sources'][0]['version'] = version
            manifest['facts'] = [f for f in manifest['facts']
                                 if f['source_refs'][0]['source_id'] == SOURCE
                                 and (action == 'restore' or f['fact_id'] != 'fact-pool-clip-window')]
            for fact in manifest['facts']:
                fact['source_refs'][0]['version'] = version
                fact['fact_version'] = version
                if action == 'refresh' and fact['fact_id'] == 'fact-breakfast-hours': fact['value'] = '08:00-11:00'
            manifest['media'] = [m for m in manifest['media'] if action == 'restore' or m['media_id'] == 'media-room']
            for media in manifest['media']:
                media['source_version'] = version
                media['caption'] += ' Refreshed approved source revision ' + version + '.'
            for asset in (root/'assets').iterdir():
                if str(asset.relative_to(root)) not in {m['asset_path'] for m in manifest['media']}: asset.unlink()
            (root/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
            command = [sys.executable, '-m', 'staylead_platform.infrastructure.source_connectors.lifecycle',
                       'refresh', '--hotel-id', HOTEL, '--source-id', SOURCE,
                       '--expected-generation', str(snapshot.generation), '--expected-version', source.source_version,
                       '--expected-source-hash', source.source_hash, '--operation-id', 's4-acceptance-' + action + '-' + version,
                       '--pack-root', str(root), '--allowed-root', str(BASE/'packs')]
            completed = subprocess.run(command, env=dict(os.environ, STAYLEAD_DATABASE_URL=cfg['database_url']),
                                       capture_output=True, text=True, check=True)
            result = json.loads(completed.stdout)
            result['operator_surface'] = 'trusted-local-cli'

        else:
            result = transition_source(
                engine, hotel_id=HOTEL, source_id=SOURCE,
                expected_generation=snapshot.generation, expected_version=source.source_version,
                expected_source_hash=source.source_hash, operation_id='s4-acceptance-revoke-' + source.source_version,
                action='revoke',
            )
    output = {'action': action, 'result': result}
    (BASE/f'lifecycle-{action}-{result.get("generation", result.get("hotel_generation", "observation"))}.json').write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    print(json.dumps(output, ensure_ascii=False, default=str))
    engine.dispose()


if __name__ == '__main__': main()
