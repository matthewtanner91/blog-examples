"""Run a small local CPU configuration check and retain its evidence."""
import hashlib, json, os, pathlib, re, signal, socket, subprocess, time, urllib.request, uuid
ROOT = pathlib.Path(__file__).resolve().parent
RUN = ROOT / 'runs' / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())+'-'+uuid.uuid4().hex[:8])
RUN.mkdir(parents=True, exist_ok=False)
(RUN/'evidence').mkdir()
for name in ('model','hf-cache'):
    (RUN/name).symlink_to(ROOT/name, target_is_directory=True)
# Node resolves dependencies from this unchanged source file's original location.
NODE = ROOT/'.runtime/node-v24.22.2-darwin-arm64/bin/node'
AIPERF = ROOT/'.venv/bin/aiperf'
ENV = dict(os.environ, HF_HUB_CACHE=str(ROOT/'hf-cache'), HF_HUB_OFFLINE='1',
           TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='2')
started=time.monotonic(); deadline=started+600
server=profile=None; status=1; cleanup={}; handles=[]
def integrity(label):
    files=[ROOT/n for n in ('server.mjs','run.py','setup.sh','verify.py','verify-tokenizer.mjs','model-manifest.json','model-SHASUMS256.txt','package-lock.json')]
    files+=sorted((ROOT/'model').rglob('*'))+sorted((ROOT/'hf-cache').rglob('*'))+sorted((ROOT/'receipts').glob('*'))
    files += [NODE, ROOT/'.runtime/node.tar.gz']
    manifest={str(f.relative_to(ROOT)):hashlib.file_digest(f.open('rb'),'sha256').hexdigest() for f in files if f.is_file()}
    (RUN/f'evidence/integrity-{label}.json').write_text(json.dumps(manifest,indent=2))
    return manifest

def gate():
    pressure=subprocess.check_output(['/usr/sbin/sysctl','-n','kern.memorystatus_vm_pressure_level'],text=True).strip()
    with (RUN/'evidence/gates.jsonl').open('a') as f: f.write(json.dumps({'monotonic':time.monotonic(),'pressure':pressure})+'\n')
    if server is not None and server.poll() is None:
        rss=int(subprocess.check_output(['/bin/ps','-o','rss=','-p',str(server.pid)],text=True).strip())*1024
        with (RUN/'evidence/rss.jsonl').open('a') as f: f.write(json.dumps({'monotonic':time.monotonic(),'rss':rss})+'\n')
        if rss>1500000000: raise RuntimeError('Server RSS exceeds limit')
    if pressure!='1': raise RuntimeError('OS pressure is not normal')
    if time.monotonic()>=deadline: raise TimeoutError('600-second phase limit')
def port_open():
    with socket.socket() as s:
        s.settimeout(1); return s.connect_ex(('127.0.0.1',18761))==0
def logfiles(label):
    pair=[(RUN/f'evidence/{label}.{ext}').open('wb') for ext in ('stdout','stderr')]
    handles.extend(pair); return dict(stdout=pair[0],stderr=pair[1])
def start(cmd,label):
    (RUN/f'evidence/{label}-command.json').write_text(json.dumps(cmd))
    return subprocess.Popen(cmd,cwd=RUN,env=ENV,start_new_session=True,**logfiles(label))
def terminate_owned(p,label):
    if p is None: return
    if p.poll() is None: p.send_signal(signal.SIGTERM)
    try: code=p.wait(timeout=20)
    except subprocess.TimeoutExpired:
        # Failure containment only; any forced termination fails acceptance.
        cleanup[label+'_forced_kill']=True
        os.killpg(p.pid,signal.SIGKILL); code=p.wait(timeout=10)
    cleanup[label+'_exit']=code
    try: os.killpg(p.pid,0); cleanup[label+'_group_absent']=False
    except ProcessLookupError: cleanup[label+'_group_absent']=True
try:
    before=integrity('before')
    gate()
    # One admission snapshot: normal pressure is mandatory; free percent alone is not proof.
    headroom=subprocess.check_output(['/usr/bin/memory_pressure','-Q'],text=True)
    (RUN/'evidence/headroom.txt').write_text(headroom)
    free=re.search(r'System-wide memory free percentage: (\d+)%',headroom)
    if not free or int(free.group(1))<25: raise RuntimeError('Headroom gate failed')
    owners=subprocess.check_output(['/bin/ps','-ww','-axo','pid,uid,comm,rss'],text=True)
    (RUN/'evidence/process-names.txt').write_text(owners)
    competing=re.compile(r'(?i)(ollama|llama[-_]?server|vllm|lmstudio|mlx[-_]?lm|tritonserver|text-generation)')
    if any(competing.search(line) for line in owners.splitlines()[1:]): raise RuntimeError('Competing runtime name; review ownership before another admission')
    # This name filter cannot identify every workload; run on an otherwise idle machine.
    if port_open(): raise RuntimeError('Port occupied; do not touch its owner')
    server=start([str(NODE),str(ROOT/'server.mjs')],'server')
    health_deadline=min(deadline,time.monotonic()+60)
    while True:
        gate()
        if server.poll() is not None: raise RuntimeError('Server exited before ready')
        try:
            with urllib.request.urlopen('http://127.0.0.1:18761/health',timeout=1) as r: health=json.load(r)
            if health.get('ready') and health.get('count')==0: break
        except (OSError,ValueError): pass
        if time.monotonic()>=health_deadline: raise TimeoutError('Health deadline')
        time.sleep(.5)
    body={'model':'HuggingFaceTB/SmolLM2-135M-Instruct','messages':[{'role':'user','content':'What is the capital of France?'}],'max_tokens':16,'stream':False}
    request=urllib.request.Request('http://127.0.0.1:18761/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=30) as r: readiness=json.load(r)
    (RUN/'evidence/readiness.json').write_text(json.dumps(readiness,indent=2))
    if readiness.get('model')!=body['model'] or readiness.get('id')!='local-1': raise RuntimeError('Readiness identity mismatch')
    if not readiness['choices'][0]['message']['content'].strip() or not 1<=readiness['usage']['completion_tokens']<=16: raise RuntimeError('Readiness output invalid')
    gate()
    args='--model HuggingFaceTB/SmolLM2-135M-Instruct --url http://127.0.0.1:18761 --endpoint-type chat --streaming --tokenizer HuggingFaceTB/SmolLM2-135M-Instruct --tokenizer-revision 12fd25f77366fa6b3b4b768ec3050bf629380bac --synthetic-input-tokens-mean 128 --synthetic-input-tokens-stddev 0 --output-tokens-mean 32 --output-tokens-stddev 0 --concurrency 1 --request-count 4 --request-timeout-seconds 30 --random-seed 17 --workers-max 1 --record-processor-service-count 1 --no-gpu-telemetry --wait-for-model-timeout 0 --use-server-token-count --artifact-dir evidence/profile-measured --no-auto-plot'.split()
    profile=start([str(AIPERF),'profile',*args],'profile')
    while profile.poll() is None: gate(); time.sleep(.5)
    if profile.returncode: raise RuntimeError('AIPerf failed')
    status=0
except BaseException as error:
    (RUN/'evidence/failure.txt').write_text(repr(error))
finally:
    for process,label in ((profile,'profile'),(server,'server')):
        try: terminate_owned(process,label)
        except BaseException as error: cleanup[label+'_cleanup_error']=repr(error); status=1
    try: cleanup['endpoint_closed']=not port_open()
    except BaseException as error: cleanup['endpoint_closed']=False; cleanup['port_check_error']=repr(error); status=1
    cleanup['elapsed_seconds']=time.monotonic()-started
    for f in handles: f.close()
    if server is not None:
        if cleanup.get('server_exit')!=0 or (RUN/'evidence/server.stderr').stat().st_size: status=1
    if any(k.endswith('forced_kill') for k in cleanup) or not cleanup['endpoint_closed']: status=1
    try:
        after=integrity('after')
        cleanup['integrity_unchanged']=('before' in locals() and before==after)
    except BaseException as error: cleanup['integrity_error']=repr(error); cleanup['integrity_unchanged']=False
    if not cleanup['integrity_unchanged']: status=1
    if profile is not None and not cleanup.get('profile_group_absent'): status=1
    if server is not None and not cleanup.get('server_group_absent'): status=1
    cleanup['runner_status']=status
    (RUN/'evidence/cleanup.json').write_text(json.dumps(cleanup,indent=2))
print(RUN)
raise SystemExit(status)
