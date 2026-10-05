import test from 'node:test';
import assert from 'node:assert/strict';
const {apply}=await import(process.env.DSH_PLUGIN_TEST_PATH||'./lib/index.js');

process.env.AGENTSCOPE_SCOPE_MANAGER='1';
process.env.AGENTSCOPE_TASK_ID='synthetic-test';
process.env.AGENTSCOPE_TASK_TOKEN='test-only-token';
function harness(states){
  const events={},requests=[];
  globalThis.fetch=async(url,options={})=>{
    requests.push({url,body:options.body?JSON.parse(options.body):null});
    return {ok:true,json:async()=>url.endsWith('/gate')?states.shift()||{
      gate:'open',message_revision:2,snapshot_id:'scope-2',scope:{allowed_write_dirs:['backend'],allow_output:false},messages:[],
    }:{stored:true}};
  };
  apply({on:(name,handler)=>events[name]=handler,tools:{register:()=>{}}},{baseUrl:'http://127.0.0.1:8000'});
  return {events,requests};
}
const open=revision=>({gate:'open',message_revision:revision,snapshot_id:'s'+revision,scope:{allowed_write_dirs:['backend'],allow_output:false},messages:[]});

test('native hook delivers changed context before allowing a tool',async()=>{
  const {events,requests}=harness([open(2),open(2)]);
  const exec={name:'bash',callId:'call1',signal:new AbortController().signal};
  const first=await events['tools/pre-execute'](exec,()=>({kind:'allow'}));
  assert.equal(first.kind,'deny');
  assert.ok(first.reason.includes('snapshot_id'));
  assert.equal((await events['tools/pre-execute'](exec,()=>({kind:'allow'}))).kind,'allow');
  await events['tools/post-execute'](exec,{isError:false},()=>({kind:'allow'}));
  const receipt=requests.find(r=>r.url.endsWith('/tool-result'));
  assert.equal(receipt.body.args.started.snapshot_id,'s2');
});

test('pending restriction pauses at a native boundary and reports the pause',async()=>{
  const {events,requests}=harness([{...open(1),gate:'waiting_constraint'},open(2)]);
  const result=await events['tools/pre-execute']({name:'write',callId:'waiting',signal:new AbortController().signal},()=>({kind:'allow'}));
  assert.equal(result.kind,'deny');
  assert.ok(requests.some(r=>r.body?.args?.kind==='pause'));
});

test('failed application denies execution without calling the tool',async()=>{
  const {events}=harness([{...open(1),gate:'failed'}]);
  let called=false;
  const result=await events['tools/pre-execute']({name:'bash',callId:'failure',signal:new AbortController().signal},()=>{called=true;});
  assert.equal(result.kind,'deny');
  assert.equal(called,false);
});

test('cancelled pending restriction remains cancelled',async()=>{
  const {events}=harness([{...open(1),gate:'waiting_constraint'}]);
  const controller=new AbortController();
  setTimeout(()=>controller.abort(),20);
  assert.equal((await events['tools/pre-execute']({name:'bash',callId:'cancel',signal:controller.signal},()=>({kind:'allow'}))).kind,'cancel');
});
