import test from 'node:test';
import assert from 'node:assert/strict';
import {openAgentPage} from './openAgentPage.mjs';

function browser(){
 const calls=[];
 const tab={opener:{},closed:false,location:{replace:url=>calls.push(['navigate',url])},close:()=>calls.push(['close'])};
 return {calls,tab,open:(...args)=>{calls.push(['popup',...args]);return tab;}};
}

test('an existing instance opens its freshly resolved native URL without a start request',async()=>{
 const b=browser(),url='http://127.0.0.1:18020/?native=opaque#launch=opaque';
 await openAgentPage({id:'instance-a',browser:b,post:async path=>{b.calls.push(['post',path]);return {url};}});
 assert.deepEqual(b.calls,[['popup','about:blank','_blank'],['post','/api/agent-instances/instance-a/open'],['navigate',url]]);
 assert.equal(b.tab.opener,null);
});

test('explicit start completes before resolving the same instance entry',async()=>{
 const b=browser();
 await openAgentPage({id:'instance/a',start:true,browser:b,post:async path=>{b.calls.push(['post',path]);return {url:'http://127.0.0.1:18020/'};}});
 assert.deepEqual(b.calls.slice(1,3),[['post','/api/agent-instances/instance%2Fa/start'],['post','/api/agent-instances/instance%2Fa/open']]);
});

test('blocked popup is reported before starting or contacting an instance',async()=>{
 let requests=0;
 await assert.rejects(openAgentPage({id:'instance-a',start:true,browser:{open:()=>null},post:async()=>{requests++;}}),/浏览器阻止/);
 assert.equal(requests,0);
});

test('native entry failure closes the blank tab and surfaces the actual error',async()=>{
 const b=browser();
 await assert.rejects(openAgentPage({id:'instance-a',browser:b,post:async()=>{throw Error('实例当前未运行');}}),/实例当前未运行/);
 assert.deepEqual(b.calls,[['popup','about:blank','_blank'],['close']]);
});

test('a start failure cannot navigate or fall through to the open request',async()=>{
 const b=browser(),requests=[];
 await assert.rejects(openAgentPage({id:'instance-a',start:true,browser:b,post:async path=>{requests.push(path);throw Error('保护核验失败');}}),/保护核验失败/);
 assert.deepEqual(requests,['/api/agent-instances/instance-a/start']);
 assert.deepEqual(b.calls.at(-1),['close']);
});

test('malformed and nonlocal entries cannot navigate a popup',async()=>{
 for(const url of [undefined,'not-a-url','javascript:alert(1)','http://example.com/','http://127.0.0.1.example.com/','https://127.0.0.1:18020/','http://user:pass@127.0.0.1:18020/']){
  const b=browser();
  await assert.rejects(openAgentPage({id:'instance-a',browser:b,post:async()=>({url})}),/本机核验/);
  assert.deepEqual(b.calls,[['popup','about:blank','_blank'],['close']]);
 }
});

test('a user-closed popup reports failure instead of silently claiming an open',async()=>{
 const b=browser();
 await assert.rejects(openAgentPage({id:'instance-a',browser:b,post:async()=>{b.tab.closed=true;return {url:'http://127.0.0.1:18020/'};}}),/标签页已关闭/);
 assert.equal(b.calls.some(call=>call[0]==='navigate'),false);
});
