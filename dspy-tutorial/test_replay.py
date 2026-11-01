"""Offline native GEPA replay of saved provider responses, not a new live run."""
import os,sys,pathlib,json,tempfile,socket,hashlib
os.environ.clear();os.environ.update({'PATH':'/usr/bin:/bin','LITELLM_LOCAL_MODEL_COST_MAP':'true','DO_NOT_TRACK':'1','OTEL_SDK_DISABLED':'true'})
ROOT=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from unittest.mock import patch
from guard import Guard
from transport import GuardedTransport
import program
fixture=json.loads((ROOT/'saved-run/wire-replay.json').read_text());index=0;sentinel='OFFLINE_ONLY_SENTINEL_NOT_A_REAL_KEY'
def sender(request):
 global index
 expected=fixture[index]
 assert json.loads(request.body)==expected['request'],('request-shape-mismatch',index)
 assert hashlib.sha256(request.body).hexdigest()==expected['body_sha256'],('serialized-request-mismatch',index)
 index+=1
 return expected['status'],expected['body'].encode()
with tempfile.TemporaryDirectory() as tmp,patch.object(socket.socket,'connect',side_effect=AssertionError('No network')),patch.object(socket,'getaddrinfo',side_effect=AssertionError('No DNS')),patch.object(program,'GuardedTransport',side_effect=lambda g,k,r:GuardedTransport(g,k,r,sender=sender)):
 out=pathlib.Path(tmp);guard=Guard(out);program.run(ROOT,out,sentinel,guard)
 assert index==len(fixture)==29 and guard.calls==29 and guard.outputs==2624 and guard.reflections==4
 result=json.loads((out/'result.jsonl').read_text());assert result['status']=='completed' and result['accepted_candidate_count']==0 and result['baseline_heldout_correct']==result['selected_heldout_correct']==3
 for f in out.iterdir():
  if f.is_file():assert sentinel not in f.read_text()
 print(json.dumps({'kind':'offline native replay','live_provider_calls':0,'request_shapes_and_bytes_matched':index,'fresh_example_reserved_outputs':guard.outputs,'reflection_calls':guard.reflections,'baseline_heldout':'3/3','selected_heldout':'3/3','state_roundtrip':json.loads((out/'save-load.jsonl').read_text())['verified_state']}))
