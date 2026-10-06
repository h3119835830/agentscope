import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequester} from '../lib/transport.js';

test('accepted event waits through an outage and retains the same idempotency key',async()=>{
 let clock=0,attempts=0;const sent=[],events=[];let recovered=0;
 const request=createRequester({now:()=>clock,sleep:async ms=>{clock+=ms;},onRecovery:()=>recovered++,fetchImpl:async(_url,options)=>{
  sent.push(options.body);if(++attempts<3)throw TypeError('fetch failed');
  const value=JSON.parse(options.body);events.push(value.event_key);
  return {ok:true,status:200,text:async()=>JSON.stringify({accepted:true})};
 }});
 const body=JSON.stringify({event_key:'accepted:session:rpc',text:'new restriction'});
 let released=false;const admitted=request('local',{method:'POST',body}).then(()=>{released=true;});
 assert.equal(released,false);await admitted;
 assert.deepEqual(events,['accepted:session:rpc']);assert.equal(new Set(sent).size,1);assert.equal(recovered,1);
});

test('authentication failure is never retried or treated as success',async()=>{
 let calls=0;const request=createRequester({fetchImpl:async()=>{calls++;return {ok:false,status:401,text:async()=>'{"detail":"revoked"}'};}});
 await assert.rejects(request('local'),/revoked/);assert.equal(calls,1);
});

test('unrecovered outage reaches a bounded failed-closed deadline',async()=>{
 let clock=0,granted=false;const request=createRequester({budgetMs:500,now:()=>clock,sleep:async ms=>{clock+=ms;},fetchImpl:async()=>{throw TypeError('offline');}});
 await assert.rejects(request('local').then(()=>{granted=true;}),/execution remains paused/);
 assert.equal(granted,false);assert.equal(clock,500);
});
