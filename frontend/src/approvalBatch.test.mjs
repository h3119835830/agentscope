import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareApprovalBatch,executeApprovalBatch,approvalNeedsAttention,batchActionFor} from './approvalBatch.mjs';
const row=(id,scope=id,status='pending')=>({id,name:'策略 '+id,kind:'dsl',scope_id:scope,scope_type:scope==='system'?'system':'agent',target:{scope:'agent',id:scope},candidate_hash:'candidate-'+id,baseline:{revision:1},status,can_approve:status==='pending',can_apply:status==='approved',...(status==='approved'?{approval_hash:'approved-'+id}:{})});
const url=id=>'/api/console/approvals/'+encodeURIComponent(id);

test('attention categories and batch actions preserve approve/apply separation',()=>{
 for(const s of ['stale','invalid','failed','blocked'])assert.ok(approvalNeedsAttention(s));
 for(const s of ['pending','approved','applied','rejected'])assert.ok(!approvalNeedsAttention(s));
 assert.equal(batchActionFor('pending'),'approve');assert.equal(batchActionFor('approved'),'apply');assert.equal(batchActionFor('attention'),'revalidate');assert.equal(batchActionFor('processed'),undefined);
});
test('preparing a batch reads exact selected records without mutations',async()=>{
 const records=[row('a:b'),row('two')],reads=[];
 const batch=await prepareApprovalBatch([...records,records[0]],'approve',async path=>{reads.push(path);return records.find(r=>url(r.id)===path);});
 assert.deepEqual(reads,[url('a:b'),url('two')]);assert.equal(batch.entries.length,2);assert.ok(batch.entries.every(e=>e.requestKey));
});
test('bulk approve uses individual frozen hashes and never applies',async()=>{
 const records=[row('one'),row('two')],calls=[],current=new Map(records.map(r=>[r.id,r]));
 const api=async path=>[...current.values()].find(r=>url(r.id)===path);
 const batch=await prepareApprovalBatch(records,'approve',api);
 const result=await executeApprovalBatch(batch,api,async(path,body)=>{calls.push({path,body});const id=records.find(r=>path===url(r.id)+'/approve').id;current.set(id,{...current.get(id),status:'approved',can_approve:false,can_apply:true});return {state:'approved'};});
 assert.equal(result.length,2);assert.ok(result.every(r=>r.outcome==='success'&&r.status==='approved'));
 assert.ok(calls.every(c=>c.path.endsWith('/approve')&&!('approval_hash' in c.body)));
 assert.deepEqual(calls.map(c=>c.body.proposal_hash),records.map(r=>r.candidate_hash));assert.notEqual(calls[0].body.request_key,calls[1].body.request_key);
});
test('two proposals for one scope are all excluded instead of choosing authority implicitly',async()=>{
 const records=[row('one','shared'),row('two','shared'),row('three','other')];const api=async path=>records.find(r=>url(r.id)===path);
 const batch=await prepareApprovalBatch(records,'approve',api),calls=[];
 assert.ok(batch.entries.slice(0,2).every(e=>e.error.includes('同一范围')));assert.ok(!batch.entries[2].error);
 await executeApprovalBatch(batch,api,async path=>calls.push(path));assert.deepEqual(calls,[url('three')+'/approve']);
});

test('distinct policy records in the same scope can be approved independently',async()=>{
 const records=[{...row('one','shared'),approval_unit:{configuration_id:'policy-one'}},{...row('two','shared'),approval_unit:{configuration_id:'policy-two'}}];
 const api=async path=>records.find(r=>url(r.id)===path),calls=[];
 const batch=await prepareApprovalBatch(records,'approve',api);
 assert.ok(batch.entries.every(entry=>!entry.error));
 await executeApprovalBatch(batch,api,async path=>calls.push(path));
 assert.deepEqual(calls,[url('one')+'/approve',url('two')+'/approve']);
});
test('bulk apply requires the existing approval receipt and submits only apply calls',async()=>{
 const r=row('one','agent-a','approved'),calls=[];let applied=false;
 const api=async()=>applied?{...r,status:'applied'}:r;
 const batch=await prepareApprovalBatch([r],'apply',api);
 const result=await executeApprovalBatch(batch,api,async(path,body)=>{calls.push({path,body});applied=true;return {state:'applied'};});
 assert.deepEqual(calls,[{path:url(r.id)+'/apply',body:{proposal_hash:r.candidate_hash,approval_hash:r.approval_hash,request_key:batch.entries[0].requestKey}}]);
 assert.equal(result[0].status,'applied');
});
test('changes after review prevent submission without refreshing the approved content',async()=>{
 for(const changes of [{candidate_hash:'new'},{baseline:{revision:2}},{target:{scope:'agent',id:'other'}},{approval_hash:'other-receipt'},{scope_id:'other'}]){
  const r=row('one','agent-a','approved'),batch=await prepareApprovalBatch([r],'apply',async()=>r),calls=[];
  const result=await executeApprovalBatch(batch,async()=>({...r,...changes}),async()=>calls.push('write'));
  assert.equal(result[0].outcome,'failed');assert.equal(calls.length,0);
 }
});
test('partial failures are retained and every independent record is still processed',async()=>{
 const records=[row('one'),row('two')],order=[];let inFlight=0;const api=async path=>records.find(r=>url(r.id)===path);
 const batch=await prepareApprovalBatch(records,'approve',api);
 const result=await executeApprovalBatch(batch,api,async path=>{assert.equal(inFlight,0);inFlight++;order.push(path);try{if(path.includes('/one/'))throw Error('已有待应用变更');return {state:'approved'};}finally{inFlight--;}});
 assert.deepEqual(result.map(r=>r.outcome),['failed','success']);assert.match(result[0].message,/已有待应用/);assert.equal(order.length,2);
});

test('approval has bounded concurrency, immediate progress and no redundant receipt readback',async()=>{
 const records=Array.from({length:11},(_,i)=>({...row(String(i),'shared'),approval_unit:{configuration_id:'policy-'+i}}));
 const reads=[],pending=[],progress=[];let active=0,maxActive=0;
 const api=async path=>{reads.push(path);return records.find(r=>url(r.id)===path);};
 const batch=await prepareApprovalBatch(records,'approve',api);reads.length=0;
 const run=executeApprovalBatch(batch,api,async path=>{
  const id=records.find(r=>path===url(r.id)+'/approve').id;
  active++;maxActive=Math.max(maxActive,active);
  await new Promise(resolve=>pending.push(resolve));active--;
  return {id,state:'approved',approval_hash:'receipt-'+id};
 },values=>progress.push(values.map(v=>v.outcome)));
 // Resolve blocked requests in waves; this tests concurrency without timers.
 for(let completed=0;completed<11;){
  await new Promise(resolve=>setImmediate(resolve));
  const wave=pending.splice(0);assert.ok(wave.length>0);completed+=wave.length;wave.forEach(resolve=>resolve());
 }
 const results=await run;
 assert.equal(maxActive,3);assert.equal(reads.length,11);
 assert.deepEqual(results.map(r=>r.id),records.map(r=>r.id));
 assert.ok(results.every(r=>r.status==='approved'&&r.outcome==='success'));
 assert.ok(progress[0].includes('processing'));
});

test('application remains sequential even for distinct policies',async()=>{
 const records=[row('one','shared','approved'),row('two','shared','approved')];let active=0,maxActive=0;
 const api=async path=>records.find(r=>url(r.id)===path),batch=await prepareApprovalBatch(records,'apply',api);
 await executeApprovalBatch(batch,api,async()=>{active++;maxActive=Math.max(maxActive,active);await new Promise(resolve=>setImmediate(resolve));active--;return {state:'applied'};});
 assert.equal(maxActive,1);
});
test('unsupported attention records are skipped and supported records bind the reviewed plan',async()=>{
 const supported={...row('one'),status:'stale',can_approve:false,revalidation:{available:true}},blocked={...row('two'),status:'blocked',can_approve:false,revalidation:{available:false,reason:'请返回所属配置重新生成'}};
 const plan={source_id:supported.id,plan_hash:'plan-hash',comparisons:[]},calls=[];
 const api=async path=>path.endsWith('/revalidation')?plan:path===url(blocked.id)?blocked:path===url('new')?{status:'pending'}:supported;
 const batch=await prepareApprovalBatch([supported,blocked],'revalidate',api);
 const result=await executeApprovalBatch(batch,api,async(path,body)=>{calls.push({path,body});return {id:'new'};});
 assert.deepEqual(calls,[{path:url('one')+'/revalidate',body:{plan_hash:'plan-hash',request_key:batch.entries[0].requestKey}}]);assert.equal(result[0].resultId,'new');assert.equal(result[1].outcome,'skipped');
});
test('a successful request with missing readback is not reported as a completed application',async()=>{
 const r=row('one','agent-a','approved');let reads=0;
 const api=async()=>{if(++reads>2)throw Error('unavailable');return r;};
 const batch=await prepareApprovalBatch([r],'apply',api),result=await executeApprovalBatch(batch,api,async()=>({state:'applied'}));
 assert.equal(result[0].outcome,'unverified');assert.match(result[0].message,/暂未读回/);
});
test('revalidation previews cannot silently switch to another record',async()=>{
 const r={...row('one'),status:'stale',revalidation:{available:true}};
 const batch=await prepareApprovalBatch([r],'revalidate',async path=>path.endsWith('/revalidation')?{source_id:'different'}:r);
 assert.match(batch.entries[0].error,/不一致/);
});
test('cleanup and restore use visibility hashes and never call approval or execution endpoints',async()=>{
 let current={...row('one','agent-a','rejected'),can_clear:true,can_restore:false,cleared:false,clearance_hash:'visibility-0'};const calls=[];
 const api=async()=>current;
 const clearing=await prepareApprovalBatch([current],'clear',api);
 const cleared=await executeApprovalBatch(clearing,api,async(path,body)=>{calls.push({path,body});current={...current,cleared:true,can_restore:true,clearance_hash:'visibility-1'};return current;});
 assert.equal(cleared[0].cleared,true);assert.deepEqual(calls[0],{path:url('one')+'/clear',body:{expected_hash:'visibility-0',request_key:clearing.entries[0].requestKey}});
 const restoring=await prepareApprovalBatch([current],'restore',api);
 const restored=await executeApprovalBatch(restoring,api,async(path,body)=>{calls.push({path,body});current={...current,cleared:false,can_restore:false,clearance_hash:'visibility-2'};return current;});
 assert.equal(restored[0].cleared,false);assert.equal(calls[1].path,url('one')+'/restore');assert.equal(calls[1].body.expected_hash,'visibility-1');
 assert.ok(calls.every(c=>!('proposal_hash' in c.body)&&!c.path.endsWith('/apply')&&!c.path.endsWith('/reject')));
});
test('cleanup excludes actionable records and does not impose approval owner selection rules',async()=>{
 const records=[{...row('one','shared','rejected'),can_clear:true,clearance_hash:'v1'},
  {...row('two','shared','applied'),can_clear:true,clearance_hash:'v2'},
  {...row('pending','shared','pending'),can_clear:false},
  {...row('approved','shared','approved'),can_clear:false},
  {...row('applying','shared','applying'),can_clear:false}];
 const api=async path=>records.find(r=>url(r.id)===path),batch=await prepareApprovalBatch(records,'clear',api),calls=[];
 assert.ok(batch.entries.slice(0,2).every(e=>!e.error));assert.ok(batch.entries.slice(2).every(e=>e.error));
 await executeApprovalBatch(batch,api,async path=>calls.push(path));assert.deepEqual(calls,[url('one')+'/clear',url('two')+'/clear']);
});
test('changed cleanup visibility revision invalidates the old preview without issuing a write',async()=>{
 const r={...row('one','agent-a','rejected'),can_clear:true,clearance_hash:'before'};
 const batch=await prepareApprovalBatch([r],'clear',async()=>r),calls=[];
 const result=await executeApprovalBatch(batch,async()=>({...r,clearance_hash:'after'}),async()=>calls.push('write'));
 assert.equal(result[0].outcome,'failed');assert.equal(calls.length,0);
});
