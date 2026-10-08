import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {startupRecoveryPath,startupRecoveryRequest,pollStartupRecovery} from './startupRecovery.mjs';
const recovery={eligible:true,origin:{context_hash:'frozen-context',manifest_hash:'frozen-manifest'},candidate:{task_id:'candidate-task',proposal_hash:'candidate-hash',status:'awaiting_review'}};
test('recovery prepare and reuse are bound to immutable origin and exact selected candidate without approval',()=>{
 assert.equal(startupRecoveryPath('old/task'),'/api/managed/tasks/old%2Ftask/startup/recovery');
 assert.deepEqual(startupRecoveryRequest(recovery,'reuse'),{action:'reuse',expected_context_hash:'frozen-context',expected_manifest_hash:'frozen-manifest',expected_candidate_task_id:'candidate-task',expected_candidate_proposal_hash:'candidate-hash'});
 assert.deepEqual(startupRecoveryRequest(recovery,'rebuild'),{action:'rebuild',expected_context_hash:'frozen-context',expected_manifest_hash:'frozen-manifest'});
 assert.throws(()=>startupRecoveryRequest({...recovery,eligible:false,blocked_reason:'已有执行版本'},'rebuild'),/已有执行版本/);
 assert.throws(()=>startupRecoveryRequest({...recovery,candidate:null},'reuse'),/没有可核验/);
 const explicit={task_id:'second',proposal_hash:'second-hash',status:'awaiting_review'};assert.equal(startupRecoveryRequest({...recovery,candidate:null,candidates:[explicit]},'reuse',explicit).expected_candidate_task_id,'second');
});
test('failed startup cannot retry fixed context start, while runtime recovery and explicit startup confirmation remain',()=>{
 const workbench=readFileSync(new URL('./ManagedWorkbench.jsx',import.meta.url),'utf8'),hub=readFileSync(new URL('./TaskHub.jsx',import.meta.url),'utf8'),controller=readFileSync(new URL('./StartupRecovery.jsx',import.meta.url),'utf8');
 assert.match(workbench,/s.phase==='failed'&&s.version>0/);assert.match(workbench,/embedded onRecoveryTask=\{onSelectTask\}/);assert.match(workbench,/本次生成失败，尚无可审核语句/);
 assert.match(hub,/!embedded&&<section className="panel task-section task-record-summary"/);assert.match(hub,/!embedded&&<details open ><summary>启动前策略/);assert.match(hub,/onRecoveryTask=\{onSelectTask\}/);assert.match(hub,/startup\/confirm/);
 assert.doesNotMatch(controller,/\/start[`'"]|startup\/confirm|decision:.*approve|window\.|history\./);
});

test('recovery polling is serial, retries GET failure after clearing stale ready data, and ignores unmounted responses',async()=>{
 const pending=[],timers=new Map(),seen=[],errors=[];let id=0,calls=0,ready=null;
 const stop=pollStartupRecovery({read:()=>{calls++;return new Promise((resolve,reject)=>pending.push({resolve,reject}));},onData:data=>{ready=data;seen.push(data);},onError:error=>{ready=null;errors.push(error.message);},schedule:(fn,delay)=>{assert.equal(delay,3000);timers.set(++id,fn);return id;},cancel:id=>timers.delete(id)});
 const flush=async()=>{await Promise.resolve();await Promise.resolve();};
 assert.equal(calls,1);assert.equal(timers.size,0);pending.shift().resolve({candidate:{status:'awaiting_review'}});await flush();assert.equal(ready.candidate.status,'awaiting_review');assert.equal(timers.size,1);
 const tick=()=>{const [key,fn]=[...timers][0];timers.delete(key);fn();};tick();assert.equal(calls,2);assert.equal(timers.size,0);await flush();assert.equal(calls,2);
 pending.shift().reject(new Error('offline'));await flush();assert.equal(ready,null);assert.deepEqual(errors,['offline']);assert.equal(timers.size,1);
 tick();assert.equal(calls,3);stop();pending.shift().resolve({candidate:{status:'awaiting_review'}});await flush();assert.equal(seen.length,1);assert.equal(timers.size,0);
});
