"""Verify and reuse GEPA's actual initial full validation of the unchanged seed."""
import hashlib
from guard import Stop
def equivalent_baseline(detail,baseline,validation,events,frozen_seed):
 if len(validation)!=3 or len(events)<3 or not detail.candidates:raise Stop('native baseline coverage missing')
 seed=detail.candidates[0]
 if seed.predict.signature.dump_state()!=frozen_seed['signature'] or baseline.predict.signature.dump_state()!=frozen_seed['signature'] or seed.predict.demos!=frozen_seed['demos'] or baseline.predict.demos!=frozen_seed['demos']:raise Stop('native candidate0 differs from frozen baseline')
 scores=detail.val_subscores[0]
 if set(scores)!=set(range(3)) or any(type(k) is not int for k in scores):raise Stop('native validation IDs changed')
 rows=[]
 for index,example in enumerate(validation):
  event=events[index];expected_hash=hashlib.sha256(example.ticket.encode()).hexdigest()
  if event['id']!=example.id or event['ticket_sha256']!=expected_hash or event['expected']!=example.category:raise Stop('native validation row/input mismatch')
  if event['predicted'] not in ('billing','technical','account'):raise Stop('invalid baseline prediction')
  score=float(event['predicted']==example.category)
  if event['score']!=score or scores[index]!=score:raise Stop('native baseline metric mismatch')
  rows.append({'native_val_id':index,'frozen_id':example.id,'ticket_sha256':expected_hash,'expected':example.category,'predicted':event['predicted'],'score':score})
 correct=sum(r['score'] for r in rows)
 if abs(detail.val_aggregate_scores[0]-correct/3)>1e-12:raise Stop('native baseline aggregate mismatch')
 return int(correct),{'source':'GEPA candidate0 initial full validation','rows':rows,'denominator':3,'correct':int(correct),'separate_duplicate_validation_requests':0,'same_frozen_order_and_exact_metric_verified':True}
