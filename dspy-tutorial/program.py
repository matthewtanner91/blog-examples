"""Actual native DSPy GEPA plan; no execution at import."""
import json,pathlib,hashlib
from typing import Literal
import dspy
from dspy.lm15 import RouterConfig
from dspy.clients.engines import LM15Engine
from dspy.teleprompt.gepa.instruction_proposal import InstructionProposer
from guard import Stop
from transport import GuardedTransport
class TicketLabel(dspy.Signature):
 '''Classify a support ticket as billing, technical, or account.'''
 ticket:str=dspy.InputField()
 category:Literal['billing','technical','account']=dspy.OutputField()
class Classifier(dspy.Module):
 def __init__(self):super().__init__();self.predict=dspy.Predict(TicketLabel)
 def forward(self,ticket):return self.predict(ticket=ticket)
def state_save(program,path):
 # Predict.dump_state serializes self.lm if attached. Detach explicitly;
 # never call custom-engine dump_state, pickle or save_program=True.
 bindings=[(pred,pred.lm) for pred in program.predictors()]
 try:
  for pred,lm in bindings:pred.lm=None
  program.save(path,save_program=False)
 finally:
  for pred,lm in bindings:pred.lm=lm
 raw=json.loads(pathlib.Path(path).read_text())
 if any(v.get('lm') is not None for v in raw.values() if isinstance(v,dict) and 'lm' in v):raise Stop('saved LM was not detached')
 return raw

def run(root,output,key,guard):
 raw=(root/'dataset.json').read_bytes();data=json.loads(raw)
 allrows=sum((data[k] for k in ('train','validation','test')),[])
 if [len(data[k]) for k in ('train','validation','test')]!=[6,3,3] or len({x['id'] for x in allrows})!=12 or len({x['ticket'] for x in allrows})!=12:raise Stop('split integrity')
 guard.write('frozen.jsonl',{'dataset_sha256':hashlib.sha256(raw).hexdigest(),'split_ids':{k:[x['id'] for x in data[k]] for k in ('train','validation','test')}})
 transports=[];engines=[]
 def lm(reflection):
  t=GuardedTransport(guard,key,reflection);transports.append(t)
  engine=LM15Engine(RouterConfig(env={},api_keys={'openai':'SESSION-TRANSPORT-INJECTS-KEY'},transport=t),model_type='responses');engines.append(engine)
  return dspy.LM('openai/gpt-6-luna',engine=engine,model_type='responses',temperature=0,max_tokens=256 if reflection else 64,reasoning_effort='none',store=False,service_tier='default',cache=False,num_retries=0)
 task=lm(False);reflection=lm(True);baseline=Classifier();baseline.set_lm(task)
 dspy.configure_cache(enable_disk_cache=False,enable_memory_cache=False)
 metric_calls=[]
 def metric(gold,pred,trace=None,pred_name=None,pred_trace=None):
  if guard.failed:raise Stop('latched transport failure')
  category=pred.category
  if category not in ('billing','technical','account'):raise Stop('typed output failure')
  score=float(category==gold.category)
  feedback=('Correct.' if score else 'Incorrect.')+' Expected '+gold.category+' for this support ticket.'
  entry={'id':gold.id,'ticket_sha256':hashlib.sha256(gold.ticket.encode()).hexdigest(),'expected':gold.category,'predicted':category,'score':score,'feedback':feedback,'predictor':pred_name}
  metric_calls.append(entry);guard.write('metric-events.jsonl',entry)
  return dspy.Prediction(score=score,feedback=feedback)
 def examples(split):return [dspy.Example(**x).with_inputs('ticket') for x in data[split]]
 def evaluate(program,split,phase):
  rows=[]
  for ex in examples(split):
   if guard.failed:raise Stop('latched failure')
   pred=program(ticket=ex.ticket)
   if pred.category not in ('billing','technical','account'):raise Stop('parse failure')
   rows.append({'id':ex.id,'expected':ex.category,'predicted':pred.category,'correct':pred.category==ex.category})
  guard.write('evaluations.jsonl',{'phase':phase,'split':split,'rows':rows,'correct':sum(x['correct'] for x in rows),'denominator':len(rows)})
  return sum(x['correct'] for x in rows)
 try:
  with dspy.context(lm=task,adapter=dspy.JSONAdapter(),max_errors=1):
   first=baseline(ticket='I was charged twice for my subscription. Please refund the duplicate payment.')
   guard.write('pilot.jsonl',{'classifier':first.toDict()})
   if first.category!='billing':raise Stop('pilot classifier did not pass')
   with dspy.context(lm=reflection):
    proposal=InstructionProposer()(candidate={'predict':'Classify a support ticket as billing, technical, or account.'},reflective_dataset={'predict':[{'Inputs':{'ticket':'I was charged twice for my subscription.'},'Generated Outputs':{'category':'technical'},'Feedback':'Incorrect. Expected billing because duplicate charges are payment issues.'}]},components_to_update=['predict'])
   guard.write('pilot.jsonl',{'instruction_proposer':proposal})
   instruction=proposal.get('predict','')
   if not isinstance(instruction,str) or len(instruction)<40 or not all(x in instruction.lower() for x in ('billing','technical','account')) or not any(x in instruction.lower() for x in ('charg','payment')):raise Stop('pilot instruction not meaningfully usable')
   before_metrics=len(metric_calls)
   import copy
   frozen_seed={'signature':copy.deepcopy(baseline.predict.signature.dump_state()),'demos':copy.deepcopy(baseline.predict.demos)}
   validation_examples=examples('validation')
   optimizer=dspy.GEPA(metric=metric,max_metric_calls=12,num_threads=1,reflection_lm=reflection,reflection_minibatch_size=2,skip_perfect_score=False,use_merge=False,track_stats=True,log_dir=None,use_wandb=False,use_mlflow=False,seed=42)
   candidate=optimizer.compile(baseline,trainset=examples('train'),valset=validation_examples)
   if guard.failed:raise Stop('GEPA encountered a transport/protocol failure')
   detail=candidate.detailed_results
   from native_baseline import equivalent_baseline
   baseline_val,baseline_evidence=equivalent_baseline(detail,baseline,validation_examples,metric_calls[before_metrics:],frozen_seed)
   guard.write('native-baseline-equivalence.jsonl',baseline_evidence)
   trajectory={'instructions':[{name:p.signature.instructions for name,p in c.named_predictors()} for c in detail.candidates],'parents':detail.parents,'validation_scores':detail.val_aggregate_scores,'validation_subscores':detail.val_subscores,'discovery_eval_counts':detail.discovery_eval_counts,'total_metric_calls':detail.total_metric_calls,'metric_events':len(metric_calls)-before_metrics}
   guard.write('gepa-trajectory.jsonl',trajectory)
   candidate_val=evaluate(candidate,'validation','candidate-after-compile')
   selected=candidate if candidate_val>baseline_val else baseline
   selection={'selected':'candidate' if selected is candidate else 'baseline','baseline_validation_correct':baseline_val,'candidate_validation_correct':candidate_val,'denominator':3,'baseline_wins_ties':True,'candidate_proposed':guard.reflections>1,'proposal_attempts_after_pilot':guard.reflections-1,'accepted_candidates_after_baseline':len(detail.candidates)-1}
   guard.write('selection-frozen.jsonl',selection) # before any held-out execution
   baseline_test=evaluate(baseline,'test','baseline-heldout')
   selected_test=evaluate(selected,'test','selected-heldout')
   state_save(selected,output/'program-state.json')
   loaded=Classifier();loaded.load(output/'program-state.json',allow_pickle=False,allow_unsafe_lm_state=False);loaded.set_lm(task)
   # Verify credential-free state round-trip without spending another API call.
   if loaded.predict.signature.dump_state()!=selected.predict.signature.dump_state():raise Stop('state round-trip mismatch')
   if loaded.predict.demos!=selected.predict.demos or loaded.predict.lm is not task:raise Stop('state/LM reattachment mismatch')
   guard.write('save-load.jsonl',{'verified_state':True,'signature_and_demos_equal':True,'same_guarded_lm_reattached':True,'additional_api_calls':0,'saved_without_lm':True})
   guard.write('result.jsonl',{'status':'completed','selection':selection,'baseline_heldout_correct':baseline_test,'selected_heldout_correct':selected_test,'heldout_denominator_each':3,'optimizer_demonstrated':guard.reflections>1,'accepted_candidate_count':len(detail.candidates)-1,'generation_attempts':guard.calls,'reserved_output_tokens':guard.outputs,'reflection_attempts':guard.reflections,'actual_usage_usd':str(guard.actual)})
 finally:
  for engine in engines:engine.close()
  for transport in transports:transport.close()
  key=None
