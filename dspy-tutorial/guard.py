"""Durable fail-closed paid-call guard. No API keys in artifacts."""
import json,time,threading,os,hashlib
from pathlib import Path
from decimal import Decimal as D
URL='https://api.openai.com/v1/responses'
class Stop(RuntimeError):pass
class Guard:
 def __init__(self,root,clock=time.monotonic):
  self.root=Path(root);self.clock=clock;self.start=clock();self.calls=0;self.outputs=0;self.reflections=0;self.estimated=D(0);self.actual=D(0);self.failed=False;self.lock=threading.Lock()
  self.path=self.root/'reservations.jsonl'
  if self.path.exists():raise Stop('No ledger resume or reset')
 def write(self,name,obj):
  with (self.root/name).open('a',encoding='utf8') as f:f.write(json.dumps(obj,ensure_ascii=False)+'\n');f.flush();os.fsync(f.fileno())
 def reserve(self,request,reflection):
  with self.lock:
   if self.failed:raise Stop('failure latched')
   try:
    if self.clock()-self.start>=600:raise Stop('absolute inference deadline')
    if request.method!='POST' or request.url!=URL:raise Stop('endpoint/method')
    body=request.body
    if type(body) is not bytes or len(body)>8192:raise Stop('serialized body cap')
    p=json.loads(body)
    if set(p)-{'model','input','instructions','stream','max_output_tokens','temperature','reasoning','store','text','service_tier'}:raise Stop('unsupported request parameter')
    if p.get('model')!='gpt-6-luna' or p.get('reasoning')!={'effort':'none'} or p.get('temperature')!=0 or p.get('store') is not False or p.get('stream',False) is not False:raise Stop('model/generation settings')
    if p.get('service_tier')!='default':raise Stop('explicit standard service required')
    n=p.get('max_output_tokens')
    if type(n) is not int or n!=(256 if reflection else 64):raise Stop('output bound')
    if not isinstance(p.get('input'),list):raise Stop('text input required')
    for item in p['input']:
     if set(item)-{'role','content'} or item.get('role') not in ('user','assistant','system','developer'):raise Stop('input structure')
     for part in item['content']:
      if set(part)!={'type','text'} or part['type']!='input_text' or not isinstance(part['text'],str):raise Stop('nontext input')
    if self.calls>=32 or self.outputs+n>4096 or (reflection and self.reflections>=4):raise Stop('aggregate cap')
    estimate=D(len(body)+1024)*D('.125')/1000000+D(n)*D('.50')/1000000
    if max(self.estimated,self.actual)+estimate>D('.10'):raise Stop('cost budget')
    event={'attempt':self.calls+1,'reflection':reflection,'reserved_output':n,'body_bytes':len(body),'body_sha256':hashlib.sha256(body).hexdigest(),'estimated_usd':str(estimate),'request':p}
    self.write('reservations.jsonl',event) # durable before transport, never refund
    self.calls+=1;self.outputs+=n;self.reflections+=int(reflection);self.estimated+=estimate
    return event
   except BaseException as e:
    self.failed=True;self.write('refusals.jsonl',{'error_type':type(e).__name__,'reason':str(e) if isinstance(e,Stop) else 'invalid request'});raise
 def receive(self,event,status,body):
  try:
   if status!=200:raise Stop('non200 provider response')
   p=json.loads(body)
   if p.get('status')!='completed' or p.get('error') or p.get('incomplete_details'):raise Stop('incomplete provider response')
   if p.get('model')!='gpt-6-luna' or p.get('service_tier')!='default':raise Stop('unknown model/tier billing')
   u=p['usage'];i=u['input_tokens'];o=u['output_tokens'];details=u['input_tokens_details'];cached=details['cached_tokens'];writes=details['cache_write_tokens']
   if type(writes) is not int or writes<0:raise Stop('unknown cache-write usage')
   ttl=details.get('cache_write_tokens_details')
   if writes:
    if not isinstance(ttl,dict) or set(ttl)!={'ttl_30m_tokens','ttl_12h_tokens'}:raise Stop('unknown write lifetime')
    if type(ttl['ttl_30m_tokens']) is not int or type(ttl['ttl_12h_tokens']) is not int or ttl['ttl_30m_tokens']!=writes or ttl['ttl_12h_tokens']!=0:raise Stop('unexpected cache-write lifetime')
   elif ttl is not None and (not isinstance(ttl,dict) or any(type(v) is not int or v!=0 for v in ttl.values()) or set(ttl)-{'ttl_30m_tokens','ttl_12h_tokens'}):raise Stop('inconsistent zero cache-write usage')
   if any(type(x) is not int or x<0 for x in (i,o,cached)) or cached+writes>i or o>event['reserved_output'] or u.get('total_tokens')!=i+o:raise Stop('unknown/inconsistent usage')
   cost=(D(i-cached-writes)*D('.10')+D(cached)*D('.01')+D(writes)*D('.125')+D(o)*D('.50'))/1000000
   self.actual+=cost;self.write('usage.jsonl',{'attempt':event['attempt'],'usage':u,'actual_usd':str(cost),'actual_total_usd':str(self.actual)})
   if i>event['body_bytes']+1024 or self.actual>D('.10'):raise Stop('usage exceeded planning reserve')
   if u.get('output_tokens_details',{}).get('reasoning_tokens')!=0:raise Stop('unknown/unexpected reasoning usage')
   texts=[]
   for item in p.get('output',[]):
    if item.get('type')!='message' or item.get('role')!='assistant':raise Stop('unexpected output item')
    for part in item.get('content',[]):
     if part.get('type')!='output_text':raise Stop('unexpected output content')
     texts.append(part['text'])
   if len(texts)!=1 or not isinstance(texts[0],str):raise Stop('unexpected output shape')
   parsed=json.loads(texts[0]) # reject invalid JSON before adapter can retry/repair it
   if event['reflection']:
    if set(parsed)!={'new_instruction'} or not isinstance(parsed['new_instruction'],str) or not parsed['new_instruction'].strip():raise Stop('invalid instruction response')
   elif set(parsed)!={'category'} or parsed['category'] not in ('billing','technical','account'):raise Stop('invalid typed lowercase label')
   return p
  except BaseException:self.failed=True;raise
