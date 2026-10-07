import test from 'node:test';
import assert from 'node:assert/strict';
import {archivePanes,archivePane,policyArchiveRows,archivePolicyLabel,archivePolicyText,statementDslEvidence,archiveJobDecision,archivePolicyLoading,archiveAuditRow,archivePolicyState,archiveNextVisible} from './archiveRecords.mjs';
test('history exposes explicit strategy and execution audit tabs with legacy pane migration',()=>{
 assert.deepEqual(Object.values(archivePanes),['运行前策略','运行时策略','执行监控','执行审计','任务概况','结束结果']);
 assert.equal(archivePane('preparation'),'startup');assert.equal(archivePane('execution'),'runtime');assert.equal(archivePane('audit'),'audit');assert.equal(archivePane('invalid'),'startup');
});
test('each statement keeps its exact child ID and text even within the same generation job',()=>{
 const input=[{id:'runtime:j1:statement:0',job_id:'j1',record_kind:'statement',statement:'保留 frontend/report.py',change_status:'retained',decision:'expand'}, {id:'runtime:j1:statement:1',job_id:'j1',record_kind:'statement',statement:'允许输出结果',change_status:'permission_changed',decision:'expand'}];
 const rows=policyArchiveRows([...input,input[0]]);assert.equal(rows.length,2);assert.deepEqual(new Set(rows.map(r=>r.id)),new Set(input.map(r=>r.id)));assert.equal(archivePolicyText(rows.find(r=>r.id===input[0].id)),'保留 frontend/report.py');assert.equal(archivePolicyLabel(input[0]),'保留规则');assert.equal(archivePolicyLabel(input[1]),'权限变化');assert.equal(archiveJobDecision(input[0]),'扩权');
});
test('failed and statement-less jobs remain honest placeholders without fabricated policy text',()=>{
 assert.equal(archivePolicyText({record_kind:'job',generation_status:'failed',statement:'运行时策略评估'}),'生成失败，查看已保存记录');assert.equal(archivePolicyText({record_kind:'job',generation_status:'completed',statement:'运行时策略评估'}),'本次未记录策略语句');
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

test('unverified or integrity-failed compilation is never presented as a recorded success',()=>{assert.equal(archivePolicyState('not_verified'),'未核验');assert.equal(archivePolicyState('integrity_failed'),'完整性校验失败');assert.notEqual(archivePolicyState('integrity_failed'),'已记录');});

test('whole candidate DSL cannot masquerade as a statement mapping',()=>{
 const bundle='rule inherited-protect { deny write /inherited }';const view=statementDslEvidence({record_kind:'statement',compilation:{scope:'candidate_bundle',dsl:bundle}});assert.equal(view.dsl,'');assert.equal(view.bundleDsl,bundle);assert.equal(statementDslEvidence({compilation:{dsl:bundle}}).dsl,'');
});
test('a retained clause under a no-change job still shows its own exact DSL',()=>{
 const record={record_kind:'statement',decision:'no_change',change_status:'retained',compilation:{scope:'statement',dsl:'rule keep-frontend'},loading:{loaded:true}};assert.equal(statementDslEvidence(record).dsl,'rule keep-frontend');assert.equal(statementDslEvidence(record).guidance,false);assert.equal(archivePolicyLoading(record),'历史沿用规则');
});
test('semantic guidance never exports OS DSL and integrity failure cannot show a claimed mapping',()=>{
 const guidance={record_kind:'statement',decision:'expand',policy_type:'semantic_only',compilation:{scope:'statement',dsl:'must-not-export'}};assert.equal(statementDslEvidence(guidance).dsl,'');assert.equal(statementDslEvidence(guidance).guidance,true);assert.equal(archivePolicyLoading(guidance),'不生成 OS 规则');assert.equal(statementDslEvidence({compilation:{scope:'statement',status:'integrity_failed',dsl:'must-not-export'}}).dsl,'');
});
test('expansion displays recorded permission delta without inventing a removed deny clause',()=>{
 const record={record_kind:'statement',change_status:'permission_changed',dsl_diff:{status:'not_recorded',before:'',after:'',removed_clauses:[]},permission_delta:{allow_output_before:false,allow_output_after:true,target:'/output'}};const view=statementDslEvidence(record);assert.equal(view.diff,null);assert.equal(view.dsl,'');assert.equal(view.permission.allow_output_before,false);assert.equal(view.permission.allow_output_after,true);
 const removed=statementDslEvidence({change_status:'removed',dsl_diff:{status:'recorded',before:'deny write /output',after:''}});assert.equal(removed.diff.before,'deny write /output');assert.equal(removed.diff.after,'');
});
