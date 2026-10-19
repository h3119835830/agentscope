import test from 'node:test';
import assert from 'node:assert/strict';
import {readAttachments,conversationFor} from './policyConversationInput.mjs';
const file=(name,text)=>({name,size:new TextEncoder().encode(text).length,arrayBuffer:async()=>new TextEncoder().encode(text).buffer});
test('selected UTF-8 files preserve actual body; unsupported or oversized files never partially append',async()=>{
 const existing=await readAttachments([file('场景.md','禁止读取员工资料。')]);
 assert.deepEqual(existing,[{name:'场景.md',text:'禁止读取员工资料。'}]);
 for(const invalid of [file('报告.pdf','binary'),file('large.md','x'.repeat(8001)),file('zero.txt','\0'),file('empty.txt',' '),{name:'bad.txt',size:1,arrayBuffer:async()=>new Uint8Array([255]).buffer}])await assert.rejects(readAttachments([file('valid.md','good'),invalid],existing));
 assert.equal(existing.length,1);
 await assert.rejects(readAttachments(Array.from({length:10},(_,i)=>file(i+'.md','a')),existing));
});
test('dialogue context preserves the prior question and bounds the exact supplied conversation',()=>{
 const history=Array.from({length:9},(_,i)=>({text:'第'+i+'轮',items:[],questions:['请提供路径'+i],gaps:[]}));
 const messages=conversationFor(history);assert.equal(messages.length,6);assert.equal(messages[0].content,'第6轮');assert.equal(messages.at(-1).content,'请提供路径8');
 assert.deepEqual(conversationFor([]),[]);
});
