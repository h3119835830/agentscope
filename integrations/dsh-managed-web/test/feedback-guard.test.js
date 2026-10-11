import test from 'node:test';
import assert from 'node:assert/strict';
import {createFeedbackGuard} from '../lib/feedback-guard.js';
import {createExecutionLane} from '../lib/execution-lane.js';

test('denial cancels queued batch bodies and reaches post processing without deadlock',async()=>{
 const guard=createFeedbackGuard(),lane=createExecutionLane(),signal=AbortSignal.timeout(1000);
 let writes=0;
 const body=async denied=>{
  const ticket=guard.ticket(),release=await lane(signal);
  try{guard.check(ticket);writes++;if(denied)guard.block([{feedback_id:'one'}]);return 'ran';}
  finally{release();}
 };
 const results=await Promise.allSettled([body(true),body(false),body(false)]);
 assert.equal(writes,1);assert.equal(results.filter(r=>r.status==='rejected').length,2);
 // SDK can now complete the batch and admit the post-hook context.
 guard.admit('[ActPlane operation feedback] [{"feedback_id":"one"}]\n指导');
 assert.equal(await body(false),'ran');assert.equal(writes,2);
});

test('persistence, malformed receipts and partial admission cannot open the barrier',()=>{
 const g=createFeedbackGuard();g.block([{feedback_id:'a'},{feedback_id:'b'}]);
 g.admit('persisted');g.admit('[ActPlane operation feedback] invalid');
 assert.throws(()=>g.check(g.ticket()));
 g.admit('[ActPlane operation feedback] [{"feedback_id":"a"}]');
 assert.deepEqual(g.pending(),['b']);assert.throws(()=>g.check(g.ticket()));
 g.admit('[ActPlane operation feedback] [{"feedback_id":"b"}]');g.check(g.ticket());
});
