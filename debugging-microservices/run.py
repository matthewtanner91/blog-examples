#!/usr/bin/env python3
"""Synthetic, loopback-only HTTP fixture; no packages, secrets, or external calls."""
import datetime as dt, hashlib, json, os, pathlib, platform, signal, subprocess, sys, time, urllib.request, urllib.error
ROOT=pathlib.Path(__file__).resolve().parent
OUT=ROOT/('run-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
OUT.mkdir()
PROCS=[]; HANDLES=[]; PORTS=[]
ENV={'PATH':os.defpath,'PYTHONUNBUFFERED':'1','PYTHONDONTWRITEBYTECODE':'1','LANG':'C.UTF-8'}
COMMON='''import datetime as dt, hashlib, json, os, pathlib, re, sys, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
SERVICE = __SERVICE__
SHA = os.environ['SOURCE_SHA']
SOURCE_HASH = hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()
def log(event, **fields):
    print(json.dumps(dict(utc=dt.datetime.now(dt.timezone.utc).isoformat(), service=SERVICE, sha=SHA, source_hash=SOURCE_HASH, event=event, **fields)), flush=True)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
def downstream(path, rid):
    url=os.environ['UPSTREAM']+path
    request=urllib.request.Request(url,headers={'X-Request-ID':rid})
    try:
        response=OPENER.open(request, timeout=2)
    except urllib.error.HTTPError as e:
        response=e
    with response:
        body=json.loads(response.read(8192))
        status=response.status
    log('downstream_response', rid=rid, url=url, status=status, body=body)
    return status, body
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def reply(self,status,body,rid):
        payload=json.dumps(body, separators=(',',':')).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('X-Request-ID',rid)
        self.end_headers()
        self.wfile.write(payload)
        log('response',rid=rid,path=self.path,status=status,body=body)
    def do_GET(self):
        rid=self.headers.get('X-Request-ID','')
        if not re.fullmatch(r'[A-Za-z0-9-]{1,64}',rid):
            return self.reply(400,{'error':'INVALID_REQUEST_ID'},'rejected')
        log('request',rid=rid,path=self.path)
        if self.path != __ROUTE__:
            return self.reply(404,{'error':'NOT_FOUND'},rid)
__BODY__
server=HTTPServer(('127.0.0.1',0),Handler)
pathlib.Path(os.environ['READY']).write_text(str(server.server_port))
log('started',port=server.server_port)
server.serve_forever()
'''
BODIES={
'warehouse':'''        return self.reply(200,{'sku':'demo-1','available':7},rid)''',
'order':'''        try:
            status, body=downstream('/stock/demo-1',rid)
        except (urllib.error.URLError,TimeoutError,OSError):
            return self.reply(502,{'error':'WAREHOUSE_TRANSPORT'},rid)
        if status != 200:
            return self.reply(502,{'error':'WAREHOUSE_STATUS'},rid)
        if type(body.get('available')) is not int:
            return self.reply(502,{'error':'WAREHOUSE_CONTRACT: available must be integer'},rid)
        return self.reply(200,{'sku':'demo-1','can_order':body['available']>0},rid)''',
'edge':'''        try:
            status, body=downstream('/can-order/demo-1',rid)
        except (urllib.error.URLError,TimeoutError,OSError):
            return self.reply(502,{'error':'ORDER_TRANSPORT'},rid)
        return self.reply(status,body,rid)'''}
ROUTES={'warehouse':'/stock/demo-1','order':'/can-order/demo-1','edge':'/checkout/demo-1'}
def command(argv,cwd):
    result=subprocess.run(argv,cwd=cwd,env=ENV,capture_output=True,text=True,timeout=10)
    with (OUT/'commands.jsonl').open('a') as f:f.write(json.dumps({'argv':argv,'cwd':str(cwd),'rc':result.returncode,'stdout':result.stdout,'stderr':result.stderr})+'\n')
    if result.returncode: raise RuntimeError(f'Command failed: {argv}')
    return result.stdout.strip()
def commit(repo,message):
    command(['git','add','app.py'],repo)
    command(['git','-c','user.name=Fixture Author','-c','user.email=fixture@example.invalid','-c','commit.gpgsign=false','commit','-m',message],repo)
    return command(['git','rev-parse','HEAD'],repo)
def stop(p):
    if p.poll() is None:
        os.killpg(p.pid,signal.SIGTERM)
        try:p.wait(timeout=3)
        except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=3)
def launch(name,sha,phase,upstream=None):
    repo=OUT/'repos'/name
    # Materialize exact committed source outside the mutable Git worktree.
    dest=OUT/'deployments'/phase/name;dest.mkdir(parents=True)
    source=command(['git','show',sha+':app.py'],repo)+'\n'
    (dest/'app.py').write_text(source)
    ready=dest/'port';logfile=open(dest/'events.jsonl','w');HANDLES.append(logfile)
    env=ENV|{'SOURCE_SHA':sha,'READY':str(ready)}
    if upstream:env['UPSTREAM']=upstream
    p=subprocess.Popen([sys.executable,str(dest/'app.py')],env=env,stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True)
    PROCS.append(p)
    end=time.monotonic()+4
    while not ready.exists():
        if p.poll() is not None or time.monotonic()>end:raise RuntimeError('Startup failed')
        time.sleep(.02)
    port=int(ready.read_text());PORTS.append(port)
    manifest={'service':name,'sha':sha,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'port':port,'pid':p.pid,'command':[sys.executable,str(dest/'app.py')]}
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return p,'http://127.0.0.1:'+str(port)
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
RESULTS=[]
def request(url,rid,expected_status,expected_body):
    row={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'url':url,'headers':{'X-Request-ID':rid}}
    try:response=OPENER.open(urllib.request.Request(url,headers=row['headers']),timeout=3)
    except urllib.error.HTTPError as e:response=e
    with response:row.update(status=response.status,body=json.loads(response.read(8192)),response_headers=dict(response.headers))
    row['pass']=row['status']==expected_status and row['body']==expected_body
    RESULTS.append(row)
    (OUT/'requests.json').write_text(json.dumps(RESULTS,indent=2))
    if not row['pass']:raise RuntimeError('Response expectation failed')
    return row
def interrupted(signum, frame):
    raise RuntimeError('Interrupted signal '+str(signum))
signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)
signal.signal(signal.SIGALRM, interrupted)
signal.alarm(45)
status='FAIL';error=None
try:
    repos=OUT/'repos';repos.mkdir()
    shas={}
    for name in BODIES:
        repo=repos/name;repo.mkdir();command(['git','init','-b','main'],repo)
        source=COMMON.replace('__SERVICE__',repr(name)).replace('__ROUTE__',repr(ROUTES[name])).replace('__BODY__',BODIES[name])
        (repo/'app.py').write_text(source)
        shas[name]=commit(repo,'Initial synthetic '+name+' contract')
    wh=repos/'warehouse';app=wh/'app.py'
    original=app.read_text();app.write_text(original.replace("'available':7","'available':'7'"))
    shas['warehouse_bad']=commit(wh,'Change available representation to string')
    app.write_text(original);shas['warehouse_mitigated']=commit(wh,'Restore integer response contract')
    (OUT/'revisions.json').write_text(json.dumps(shas,indent=2))
    for phase,key in [('baseline','warehouse'),('failure','warehouse_bad'),('mitigation','warehouse_mitigated')]:
        wp,wu=launch('warehouse',shas[key],phase)
        op,ou=launch('order',shas['order'],phase,wu)
        ep,eu=launch('edge',shas['edge'],phase,ou)
        if phase=='failure':
            request(eu+ROUTES['edge'],'failure-1',502,{'error':'WAREHOUSE_CONTRACT: available must be integer'})
            request(wu+ROUTES['warehouse'],'direct-probe-1',200,{'sku':'demo-1','available':'7'})
            stop(wp)
            request(eu+ROUTES['edge'],'transport-control-1',502,{'error':'WAREHOUSE_TRANSPORT'})
        else:
            for n in range(3 if phase=='mitigation' else 1):request(eu+ROUTES['edge'],f'{phase}-{n+1}',200,{'sku':'demo-1','can_order':True})
        for p in (ep,op,wp):stop(p)
    order=repos/'order'
    query=['git','grep','-n','-F','WAREHOUSE_CONTRACT',shas['order'],'--','app.py']
    (OUT/'local-emitter-search.txt').write_text(command(query,order)+'\n')
    (OUT/'candidate-diff.txt').write_text(command(['git','diff',shas['warehouse'],shas['warehouse_bad'],'--','app.py'],wh)+'\n')
    (OUT/'candidate-commit-set.txt').write_text(command(['git','rev-list',shas['warehouse_bad'],'^'+shas['warehouse']],wh)+'\n')
    status='PASS_LOCAL_ONLY'
except Exception as exc:
    error=repr(exc)
finally:
    signal.alarm(0)
    for p in PROCS:stop(p)
    for f in HANDLES:f.close()
    import socket
    closed=[]
    for port in PORTS:
        with socket.socket() as s:s.settimeout(.1);closed.append({'port':port,'closed':s.connect_ex(('127.0.0.1',port))!=0})
    receipt={'status':status,'error':error,'python':sys.version,'os':platform.platform(),'executable':sys.executable,'dependency_lock':'standard library only; no third-party dependencies','container_images':'not used; direct isolated fixture processes','requests':len(RESULTS),'children_exited':all(p.poll() is not None for p in PROCS),'ports':closed,'sourcegraph':'NOT_RUN: no authorized connected fixture repositories established','paid_spend':0}
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2));print('EVIDENCE_DIR='+str(OUT))
if status!='PASS_LOCAL_ONLY':sys.exit(1)
