"""Bounded example CLI. Enter API key privately; never write it to disk."""
import os,sys,pathlib,getpass,warnings,signal,json
ROOT=pathlib.Path(__file__).resolve().parent
def main():
 if len(sys.argv)!=2:raise ValueError('Usage: python -I run.py NEW_OUTPUT_DIRECTORY')
 output=pathlib.Path(sys.argv[1]).resolve();output.mkdir(mode=0o700,exist_ok=False)
 # Keep the example isolated from ambient provider/proxy settings.
 os.environ.clear();os.environ.update({'PATH':'/usr/bin:/bin','HOME':str(output/'home'),'LANG':'en_US.UTF-8','LITELLM_LOCAL_MODEL_COST_MAP':'true','DO_NOT_TRACK':'1','OTEL_SDK_DISABLED':'true','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','TOKENIZERS_PARALLELISM':'false','HF_HUB_OFFLINE':'1','DSPY_CACHEDIR':str(output/'cache')})
 if not all(x.isatty() for x in (sys.stdin,sys.stdout,sys.stderr)):raise RuntimeError('Run in an interactive terminal; hidden key entry is required')
 sys.path.insert(0,str(ROOT))
 from guard import Guard,Stop
 from program import run
 key=None;guard=None
 try:
  with warnings.catch_warnings():
   warnings.simplefilter('error',getpass.GetPassWarning)
   key=getpass.getpass('OpenAI API key (hidden): ')
  if not key or any(c.isspace() for c in key):raise ValueError('Empty or malformed key')
  guard=Guard(output)
  def deadline(*args):raise Stop('absolute inference deadline')
  signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,600)
  run(ROOT,output,key,guard)
  guard.write('terminal.jsonl',{'status':'completed','attempts':guard.calls,'reserved_output':guard.outputs,'usage_usd':str(guard.actual)})
  print('Completed. Read result.jsonl, selection-frozen.jsonl and evaluations.jsonl in the output directory.');return 0
 except BaseException as e:
  if guard:guard.write('terminal.jsonl',{'status':'stopped','error_type':type(e).__name__,'attempts':guard.calls,'reserved_output':guard.outputs,'no_retry':True})
  print('Stopped without retry. Check the saved diagnostic files. No key is stored.');return 1
 finally:signal.setitimer(signal.ITIMER_REAL,0);key=None
if __name__=='__main__':
 try:code=main()
 except BaseException as e:print('Could not start:',type(e).__name__);sys.exit(1)
 sys.exit(code)
