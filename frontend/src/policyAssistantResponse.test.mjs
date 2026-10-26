import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {analysisParts,referenceFiles,activitySummary,generationOutcome} from './policyAssistantResponse.mjs';

test('compact analysis preserves every character for expansion without inventing an explanation',()=>{
 const original='已读取 README.md，入口为 maintenance.py。'+ '只保护发布清单并保留正常维护。'.repeat(30);
 const {lead,rest}=analysisParts(original);assert.ok(lead.length<=220);assert.equal(lead+rest,original);
 assert.deepEqual(analysisParts(),{lead:'',rest:''});
 assert.deepEqual(analysisParts(null),{lead:'',rest:''});
});
test('only receipted bodies and provided texts count as files, deduplicated by workspace',()=>{
 assert.deepEqual(referenceFiles({activity:[{tool:'list_directory'},{tool:'search_project'},{tool:'draft_file_change'}]}),[]);
 assert.deepEqual(referenceFiles(null),[]);
 const files=referenceFiles({sources:[{workspace:'A',paths:['/w/0/README.md','/w/0/README.md']},{workspace:'B',paths:['/w/0/README.md']}],provided_files:[{name:'notes.md'},{name:'notes.md'}]});
 assert.equal(files.length,3);assert.equal(files[2].kind,'provided');
});
test('drafts, resource checks and failed previews never masquerade as file reads',()=>{
 for(const tool of ['draft_file_change','search_policy_templates','search_project','inspect_resource','preview_policy_matches','unknown_tool'])assert.notEqual(activitySummary({tool,status:'completed'}).status,'已读取');
 assert.deepEqual(activitySummary({tool:'preview_policy_matches',status:'completed',coverage_checks_passed:false}),{label:'验证策略匹配',status:'样本未通过',location:''});
 assert.equal(activitySummary({tool:'inspect_resource',status:'rejected'}).status,'未完成');
 assert.equal(activitySummary({tool:'read_files',status:'unavailable'}).status,'暂不可用');
});
test('one and multiple policies remain the real model result, not a display cap',()=>{
 for(const [file,count] of [['real-locate-file',1],['real-directory-gate',2]]){
  const {result}=JSON.parse(readFileSync(new URL('../../acceptance/policy-investigation-20261026/e3/results/'+file+'.json',import.meta.url),'utf8'));
  assert.equal(result.items.length,count);assert.match(generationOutcome(result),new RegExp(count+' 项'));
  assert.ok(referenceFiles(result.context_usage).length>0);
 }
});
