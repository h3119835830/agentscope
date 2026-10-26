import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {analysisParts,referenceFiles,activitySummary,generationOutcome,responseSentence,compactPolicyText} from './policyAssistantResponse.mjs';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const bundle=await build({entryPoints:[join(base,'PolicyAssistantResponse.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
const filename=join(base,'.compact-response-test.cjs'),loaded=new Module(filename);loaded.paths=Module._nodeModulePaths(base);loaded._compile(bundle.outputFiles[0].text,filename);
const Response=loaded.exports.default;

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
test('response uses a receipt sentence and the shared one-policy-per-row fields',()=>{
 const {result}=JSON.parse(readFileSync(new URL('../../acceptance/policy-investigation-20261026/e3/results/real-locate-file.json',import.meta.url),'utf8'));
 const html=renderToStaticMarkup(React.createElement(Response,{generation:result})),visible=html;
 assert.match(visible,/已读取/);assert.match(visible,/拟定以下 1 项策略/);assert.match(visible,/<table class="policy-record-table"/);
 for(const field of ['策略名称','作用范围','匹配对象','限制操作','触发条件','处置','状态'])assert.ok(visible.includes('<th>'+field+'</th>'));
 assert.doesNotMatch(html,/assistant-response-details|assistant-full-analysis/);
 assert.ok(!html.includes(result.summary));
});
test('eight policies remain eight structured records with accurate draft status',()=>{
 const row={id:'row',name:'项目保护',template:{name:'文件限制',version:2,parameters:[{key:'target',type:'path',label:'路径'}]},parameters:{target:'/w/0/tests/**'},execution:{effective_operations:['write','unlink'],effect:'block'},approval_status:'draft',scope:{label:'指定 Agent'}};
 const generation={items:Array.from({length:8},(_,i)=>({id:'row-'+i})),configuration_snapshots:Array.from({length:8},(_,i)=>({...row,id:'row-'+i,name:'策略 '+(i+1)})),questions:[],gaps:[]};
 const visible=renderToStaticMarkup(React.createElement(Response,{generation}));
 assert.equal((visible.match(/<tr>/g)||[]).length,9);assert.match(visible,/写入、删除/);assert.match(visible,/待提交审批/);assert.doesNotMatch(visible,/已应用|已加载/);
});
test('no-read and failed responses do not invent evidence or a successful generation',()=>{
 const g={items:[],context_usage:{activity:[{tool:'list_directory'}]},generation_state:'failed'};
 assert.match(responseSentence(g),/未读取文件正文/);assert.match(responseSentence(g),/分析未完成/);assert.doesNotMatch(responseSentence(g),/已读取|拟定以下/);
 assert.match(responseSentence({...g,generation_state:'completed',reference_read:{workspace:'旧资料',paths:['README.md']}}),/已读取 README.md/);
});
test('conditional templates do not turn into unconditional bans in compact sentences',()=>{
 const {result}=JSON.parse(readFileSync(new URL('../../acceptance/policy-investigation-20261026/e3/results/real-directory-gate.json',import.meta.url),'utf8'));
 for(const row of result.configuration_snapshots){const text=compactPolicyText(row);assert.match(text,/按模板条件约束/);assert.match(text,/git commit/);assert.match(text,/pytest/);assert.match(text,/退出码 0/);assert.doesNotMatch(text,/禁止执行 git commit|见详情/);}
});
