import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {approvalResponse,verifyApprovalReplay} from '../../scripts/policy_preview_approvals.mjs';
const read=path=>JSON.parse(readFileSync(new URL('../../acceptance/'+path,import.meta.url),'utf8'));
const source=read('policy-response-ui-20261026/live-source.json');
const page=read('preview-approval-parity-20261026/live-approvals.json'),cleared=read('preview-approval-parity-20261026/live-cleared-approvals.json'),details=read('preview-approval-parity-20261026/approval-details.json');
const scope='instance-751ad8a6165f4357',url=path=>new URL(path,'http://127.0.0.1');
test('real applied assistant snapshot has an exact-version approval and matching document',()=>{
 assert.equal(verifyApprovalReplay(source.generations,source.items,page,details),1);
});
test('missing or wrong-version approvals fail instead of presenting empty success',()=>{
 assert.throws(()=>verifyApprovalReplay(source.generations,source.items,{records:[]},details),/缺少/);
 const items=structuredClone(source.items);items.find(c=>c.approval_current).approval_revision=999;
 assert.throws(()=>verifyApprovalReplay(source.generations,items,page,details),/缺少/);
});
test('approval lists preserve true applied/invalid and cleared states without write capabilities',()=>{
 const frozen=JSON.stringify([page,cleared,details]);
 const {body}=approvalResponse(url('/api/console/approvals'),scope,page,cleared,details);
 assert.equal(body.records.length,3);assert.equal(body.records.filter(r=>r.status==='applied').length,2);
 assert.ok(body.records.every(r=>r.read_only&&!r.can_apply&&!r.can_approve&&!r.can_clear));
 assert.equal(approvalResponse(url('/api/console/approvals?cleared=true'),scope,page,cleared,details).body.records.length,0);
 assert.equal(JSON.stringify([page,cleared,details]),frozen);
});
test('encoded exact approval details are readable but unknown/other-scope IDs do not leak records',()=>{
 for(const record of page.records){
  const response=approvalResponse(url('/api/console/approvals/'+encodeURIComponent(record.id)),scope,page,cleared,details);
  assert.equal(response.status,200);assert.equal(response.body.id,record.id);assert.equal(response.body.status,record.status);
  assert.equal(approvalResponse(url('/api/console/approvals/'+encodeURIComponent(record.id)),'other-agent',page,cleared,details).status,404);
 }
 assert.equal(approvalResponse(url('/api/console/approvals/missing'),scope,page,cleared,details).status,404);
 assert.equal(approvalResponse(url('/api/console/approvals'),'other-agent',page,cleared,details).body.records.length,0);
 assert.equal(approvalResponse(url('/api/not-replayed'),scope,page,cleared,details),null);
});
