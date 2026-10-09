const {test}=require('node:test');
const assert=require('node:assert/strict');
const {createNativeSessionLauncher}=require('./session-controller.js');
const ref={instanceId:'instance-original',sessionId:'session-original'};
function fixture(state={}){
 const calls={inspect:0,resume:0,reconnect:0,entry:0,windows:0,closed:0};
 const observed={...ref,executor:'idle',connection:'connected',sessionNavigation:true,resumeAllowed:true,revision:4,...state};
 const entry={...ref,scope:'session',url:'http://127.0.0.1:18020/?auth=test-only#native-session'};
 const target={opener:{},closed:false,location:{replace(url){calls.navigated=url;}},close(){calls.closed++;}};
 const adapter={async inspect(){calls.inspect++;return observed;},async resume(r,v){calls.resume++;assert.deepEqual(r,ref);assert.equal(v,4);},async reconnect(){calls.reconnect++;},async resolveSessionEntry(){calls.entry++;return entry;}};
 const browser={open(url,name){calls.windows++;assert.equal(url,'about:blank');calls.target=name;return target;}};
 return {calls,adapter,browser,target,entry,launcher:createNativeSessionLauncher({adapter,browser})};
}
test('online session navigates external native entry without restart',async()=>{const f=fixture();const r=await f.launcher.open(ref);assert.equal(r.kind,'reused');assert.equal(f.calls.resume,0);assert.equal(f.calls.navigated,f.entry.url);assert.equal(f.calls.target,'_blank');assert.equal(f.target.opener,null);assert.equal(r.url,undefined);});
test('transport loss reconnects rather than restarts',async()=>{const f=fixture({connection:'disconnected'});assert.equal((await f.launcher.open(ref)).kind,'reconnected');assert.equal(f.calls.reconnect,1);assert.equal(f.calls.resume,0);});
test('stopped execution resumes exact session with observed revision',async()=>{const f=fixture({executor:'stopped'});assert.equal((await f.launcher.open(ref)).kind,'resumed');assert.equal(f.calls.resume,1);});
test('concurrent clicks use one launch window and one resume',async()=>{const f=fixture({executor:'stopped'});const a=f.launcher.open(ref),b=f.launcher.open(ref);assert.equal(a,b);await a;assert.equal(f.calls.windows,1);assert.equal(f.calls.resume,1);});
test('unbound sample does not launch any window or process',async()=>{const f=fixture();await assert.rejects(f.launcher.open(null),/尚未绑定/);assert.equal(f.calls.windows,0);assert.equal(f.calls.inspect,0);});
test('popup denial performs no backend operation',async()=>{const f=fixture();f.browser.open=()=>null;await assert.rejects(f.launcher.open(ref),/浏览器阻止/);assert.equal(f.calls.inspect,0);assert.equal(f.calls.resume,0);});
test('instance-only capability cannot masquerade as session navigation',async()=>{const f=fixture({sessionNavigation:false,executor:'stopped'});await assert.rejects(f.launcher.open(ref),/不支持定位/);assert.equal(f.calls.resume,0);assert.equal(f.calls.entry,0);assert.equal(f.calls.closed,1);});
test('unknown state and pending approval cannot start execution',async()=>{for(const state of [{executor:'unknown'},{executor:'stopped',resumeAllowed:false}]){const f=fixture(state);await assert.rejects(f.launcher.open(ref));assert.equal(f.calls.resume,0);assert.equal(f.calls.navigated,undefined);}});
test('wrong-session or instance-only entry is rejected',async()=>{for(const change of [{sessionId:'other'},{scope:'instance'}]){const f=fixture();Object.assign(f.entry,change);await assert.rejects(f.launcher.open(ref),/未定位/);assert.equal(f.calls.navigated,undefined);assert.equal(f.calls.closed,1);}});
test('unsafe URL fails closed and retry releases pending state',async()=>{const f=fixture();f.entry.url='https://example.com/';await assert.rejects(f.launcher.open(ref),/本机校验/);f.entry.url='http://127.0.0.1:18020/';await f.launcher.open(ref);assert.equal(f.calls.windows,2);assert.equal(f.calls.closed,1);});
