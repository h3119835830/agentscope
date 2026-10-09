import test from 'node:test';
import assert from 'node:assert/strict';
import {recordTone} from './recordTone.mjs';
test('paused, expired, unknown and unverified records never look successful',()=>{
  for(const label of ['已加载，执行暂停','执行暂停','证据已过期','状态未知','当前未核验','未核验'])assert.equal(recordTone(label),'warn');
});
test('loading and compilation remain distinct from verification',()=>{
  assert.equal(recordTone('已编译'),'info');assert.equal(recordTone('已加载'),'info');assert.equal(recordTone('已核验'),'good');
});
test('guidance and unknown backend labels cannot imply enforced protection',()=>{
  assert.equal(recordTone('行为约定'),'purple');assert.equal(recordTone('future-backend-status'),'neutral');assert.equal(recordTone(null),'neutral');
});
test('task ended is neutral and does not claim task success',()=>{
  assert.equal(recordTone('已结束'),'neutral');assert.equal(recordTone('已完成'),'good');
});
