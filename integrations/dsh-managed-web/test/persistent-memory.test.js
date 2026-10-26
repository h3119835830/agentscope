import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {persistentMemoryObservation as observe} from '../lib/persistent-memory.js';
const metadata={sessionId:'session-a',provider:'pinned-memory-provider',seq:0};
const assembly=content=>({sections:[{name:'memory',interpolate:false,text:'provider guidance\n<summary_snapshot>\n'+content+'\n</summary_snapshot>'},{name:'system-private',text:'PRIVATE_SYSTEM_PROMPT'}]});
test('only the actual bounded memory snapshot crosses the seam',()=>{
 const value=observe(assembly('记住项目约定'),metadata);
 assert.equal(value.content,'记住项目约定');assert.equal(value.seq,0);
 assert.equal(value.content_hash,createHash('sha256').update(value.content).digest('hex'));
 assert.ok(!JSON.stringify(value).includes('PRIVATE_SYSTEM_PROMPT'));
 assert.ok(!value.content.includes('provider guidance'));
});
test('missing provider, session or summary cannot fabricate memory',()=>{
 assert.equal(observe(assembly('text'),{...metadata,provider:''}),null);
 assert.equal(observe(assembly('text'),{...metadata,sessionId:''}),null);
 assert.equal(observe({sections:[{name:'memory',text:'No stored summary'}]},metadata),null);
});
test('ambiguous or interpolated memory is not observed',()=>{
 const value=assembly('text');value.sections.push(value.sections[0]);assert.equal(observe(value,metadata),null);
 value.sections.pop();value.sections[0].interpolate=true;assert.throws(()=>observe(value,metadata),/literal/);
});
test('oversized memory fails closed without truncating its hash',()=>{
 assert.throws(()=>observe(assembly('a'.repeat(16385)),metadata),/budget/);
});
