import test from 'node:test';
import assert from 'node:assert/strict';
import {archivePanes,archivePane,policyArchiveRows,archivePolicyLabel,archivePolicyLoading,archiveAuditRow,archivePolicyState,archiveNextVisible} from './archiveRecords.mjs';
test('history exposes explicit strategy and execution audit tabs with legacy pane migration',()=>{
 assert.deepEqual(Object.values(archivePanes),['任务概况','运行前策略','运行时策略','执行审计','结束结果']);
 assert.equal(archivePane('preparation'),'startup');assert.equal(archivePane('execution'),'runtime');assert.equal(archivePane('audit'),'audit');assert.equal(archivePane('invalid'),'startup');
});
test('policy lifecycle groups exact job and preserves the complete parent detail ID',()=>{
 const rows=policyArchiveRows([{id:'s1',job_id:'j1',record_kind:'statement',version:4,targets:['/report.py'],operations:['write'],status:'loaded'}, {id:'runtime:j1',job_id:'j1',record_kind:'job',generation_status:'completed',decision:'expand'}, {id:'s2',job_id:'j1',record_kind:'statement',targets:['/output'],operations:['write'],review_status:'approved'}]);
 assert.equal(rows.length,1);assert.equal(rows[0].id,'runtime:j1');assert.deepEqual(rows[0].targets,['/report.py','/output']);assert.deepEqual(rows[0].operations,['write']);assert.equal(rows[0].version,4);assert.equal(rows[0].review_status,'approved');assert.equal(archivePolicyLoading(rows[0]),'已加载（历史回执）');
});
test('same-version assessments and unlinked versions do not merge with permission changes',()=>{
 const rows=policyArchiveRows([{id:'a',job_id:'expand-job',record_kind:'job',version:4,decision:'expand',loaded:true},{id:'b',job_id:'assessment-job',record_kind:'job',version:4,decision:'no_change'},{id:'c',record_kind:'version',version:4}]);
 assert.equal(rows.length,3);assert.equal(archivePolicyLabel(rows.find(r=>r.id==='b')),'保持当前权限');assert.equal(archivePolicyLoading(rows.find(r=>r.id==='b')),'该次无权限变化');
});
test('OS rows show actual operation result and distinguish probe process domain from ancestor rule domain',()=>{
 const row=archiveAuditRow({id:'19461',operation:'unlink',target:'/workspace/protected.txt',source:'independent_probe',result:'correct_block',pid:991,domain_id:421785620,rule_domain_id:1139067470,rule:'bootstrap-1'});
 assert.equal(row.sourceLabel,'独立验收探针');assert.equal(row.operationLabel,'删除');assert.equal(row.resultLabel,'核验拦截');assert.equal(row.ruleLabel,'bootstrap-1');assert.notEqual(row.domain_id,row.rule_domain_id);assert.equal(row.target,'/workspace/protected.txt');
});
test('missing generation and review receipts stay explicit and pending is not approved',()=>{
 assert.equal(archivePolicyState(undefined),'未记录');assert.equal(archivePolicyState('pending'),'待审核');assert.equal(archivePolicyState('clarify'),'待澄清');assert.equal(archivePolicyState('compiled'),'编译通过');assert.equal(archivePolicyState('not_recorded'),'未记录');
});

test('policy detail reads stored loading receipt without pretending completion alone is loading',()=>{assert.equal(archivePolicyLoading({status:'completed',loading:{loaded:true,active:false}}),'已加载（历史回执）');assert.equal(archivePolicyLoading({status:'completed',loading:{loaded:false}}),'未记录加载回执');});

test('50-row audit batch reveals its last two rows before the next server page',()=>{let shown=12;for(let i=0;i<4;i++)shown=archiveNextVisible(shown,50);assert.equal(shown,50);assert.equal(archiveNextVisible(shown,100),62);});

test('a page containing only statement rows still opens the complete candidate or runtime job',()=>{assert.equal(policyArchiveRows([{id:'runtime:j:statement:0',stage:'runtime',job_id:'j',record_kind:'statement'}])[0].id,'runtime:j');assert.equal(policyArchiveRows([{id:'startup:p:atom:0',stage:'startup',job_id:'j',record_kind:'statement'}])[0].id,'startup:p');});
test('unverified or integrity-failed compilation is never presented as a recorded success',()=>{assert.equal(archivePolicyState('not_verified'),'未核验');assert.equal(archivePolicyState('integrity_failed'),'完整性校验失败');assert.notEqual(archivePolicyState('integrity_failed'),'已记录');});
