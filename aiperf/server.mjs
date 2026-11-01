import http from 'node:http';
import fs from 'node:fs';
import {execFileSync} from 'node:child_process';
import {AutoTokenizer,AutoModelForCausalLM,TextStreamer,env} from '@huggingface/transformers';
env.allowRemoteModels=false;
const name='HuggingFaceTB/SmolLM2-135M-Instruct';
const log=(event,data={})=>fs.appendFileSync('evidence/server-events.jsonl',JSON.stringify({time:new Date().toISOString(),event,...data})+'\n');
function gate(){const pressure=execFileSync('/usr/sbin/sysctl',['-n','kern.memorystatus_vm_pressure_level'],{encoding:'utf8'}).trim();log('resource',{pressure,rss:process.memoryUsage().rss});if(pressure!=='1'||process.memoryUsage().rss>1500000000)throw Error('Resource gate failed');}
gate();log('loading',{name,revision:'12fd25f77366fa6b3b4b768ec3050bf629380bac',pid:process.pid});
const tokenizer=await AutoTokenizer.from_pretrained('./model',{local_files_only:true});
const model=await AutoModelForCausalLM.from_pretrained('./model',{local_files_only:true,dtype:'q8',device:'cpu',session_options:{intraOpNumThreads:2,interOpNumThreads:1}});
let active=false,count=fs.existsSync('evidence/server-events.jsonl')?fs.readFileSync('evidence/server-events.jsonl','utf8').trim().split('\n').filter(l=>JSON.parse(l).event==='request').length:0;
const server=http.createServer(async(req,res)=>{
 if(req.method==='GET'&&req.url==='/health'){res.end(JSON.stringify({ready:true,count}));return;}
 if(req.method==='GET'&&req.url==='/v1/models'){res.end(JSON.stringify({object:'list',data:[{id:name,object:'model',owned_by:'local-demo'}]}));return;}
 if(req.method!=='POST'||req.url!=='/v1/chat/completions'){res.writeHead(404).end();return;}
 if(active||count>=5){res.writeHead(429).end('slot or request limit');return;}
 active=true;let body='';
 try{
  for await(const chunk of req){body+=chunk;if(body.length>20000)throw Error('Body too large');}
  const b=JSON.parse(body);const max=b.max_completion_tokens??b.max_tokens??32;
  if(b.model!==name||!Number.isInteger(max)||max<1||max>32)throw Error('Model/output constraint');
  const inputs=tokenizer.apply_chat_template(b.messages,{add_generation_prompt:true,return_dict:true});
  const prompt=inputs.input_ids.dims.at(-1);if(prompt>512)throw Error('Prompt exceeds 512 tokens');
  gate();count++;const id='local-'+count;let tokens=0,text='';
  log('request',{id,body:b,prompt_tokens:prompt});
  const chunk=(delta,finish=null)=>({id,object:'chat.completion.chunk',created:Math.floor(Date.now()/1000),model:name,choices:[{index:0,delta,finish_reason:finish}]});
  const send=x=>res.write('data: '+JSON.stringify(x)+'\n\n');
  if(b.stream)res.writeHead(200,{'Content-Type':'text/event-stream'});
  const streamer=new TextStreamer(tokenizer,{skip_prompt:true,skip_special_tokens:true,token_callback_function:ids=>{tokens+=ids.length;},callback_function:s=>{text+=s;if(b.stream)send(chunk({content:s}));}});
  await model.generate({...inputs,max_new_tokens:max,do_sample:false,streamer});
  const usage={prompt_tokens:prompt,completion_tokens:tokens,total_tokens:prompt+tokens};
  if(b.stream){send(chunk({},tokens>=max?'length':'stop'));send({...chunk({}),choices:[],usage});res.end('data: [DONE]\n\n');}
  else{res.setHeader('Content-Type','application/json');res.end(JSON.stringify({id,object:'chat.completion',model:name,choices:[{index:0,message:{role:'assistant',content:text},finish_reason:tokens>=max?'length':'stop'}],usage}));}
  log('response',{id,text,usage});gate();
 }catch(e){log('error',{message:String(e)});if(!res.headersSent)res.writeHead(500);res.end(String(e));process.exitCode=1;server.close();}
 finally{active=false;}
});
server.listen(18761,'127.0.0.1',()=>log('listening',{host:'127.0.0.1',port:18761}));
server.on('error',e=>{log('fatal',{message:String(e)});process.exit(1);});
const pressureTimer=setInterval(()=>{try{gate();}catch(e){log('resource_stop',{message:String(e)});process.exit(1);}},1000).unref();
process.once('SIGTERM',async()=>{
  log('shutdown',{count});
  clearInterval(pressureTimer);
  try {
    await new Promise((resolve,reject)=>server.close(error=>error?reject(error):resolve()));
    await model.dispose();
    log('disposed',{count});
    process.exitCode=0;
  } catch(error) {
    log('shutdown_error',{message:String(error)});
    process.exitCode=1;
  }
});
