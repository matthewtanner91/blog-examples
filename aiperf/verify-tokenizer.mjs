// Offline tokenizer check only; no model construction/generation.
import fs from 'node:fs';
import {AutoTokenizer,env} from '@huggingface/transformers';
env.allowRemoteModels=false;
const tokenizer=await AutoTokenizer.from_pretrained('./model',{local_files_only:true});
const inputs=JSON.parse(fs.readFileSync(process.argv[2]+'/evidence/profile-measured/inputs.json','utf8')).data;
const results=inputs.map(({session_id,payloads})=>{
 const messages=payloads[0].messages;
 const raw=tokenizer(messages[0].content,{add_special_tokens:false}).input_ids.dims.at(-1);
 const templated=tokenizer.apply_chat_template(messages,{add_generation_prompt:true,return_dict:true}).input_ids.dims.at(-1);
 if(raw!==128||templated!==158)throw Error('Unexpected tokenizer accounting');
 return {session_id,raw,templated};
});
console.log(JSON.stringify(results,null,2));
