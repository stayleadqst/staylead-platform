"""Local Sprint 4 acceptance only; fake by default, explicit opt-in live adapter."""
from __future__ import annotations
import argparse, asyncio, hashlib, http.client, json, os, secrets, subprocess, threading, time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
BASE = Path(__file__).resolve().parent
CONTROL = BASE / 'runtime-control.json'
EVENTS = BASE / 'runtime-events.jsonl'
LOCK = threading.Lock()
RUNTIME = Path('/tmp/staylead-sprint4-runtime.json')

def event(item):
    with LOCK:
        with EVENTS.open('a') as f: f.write(json.dumps({'unix_time':time.time(),**item}, ensure_ascii=False) + '\n')

def control():
    return json.loads(CONTROL.read_text()) if CONTROL.exists() else {}

class Gateway(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self): self.forward()
    def do_POST(self): self.forward()
    def forward(self):
        cfg=control(); body=self.rfile.read(int(self.headers.get('content-length',0))) or None
        port=18096 if cfg.get('live') else 18095
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=55)
        headers={'content-type':self.headers.get('content-type','application/json')}
        if self.headers.get('authorization'): headers['authorization']=self.headers['authorization']
        try:
            conn.request(self.command,self.path,body,headers); r=conn.getresponse(); raw=r.read()
            item={'stage':'http','method':self.command,'path':self.path,'status':r.status,'provider_mode':'live' if cfg.get('live') else 'fake'}
            if self.path.endswith('/messages'):
                item['question']=json.loads(body)['question']; item['response']=json.loads(raw)
            if '/media/' in self.path:
                item.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),mime=r.getheader('content-type'),cache_control=r.getheader('cache-control'))
                if cfg.get('media_delay'): time.sleep(float(cfg['media_delay']))
            if '/media/' in self.path and cfg.get('override_media_size'):
                raw=b'x'*int(cfg['override_media_size'])
            event(item)
            self.send_response(r.status)
            for k,v in r.getheaders():
                if k.lower() in ('content-type','cache-control','x-content-type-options'):
                    self.send_header(k,cfg.get('override_media_mime',v) if k.lower()=='content-type' and '/media/' in self.path else v)
            if not cfg.get('omit_media_length') or '/media/' not in self.path:self.send_header('content-length',str(len(raw)))
            self.end_headers(); self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError): event({'stage':'client_cancelled','path':self.path})
        finally: conn.close()

BLOB_PROBE = b'''<script>(()=>{const emit=x=>navigator.sendBeacon('/__s4_probe',JSON.stringify(x));const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);URL.createObjectURL=x=>{const u=create(x);emit({event:'blob_create',url:u,size:x.size,type:x.type});return u};URL.revokeObjectURL=u=>{emit({event:'blob_revoke',url:u});revoke(u)};})();</script>'''
class WebProbe(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def do_GET(self): self.forward()
    def do_POST(self):
        if self.path=='/__s4_probe':
            item=json.loads(self.rfile.read(int(self.headers.get('content-length',0)))); event({'stage':'browser_blob',**item}); self.send_response(204); self.end_headers()
        else: self.forward()
    def forward(self):
        c=http.client.HTTPConnection('127.0.0.1',13005,timeout=60)
        body=self.rfile.read(int(self.headers.get('content-length',0))) or None
        headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','accept-encoding','connection','content-length')}
        try:
            c.request(self.command,self.path,body,headers);r=c.getresponse();raw=r.read()
            if 'text/html' in (r.getheader('content-type') or ''): raw=raw.replace(b'<head>',b'<head>'+BLOB_PROBE,1)
            self.send_response(r.status)
            for k,v in r.getheaders():
                if k.lower() not in ('content-length','transfer-encoding','connection','content-encoding'):self.send_header(k,v)
            self.send_header('content-length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
        finally:c.close()

def serve_api(live):
    import uvicorn
    from pydantic import SecretStr
    from staylead_platform.composition.configuration.settings import Settings
    from staylead_platform.entrypoints.app import create_app
    from staylead_platform.infrastructure.ai_provider import FoundryGrokConfig,FoundryGrokProvider
    from staylead_platform.platform.contracts.ai_provider import GenerationResult,Usage
    cfg=json.loads(RUNTIME.read_text())
    settings=Settings(_env_file=None,database_url=cfg['database_url'],session_signing_secret=SecretStr(cfg['session_signing_secret']),ai_provider='disabled')
    class Fake:
        calls=0
        async def generate(self,request):
            self.calls+=1; data=json.loads(request.input_text)
            q=data.get('question','').lower()
            if 'Select only fact IDs' in request.instructions:
                out={'fact_ids':[x['fact_id'] for x in data['candidate_index']][:20]}
            else:
                facts=data['facts']
                if 'step' in q or 'accessib' in q: facts=[]
                elif 'pool' in q or 'clip' in q: facts=[f for f in facts if 'pool' in f['fact_id']]
                elif 'balcony' in q or 'photo' in q or 'room' in q: facts=[f for f in facts if 'room' in f['fact_id']]
                else: facts=[f for f in facts if 'breakfast' in f['fact_id']]
                claims=[{'text':str(f.get('value')) if not isinstance(f.get('value'),bool) else 'The room has a balcony.','fact_ids':[f['fact_id']]} for f in facts if f.get('status')=='confirmed']
                out={'supported_claims':claims,'unknowns':[] if claims else ['Current approved information is unavailable; this detail cannot be confirmed.'],'conflicts':[]}
            return GenerationResult(text=json.dumps(out,ensure_ascii=False),provider='fake',deployment='acceptance',model='offline-fake',request_id='fake-'+str(self.calls),usage=Usage())
    provider=Fake()
    if live:
        if os.environ.get('STAYLEAD_LIVE_EVAL')!='1':raise SystemExit('Live mode requires STAYLEAD_LIVE_EVAL=1')
        p=subprocess.run(['az','cognitiveservices','account','keys','list','--resource-group','Ken-Dev','--name','KEN-OpenAI-USEast2','--subscription','222aa766-dff0-4c9e-811f-90ce9b5c44f4','-o','json'],capture_output=True,text=True)
        if p.returncode:raise SystemExit('Existing development credential retrieval unavailable')
        provider=FoundryGrokProvider(FoundryGrokConfig(base_url='https://ken-openai-useast2.services.ai.azure.com/openai/v1/',api_key=SecretStr(json.loads(p.stdout)['key1']),deployment='cc-dev-grok-4-1-fast-reasoning'))
        generate=provider.generate
        live_calls=0
        async def observed(request):
            nonlocal live_calls
            live_calls+=1
            if live_calls>int(os.environ.get('STAYLEAD_ACCEPTANCE_MAX_CALLS','6')): raise RuntimeError('Sprint4 bounded provider call limit reached')
            try:r=await generate(request)
            except Exception as exc:
                event({'stage':'live_provider_failure','class':type(exc).__name__,'usage':'unknown'});raise
            event({'stage':'live_provider','model':r.model,'provider_request_id':r.request_id,'usage':asdict(r.usage),'output_json':r.text,'instructions_sha256':hashlib.sha256(request.instructions.encode()).hexdigest(),'input_sha256':hashlib.sha256(request.input_text.encode()).hexdigest()})
            return r
        provider.generate=observed
    app=create_app(settings,provider=provider)
    if live:
        from fastapi.responses import JSONResponse
        guest_turns=0
        @app.middleware('http')
        async def bounded_turns(request, call_next):
            nonlocal guest_turns
            if request.method=='POST' and request.url.path.endswith('/messages'):
                guest_turns+=1
                if guest_turns>int(os.environ.get('STAYLEAD_ACCEPTANCE_MAX_TURNS','3')):return JSONResponse(status_code=429,content={'error':{'code':'acceptance_limit','message':'Bounded Sprint4 acceptance complete.','retryable':False}})
            return await call_next(request)
    uvicorn.run(app,host='127.0.0.1',port=18096 if live else 18095,access_log=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['init','fake','live','gateway','webprobe']);a=p.parse_args()
    if a.mode=='init':
        data={'database_url':'<REDACTED_LOCAL_DATABASE_URL>','session_signing_secret':secrets.token_urlsafe(48)}
        RUNTIME.write_text(json.dumps(data));RUNTIME.chmod(0o600);print('Private acceptance runtime initialized.')
    elif a.mode=='gateway':ThreadingHTTPServer(('127.0.0.1',18097),Gateway).serve_forever()
    elif a.mode=='webprobe':ThreadingHTTPServer(('127.0.0.1',13006),WebProbe).serve_forever()
    else:serve_api(a.mode=='live')
