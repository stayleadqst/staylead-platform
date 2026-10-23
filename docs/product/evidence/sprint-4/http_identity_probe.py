"""Actual local HTTP replay/media checks; auth stays in a mode0600 /tmp file."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = Path(__file__).resolve().parent
PRIVATE = Path('/tmp/staylead-sprint4-http-session.json')
URL = 'http://127.0.0.1:13005/api/guest'


def request(path, body=None, token=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(URL+path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try: response = urllib.request.urlopen(req, timeout=50)
    except urllib.error.HTTPError as exc: response = exc
    data = response.read()
    if 'application/json' in response.headers.get('content-type', ''): data = json.loads(data)
    return response.status, data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=['current', 'stale'])
    phase = parser.parse_args().phase
    if phase == 'current':
        status, session = request('/sessions', {'hotel_slug': 'sprint4-garden'})
        assert status == 201
        body = {'request_id': str(uuid.uuid4()), 'question': 'Does the king room have a balcony? Show its illustration.'}
        path = f'/sessions/{session["session_id"]}/messages'
        status, answer = request(path, body, session['access_token'])
        assert status == 200, (status, answer)
        status, replay = request(path, body, session['access_token'])
        assert status == 200 and replay == answer
        assert 'evidence_bindings' not in answer and 'freshness' not in answer
        media = answer['media'][0]
        query = urllib.parse.urlencode({'generation': media['source_generation'], 'source_id': media['source_id'],
                                       'source_version': media['source_version'], 'source_hash': media['source_hash'],
                                       'sha256': media['sha256']})
        media_path = f'/sessions/{session["session_id"]}/media/{media["media_id"]}?{query}'
        ok, data = request(media_path, token=session['access_token'])
        missing, _ = request(media_path)
        wrong, _ = request(media_path.replace(session['session_id'], str(uuid.uuid4())), token=session['access_token'])
        assert ok == 200 and len(data) == media['byte_size'] and missing == 401 and wrong == 403
        PRIVATE.write_text(json.dumps({'session': session, 'body': body, 'media_path': media_path}))
        os.chmod(PRIVATE, 0o600)
        result = {'valid_replay_identical': True, 'reported_calls_in_identical_initial_and_replay_trace': answer['trace']['calls'],
                  'media_status': ok, 'media_bytes': len(data), 'missing_auth': missing, 'wrong_session': wrong}
    else:
        private = json.loads(PRIVATE.read_text())
        session, body = private['session'], private['body']
        replay, data = request(f'/sessions/{session["session_id"]}/messages', body, session['access_token'])
        freshness, decision = request(f'/sessions/{session["session_id"]}/freshness', {'request_id': body['request_id']}, session['access_token'])
        media, _ = request(private['media_path'], token=session['access_token'])
        assert replay == 409 and data['error']['code'] == 'stale_source'
        assert media == 404
        result = {'replay_status': replay, 'replay_error': data['error']['code'],
                  'old_media_status': media, 'freshness_status': freshness, 'decision': decision}
    (BASE/f'http-identity-{phase}.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__': main()
