import test from 'node:test';
import assert from 'node:assert/strict';
import {openConnection,restartConnection} from './connectionOpen.mjs';

const row={id:'instance-a',mode:'controlled',agent_type:'dsh',generation:'g1',policy_hash:'p1',gate:'open',
 product_status:{runtime:{state:'unknown'}},connected:false};
const url='http://127.0.0.1:18022/';
function fixture(){
 const requests=[],navigation=[],recoveries=[];
 const browser={open:()=>({closed:false,opener:{},location:{replace:uri=>navigation.push(uri)},close(){}})};
 const post=async(path)=>{requests.push(path);if(path.endsWith('/open'))throw Error('此实例未接入相应操作');return structuredClone(row);};
 return {row,post,browser,requests,navigation,recoveries,onRecovery:value=>recoveries.push(value)};
}

test('unknown entry attempts open/check only; cancel has no lifecycle requests and freezes identity',async()=>{
 const f=fixture();await openConnection(f);
 assert.deepEqual(f.requests,['/api/agent-instances/instance-a/open','/api/agent-instances/instance-a/check']);
 assert.equal(f.recoveries.length,1);
 assert.notEqual(f.recoveries[0].row,f.row);
 assert.deepEqual(f.recoveries[0].row,f.row);
 assert.deepEqual(f.navigation,[]);
});
test('existing entry succeeds without check or restart even when observation was unknown',async()=>{
 const f=fixture();f.post=async path=>{f.requests.push(path);return {url};};
 await openConnection(f);
 assert.deepEqual(f.requests,['/api/agent-instances/instance-a/open']);
 assert.deepEqual(f.navigation,[url]);assert.equal(f.recoveries.length,0);
});
test('blocked popup, bad URL and failed recheck cannot offer or send a restart',async()=>{
 for(const kind of ['popup','url','check']){
  const f=fixture();
  if(kind==='popup')f.browser.open=()=>null;
  if(kind==='url')f.post=async()=>({url:'https://evil.invalid/'});
  if(kind==='check')f.post=async path=>{f.requests.push(path);throw Error('不可用');};
  await assert.rejects(openConnection(f));
  assert.equal(f.recoveries.length,0);
  assert.equal(f.requests.some(p=>p.endsWith('/start')),false);
 }
});
test('other target, observed entry and busy/running states cannot offer recovery',async()=>{
 for(const change of [{id:'other'},{mode:'observed'},{gate:'starting'},{gate:'updating'},
  {product_status:{runtime:{state:'running'}}},{product_status:{runtime:{state:'paused'}}}]){
  const f=fixture();f.post=async path=>{if(path.endsWith('/open'))throw Error('未打开');return {...row,...change};};
  await assert.rejects(openConnection(f));
  assert.equal(f.recoveries.length,0);
 }
});
test('confirmation rechecks the frozen target before its explicit start and fresh open',async()=>{
 const f=fixture();f.post=async path=>{f.requests.push(path);return path.endsWith('/open')?{url}:structuredClone(row);};
 await restartConnection({...f,snapshot:row});
 assert.deepEqual(f.requests,['/api/agent-instances/instance-a/check','/api/agent-instances/instance-a/start','/api/agent-instances/instance-a/open']);
 assert.deepEqual(f.navigation,[url]);
});
test('identity changes or check failure abort confirmation before start',async()=>{
 for(const change of [{id:'other'},{generation:'g2'},{policy_hash:'p2'},{launch:{hash:'new'}},{mode:'observed'},null]){
  const f=fixture();f.post=async path=>{f.requests.push(path);if(!change)throw Error('检查失败');return {...row,...change};};
  await assert.rejects(restartConnection({...f,snapshot:row}));
  assert.deepEqual(f.requests,['/api/agent-instances/instance-a/check']);
 }
});
test('if the same process recovered while confirmation was open, reuse it without restarting',async()=>{
 const f=fixture();f.post=async path=>{f.requests.push(path);return path.endsWith('/check')?{...row,status:'running',connected:true,product_status:{runtime:{state:'running'}}}:{url};};
 await restartConnection({...f,snapshot:row});
 assert.deepEqual(f.requests,['/api/agent-instances/instance-a/check','/api/agent-instances/instance-a/open']);
});
test('start failure never falls through to native navigation',async()=>{
 const f=fixture();f.post=async path=>{f.requests.push(path);if(path.endsWith('/start'))throw Error('保护核验失败');return row;};
 await assert.rejects(restartConnection({...f,snapshot:row}),/保护核验失败/);
 assert.deepEqual(f.requests,['/api/agent-instances/instance-a/check','/api/agent-instances/instance-a/start']);
 assert.deepEqual(f.navigation,[]);
});
