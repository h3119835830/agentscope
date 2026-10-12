import test from 'node:test';
import assert from 'node:assert/strict';
import {requestJSON,singleFlight,readOverview,agentSummary} from './readLifecycle.mjs';
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const ok=value=>({ok:true,json:async()=>value});

test('a hung read leaves loading within its deadline and aborts the transport',async()=>{
 let signal;
 await assert.rejects(requestJSON((_url,options)=>{signal=options.signal;return new Promise(()=>{});},'/read',{},15),/读取超时/);
 assert.equal(signal.aborted,true);
});
test('the read deadline also covers a response body that never finishes',async()=>{
 await assert.rejects(requestJSON(async()=>({ok:true,json:()=>new Promise(()=>{})}),'/read',{},15),/读取超时/);
});
test('slow writes retain their original completion contract',async()=>{
 const signal=new AbortController().signal;
 const result=await requestJSON(async(_url,options)=>{assert.equal(options.signal,signal);await new Promise(resolve=>setTimeout(resolve,25));return ok({saved:true});},'/write',{method:'POST',signal},5);
 assert.deepEqual(result,{saved:true});
});
test('read cancellation preserves caller intent and invalid JSON cannot look like success',async()=>{
 const parent=new AbortController();let signal;
 const pending=requestJSON((_url,options)=>{signal=options.signal;return new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new Error('cancelled'))));},'/read',{signal:parent.signal},100);
 parent.abort();await assert.rejects(pending,/cancelled/);assert.equal(signal.aborted,true);
 await assert.rejects(requestJSON(async()=>({ok:true,json:async()=>{throw new Error('parse');}}),'/read'),/无法读取/);
 await assert.rejects(requestJSON(async()=>({ok:false,status:401,json:async()=>({detail:'需要认证'})}),'/read'),/需要认证/);
});
test('polls and manual retry join one outstanding read, then allow a fresh read',async()=>{
 let calls=0;const slow=deferred();const refresh=singleFlight(()=>{calls++;return slow.promise;});
 const first=refresh();for(let i=0;i<10;i++)assert.equal(refresh(),first);
 await tick();assert.equal(calls,1);
 slow.resolve('visible');assert.equal(await first,'visible');
 await refresh();assert.equal(calls,2);
});
test('a failed flight releases retries without concurrent replacements',async()=>{
 let calls=0;const refresh=singleFlight(async()=>{if(++calls===1)throw new Error('offline');return 'recovered';});
 await assert.rejects(refresh(),/offline/);assert.equal(await refresh(),'recovered');
});
test('current Agents render before slow service status or historical counts',async()=>{
 const status=deferred(),counts=deferred(),events=[];
 const request=readOverview({api:url=>url.endsWith('/agents')?Promise.resolve({instances:[{id:'a',mode:'controlled',connected:true,active:true,pid:42}]}):url.endsWith('/status')?status.promise:counts.promise,
  onAgents:data=>events.push(['agents',data]),onStatus:data=>events.push(['status',data]),onCounts:data=>events.push(['counts',data]),onError:()=>assert.fail('unexpected error')});
 await tick();assert.deepEqual(events.map(e=>e[0]),['agents']);assert.equal(events[0][1].stats.verified_agents,1);
 status.resolve({ready:true});await tick();assert.deepEqual(events.map(e=>e[0]),['agents','status']);
 counts.resolve({stats:{agents:0}});await request;assert.deepEqual(events.map(e=>e[0]),['agents','status','counts']);
});
test('first-load failure reaches an error and a subsequent read can recover',async()=>{
 let fail=true;const events=[];
 const options={api:async url=>{if(url.endsWith('/agents')){if(fail)throw new Error('offline');return {instances:[]};}return {};},onAgents:()=>events.push('ready'),onStatus:()=>{},onCounts:()=>{},onError:kind=>events.push(kind)};
 await readOverview(options);assert.deepEqual(events,['agents']);fail=false;await readOverview(options);assert.deepEqual(events,['agents','ready']);
});
test('failure of optional history does not withdraw the live Agent result',async()=>{
 const events=[];
 await readOverview({api:async url=>{if(url.endsWith('/summary'))throw new Error('slow history');return {instances:[]};},onAgents:()=>events.push('ready'),onStatus:()=>{},onCounts:()=>assert.fail(),onError:kind=>events.push(kind)});
 assert.deepEqual(events,['ready','counts']);
});
test('Agent counts use exact controlled rows without promoting observed entries',()=>{
 assert.deepEqual(agentSummary({instances:[{id:'a',mode:'controlled',active:true,connected:true},{id:'b',mode:'controlled',active:true,connected:false},{id:'c',mode:'observed',active:true,connected:true}]}).stats,{agents:2,verified_agents:1});
});
