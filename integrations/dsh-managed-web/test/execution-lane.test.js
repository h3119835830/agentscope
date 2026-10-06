import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createExecutionLane} from '../lib/execution-lane.js';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
test('parallel preflight and post batch completes with serialized bodies',async()=>{
 const acquire=createExecutionLane();let active=0,max=0,finished=0;
 const calls=[1,2,3].map(i=>({i,signal:new AbortController().signal}));
 await Promise.all(calls.map(async()=>({kind:'allow'})));
 await Promise.all(calls.map(async exec=>{const release=await acquire(exec.signal);try{active++;max=Math.max(max,active);await delay(5);finished++;}finally{active--;release();}}));
 await Promise.all(calls.map(async()=>assert.equal(finished,3)));
 assert.equal(max,1);
});
test('cancelling queued call settles before running body finishes',async()=>{
 const acquire=createExecutionLane(),controller=new AbortController();
 const first=await acquire(new AbortController().signal);
 const second=acquire(controller.signal);controller.abort();
 assert.equal(await second,null);first();
 const third=await acquire(new AbortController().signal);assert.equal(typeof third,'function');third();
});
test('failure releases body lane for later calls',async()=>{
 const acquire=createExecutionLane();
 const one=async()=>{const release=await acquire(new AbortController().signal);try{throw Error('body error');}finally{release();}};
 await assert.rejects(one());const release=await acquire(new AbortController().signal);release();
});
