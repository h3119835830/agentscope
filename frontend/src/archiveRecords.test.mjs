import assert from 'node:assert/strict';
import test from 'node:test';
import {readableConstraints,recordRow,recordScalar,visibleArchiveRecords,permissionHighlights} from './archiveRecords.mjs';

test('legacy JSON constraints translate duplicate requirements without losing either authority',()=>{
 const text='Honor task requirements to preserve tests. Do not weaken platform boundaries.';
 const input={declared_constraints:[],execution_constraints:text,platform_constraints:text};
 const before=JSON.stringify(input),rows=readableConstraints(JSON.stringify(input));
 assert.equal(rows.length,2);
 assert.equal(rows[0].requirement,'遵守任务要求，保留现有测试。');
 assert.deepEqual(rows[0].sources,['执行要求','平台要求']);
 assert.equal(rows[0].original,'Honor task requirements to preserve tests.');
 assert.equal(JSON.stringify(input),before);
});
test('declared constraints preserve original requirements and exact protected targets',()=>{
 const rows=readableConstraints({declared_constraints:[{source_quote:'Do not modify custom tests.',targets:['/task/test.special.py']}],platform_constraints:'Unknown policy wording stays unchanged.'});
 assert.equal(rows[0].requirement,'Do not modify custom tests.');
 assert.deepEqual(rows[0].targets,['/task/test.special.py']);
 assert.equal(rows[1].requirement,'Unknown policy wording stays unchanged.');
 assert.deepEqual(readableConstraints(null),[]);
});
test('an operation probe exposes its classification rather than treating recorded as proof of success',()=>{
 const row=recordRow({id:'p1',kind:'operation_verified',status:'recorded',action_source:'independent_probe',detail:{classification:'correct_block',probe:{operation:'unlink',target:'/work/tests/test.py',pid:0},effect_verified:false}});
 assert.equal(row.kind,'操作效果核验');assert.equal(row.status,'核验拦截');assert.equal(row.source,'独立验收探针');assert.equal(row.operation,'删除');assert.equal(row.pid,0);assert.equal(row.target,'/work/tests/test.py');
 assert.equal(recordScalar('effect_verified',false),'否');
});
test('stored event provenance never invents an executor and archived loading remains historical',()=>{
 const row=recordRow({id:'a',kind:'policy_active',status:'loaded',source:'managed_events',detail:{}});
 assert.equal(row.source,'来源未记录');assert.equal(row.status,'历史已加载');
 assert.equal(recordScalar('errno',0),'0');assert.equal(recordScalar('status','active'),'历史已加载');
});
test('search includes operation targets and deduplicates stable event IDs in reverse chronological order',()=>{
 const older={id:'old',kind:'operation_verified',time:'2026-10-07T10:00:00Z',detail:{classification:'correct_block',operation:'write',target:'/work/tests/test.py'}},newer={...older,id:'new',time:'2026-10-07T11:00:00Z'};
 assert.deepEqual(visibleArchiveRecords([older,newer,older],{query:'test.py',status:'good'}).map(r=>r.id),['new','old']);
 assert.deepEqual(visibleArchiveRecords([older],{status:'bad'}),[]);
 assert.equal(visibleArchiveRecords([{id:'pi',kind:'pi_read'}],{query:'文件读取'}).length,1);
});
test('critical receipts remain available beyond a busy first page and never infer an event from a version',()=>{
 const early={id:'load-v4',kind:'policy_active',version:4,time:'2026-10-07T09:00:00Z'},data={events:[{id:'latest-probe',kind:'operation_verified'}],stage_previews:{execution:{events:[],highlights:[early],highlight_total:21,highlight_limit:20}}};
 const summary=permissionHighlights(data,'execution');assert.deepEqual(summary.events,[early]);assert.equal(summary.total,21);assert.equal(summary.limit,20);
 assert.deepEqual(permissionHighlights({stage_previews:{execution:[]}},'execution').events,[]);
});
test('nested no-change and guidance decisions stay assessments rather than permission changes',()=>{
 for(const decision of ['no_change','guidance_only']){
  const event={id:decision,kind:'candidate',version:4,detail:{proposal:{decision}}};
  assert.equal(recordRow(event).kind,'策略评估');
  assert.equal(recordRow(event).summary.startsWith('策略评估：'),true);
  assert.deepEqual(permissionHighlights({stage_previews:{execution:{highlights:[event]}}},'execution').events,[]);
 }
});
