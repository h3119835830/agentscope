import test from 'node:test';
import assert from 'node:assert/strict';
import {runtimeObservation} from '../lib/runtime-observation.js';
const session={id:'native'};
test('private reasoning, attempt streams and raw compaction output are excluded',()=>{
 for(const type of ['assistant/attempt','assistant/stream','assistant/message'])assert.equal(runtimeObservation(session,{type,data:{message:{content:[{type:'reasoning',text:'PRIVATE'}]}}}),null);
 const observed=runtimeObservation(session,{type:'compaction/summary',seq:3,data:{summary:[{type:'text',text:'public task memory'},{type:'reasoning',text:'PRIVATE'}],rawOutput:[{type:'text',text:'PRIVATE'}]}});
 assert.equal(observed.content,'public task memory');assert.equal(observed.category,'memory');assert.doesNotMatch(JSON.stringify(observed),/PRIVATE/);
});
test('prompt projection uses current surface including cleared prompts',()=>{
 const s={...session,deriveMessages:()=>[{role:'system',content:[{type:'text',text:'current prompt'}]}]};
 assert.match(runtimeObservation(s,{type:'system/message',seq:4,data:{message:{content:[{type:'text',text:'old prompt'}]}}}).content,/current prompt/);
 assert.equal(runtimeObservation({...s,deriveMessages:()=>[]},{type:'system/message',seq:5,data:{message:{content:[]}}}).content,'[]');
});
test('tool observations have no model connection secrets',()=>{
 const o=runtimeObservation(session,{type:'request/header',seq:2,data:{header:{provider:'secret provider',apiKey:'PRIVATE',tools:[{name:'read',parameters:{type:'object'}}]}}});
 assert.equal(o.category,'tools');assert.doesNotMatch(o.content,/PRIVATE|secret provider/);
});
test('kernel feedback echo does not retrigger Pi',()=>assert.equal(runtimeObservation(session,{type:'user/message',data:{source:{kind:'context'},content:[{type:'text',text:'[ActPlane operation feedback] denied'}]}}),null));
