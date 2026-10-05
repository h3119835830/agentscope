import {test} from 'node:test';
import assert from 'node:assert/strict';
import {candidateState,executionState,proposalSummary,recordsFor,scopeDiff,stageEvidence} from '../frontend/src/scopeView.mjs';
const snapshot=(revision,dirs=[],output=false)=>({id:'s'+revision,revision,confirmed_at:'2026-10-05T10:00:0'+revision+'Z',payload:{allowed_write_dirs:dirs,allow_output:output}});
const fixture=()=>({session:{phase:'running',gate:'open',active_snapshot_id:'s2',message_revision:2,process_epoch:'p1',apply_id:null},
  current:snapshot(2,['backend']),effective:true,snapshots:[snapshot(2,['backend']),snapshot(1,['backend','frontend']),snapshot(0)],
  deltas:[],jobs:[],events:[]});
const candidate=()=>({id:'d',base_snapshot_id:'s2',message_revision:2,process_epoch:'p1',review_status:'pending',
  proposal_hash:'hash',compile_status:'compiled',apply_status:'not_applied',verify_status:'unverified'});
test('candidate approval alone cannot create an expansion stage',()=>{
  const d=fixture();d.deltas=[{...candidate(),review_status:'approved'}];
  assert.equal(stageEvidence(d).find(s=>s.key==='expand').evidence,undefined);
  assert.equal(stageEvidence(d).find(s=>s.key==='restrict').evidence.id,'s2');
});
test('early closure does not invent grant, restriction or expansion',()=>{
  const d=fixture();d.snapshots=[snapshot(0)];d.session.phase='ended';
  assert.deepEqual(stageEvidence(d).map(s=>!!s.evidence),[true,false,false,false,true]);
});
test('output expansion preserves backend-only and protected assets',()=>{
  const diff=scopeDiff(snapshot(2,['backend']).payload,snapshot(3,['backend'],true).payload);
  assert.deepEqual(diff.map(r=>r.resource),['output']);
});
test('approval requires matching scope, message and process with completed analysis',()=>{
  const d=fixture(),c=candidate();d.jobs=[{delta_id:'d',status:'completed'}];assert.ok(candidateState(c,d).ready);
  for(const change of [{base_snapshot_id:'s1'},{message_revision:1},{process_epoch:'old'}])
    assert.equal(candidateState({...c,...change},d).ready,false);
  d.jobs[0].status='failed';assert.equal(candidateState(c,d).ready,false);
});
test('ended or concurrent application cannot offer an approval action',()=>{
  const d=fixture();d.jobs=[{delta_id:'d',status:'completed'}];d.session.apply_id='other';
  assert.equal(candidateState(candidate(),d).ready,false);d.session.apply_id=null;d.session.phase='ended';
  assert.equal(candidateState(candidate(),d).ready,false);
});
test('approved and loaded without verification is not labeled effective',()=>{
  const d=fixture(),c={...candidate(),review_status:'approved',apply_status:'loaded_unverified'};
  assert.equal(candidateState(c,d).label,'核验失败');assert.notEqual(candidateState(c,d).label,'已核验生效');
});
test('rejected restriction still shows a waiting agent',()=>{
  const d=fixture();d.session.phase='waiting_constraint';d.session.gate='waiting_constraint';
  d.deltas=[{...candidate(),review_status:'rejected'}];assert.equal(executionState(d).label,'等待收紧生效');
});
test('lost execution domain, failure or lost connection is never running',()=>{
  const d=fixture();d.effective=false;assert.equal(executionState(d).label,'执行域待确认');
  d.session.gate='failed';assert.equal(executionState(d).label,'执行已暂停');
  assert.equal(executionState(d,true).label,'连接中断');
});
test('logs separate actual approval, rejection, probes and agent claims',()=>{
  const d=fixture();d.events=[{id:1,source:'review',occurred_at:'2026-10-05T11:00:00Z',payload:{decision:'rejected'}},
    {id:2,source:'review',occurred_at:'2026-10-05T11:01:00Z',payload:{decision:'approved'}},
    {id:3,source:'kernel',occurred_at:'2026-10-05T11:02:00Z',payload:{event:{target:'/private-long-path',blocked:true}}},
    {id:4,source:'agent_report',occurred_at:'2026-10-05T11:03:00Z',payload:{summary:'claimed success'}}];
  assert.equal(recordsFor(d).find(r=>r.id==='event-1').result,'已拒绝');
  assert.equal(recordsFor(d).find(r=>r.id==='event-2').result,'已批准');
  assert.equal(recordsFor(d).some(r=>r.id==='event-3'),false);
  assert.equal(recordsFor(d,'agent')[0].result,'Agent 自报');
  assert.equal(recordsFor(d,'kernel')[0].title.includes('/private'),false);
});
test('probe rejections are distinguished by domain and pid; allowed events are excluded',()=>{
  const d=fixture();d.snapshots[0].verification={domain_id:7,probe:{probe_pid:42}};
  d.events=[
    {id:1,source:'kernel',occurred_at:'2026-10-05T11:00:00Z',payload:{event:{blocked:true,domain_id:7,pid:42}}},
    {id:2,source:'kernel',occurred_at:'2026-10-05T11:01:00Z',payload:{event:{blocked:true,domain_id:8,pid:42}}},
    {id:3,source:'kernel',occurred_at:'2026-10-05T11:02:00Z',payload:{event:{blocked:false,domain_id:7,pid:42}}},
  ];
  const rows=recordsFor(d,'kernel');assert.equal(rows.length,2);
  assert.equal(rows.find(r=>r.id==='event-1').title,'拦截核验探针');
  assert.equal(rows.find(r=>r.id==='event-2').title,'拦截执行操作');
});
test('unresolved restriction prevents expansion approval without preventing guidance review',()=>{
  const d=fixture();d.session.phase='waiting_constraint';d.jobs=[{delta_id:'d',status:'completed'}];
  const c={...candidate(),proposal:{proposal:{decision:'expand'}}};
  assert.equal(candidateState(c,d).ready,false);assert.equal(candidateState(c,d).label,'先落实收紧要求');
  c.proposal.proposal.decision='guidance_only';assert.equal(candidateState(c,d).ready,true);
});
test('no_change uses the actual API decision enum and does not claim an agent restart',()=>{
  const c={kind:'expand',proposal:{proposal:{decision:'no_change'}}};
  assert.equal(proposalSummary(c).includes('重启'),false);
  assert.equal(proposalSummary(c).includes('文件权限保持不变'),true);
});
