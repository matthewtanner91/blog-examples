"""Public native transport hook with explicit sole HTTP destination."""
import json,time
from guard import URL,Stop
from diagnostics import classification
class BufferedResponse:
 def __init__(self,body):self.body=body;self.status=200;self.reason='OK';self.headers=[('content-type','application/json')];self.http_version='HTTP/1.1'
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def __iter__(self):yield self.body
 def read(self):return self.body
 def header(self,name):return 'application/json' if name.lower()=='content-type' else None
 def headers_all(self,name):return [self.header(name)] if self.header(name) else []
 def close(self):pass
class GuardedTransport:
 def __init__(self,guard,key,reflection=False,sender=None):
  self.guard=guard;self.key=key;self.reflection=reflection;self.sender=sender;self.client=None
 def stream(self,request):
  event=self.guard.reserve(request,self.reflection)
  try:
   if self.sender:status,body=self.sender(request) # offline-only injected sender
   else:
    import httpx
    if self.client is None:self.client=httpx.Client(trust_env=False,follow_redirects=False,transport=httpx.HTTPTransport(retries=0,trust_env=False),limits=httpx.Limits(max_connections=1,max_keepalive_connections=0))
    remaining=600-(self.guard.clock()-self.guard.start)
    if remaining<=0:raise Stop('deadline before send')
    with self.client.stream('POST',URL,content=request.body,headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'},timeout=min(30,remaining)) as r:
     status=r.status_code;chunks=[];n=0
     for chunk in r.iter_bytes():
      n+=len(chunk)
      if n>65536 or self.guard.clock()-self.guard.start>=600:raise Stop('response size/deadline')
      chunks.append(chunk)
     body=b''.join(chunks)
   # Never persist a response that unexpectedly echoes the secret.
   if self.key and self.key.encode() in body:raise Stop('response contained credential; not saved')
   self.guard.write('responses.jsonl',{'attempt':event['attempt'],'http_status':status,'raw_body':body.decode('utf8')})
   if status!=200:
    self.guard.last_safe_code=classification(status,body)
    self.guard.write('diagnostics.jsonl',{'attempt':event['attempt'],'code':self.guard.last_safe_code,'http_status':status})
   self.guard.receive(event,status,body)
   return BufferedResponse(body)
  except BaseException as e:
   self.guard.failed=True;self.guard.write('failures.jsonl',{'attempt':event['attempt'],'error_type':type(e).__name__,'reason':str(e) if isinstance(e,Stop) else 'transport error redacted'});raise Stop('Transport/protocol failure; details redacted') from None
 def close(self):
  if self.client:self.client.close()
  self.key=None
