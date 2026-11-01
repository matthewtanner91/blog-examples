"""Offline evidence checks; argument is the unique run directory. No inference."""
import json,pathlib,sys
p=pathlib.Path(sys.argv[1])/'evidence'
read=lambda name:json.loads((p/name).read_text())
events=[json.loads(s) for s in (p/'server-events.jsonl').read_text().splitlines()]
requests=[e for e in events if e['event']=='request']; responses=[e for e in events if e['event']=='response']
records=[json.loads(s) for s in (p/'profile-measured/profile_export.jsonl').read_text().splitlines()]
inputs=read('profile-measured/inputs.json')['data']; aggregate=read('profile-measured/profile_export_aiperf.json'); cleanup=read('cleanup.json')
assert len(requests)==len(responses)==5 and len(records)==len(inputs)==4
assert [e['id'] for e in requests]==[e['id'] for e in responses]==['local-'+str(i) for i in range(1,6)]
for i,(saved,req,response,record) in enumerate(zip(inputs,requests[1:],responses[1:],records)):
    assert saved['payloads']==[req['body']], 'Ordered exact input payload mismatch'
    assert record['metadata']['conversation_id']==saved['session_id']
    assert record['metadata']['profiling_index']==0  # one profiling phase, not request index
    assert not record['metadata']['was_cancelled'] and record['metadata']['benchmark_phase']=='profiling'
    assert req['body']['stream'] is True and req['body']['stream_options']['include_usage'] is True
    assert response['usage']=={'prompt_tokens':158,'completion_tokens':32,'total_tokens':190}
    assert record['metrics']['usage_completion_tokens']['value']==32
    assert record['metrics']['input_sequence_length']['value']==158
assert requests[0]['body']['stream'] is False
assert responses[0]['usage']['completion_tokens']<=16
assert aggregate['is_complete'] and not aggregate['was_cancelled'] and not aggregate['error_summary']
assert aggregate['request_count']['avg']==4
assert all(e['pressure']=='1' and e['rss']<=1500000000 for e in events if e['event']=='resource')
assert not any(e['event'] in ('error','fatal','resource_stop','shutdown_error') for e in events)
assert [e['event'] for e in events][-2:]==['shutdown','disposed']
gates=[json.loads(s) for s in (p/'gates.jsonl').read_text().splitlines()]
rss=[json.loads(s) for s in (p/'rss.jsonl').read_text().splitlines()]
assert gates and rss and all(e['pressure']=='1' for e in gates) and all(0<e['rss']<=1500000000 for e in rss)
identity=read('integrity-before.json')
snapshot='hf-cache/models--HuggingFaceTB--SmolLM2-135M-Instruct/snapshots/12fd25f77366fa6b3b4b768ec3050bf629380bac/'
for name in ('config.json','generation_config.json','tokenizer.json','tokenizer_config.json','special_tokens_map.json','merges.txt','vocab.json'):
    assert identity['model/'+name]==identity[snapshot+name]
assert cleanup['integrity_unchanged']
assert read('integrity-before.json')==read('integrity-after.json')
assert cleanup['runner_status']==cleanup['profile_exit']==cleanup['server_exit']==0
assert cleanup['endpoint_closed'] and cleanup['profile_group_absent'] and cleanup['server_group_absent']
assert not any(k.endswith('forced_kill') for k in cleanup)
assert not (p/'server.stderr').read_bytes()
print('Structural evidence checks passed; additionally run verify-tokenizer.mjs and check source/model/dependency receipts.')
