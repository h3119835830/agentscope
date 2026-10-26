import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const base=dirname(fileURLToPath(import.meta.url)),require=createRequire(import.meta.url),Module=require('node:module');
const built=await build({entryPoints:[join(base,'RuntimePolicies.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
const module=new Module(join(base,'.runtime-policies-test.cjs'));module.paths=Module._nodeModulePaths(base);module._compile(built.outputFiles[0].text,join(base,'.runtime-policies-test.cjs'));
const {default:RuntimePolicies,generatedRuntimePolicies,runtimePolicyName,runtimePolicyTrigger,runtimePolicyAction}=module.exports;
const policy={id:'runtime:real-job:statement:0',stage:'runtime',effect:'restrict',default_action:'block',policy_type:'per_event',statement:'禁止修改文件',targets:['/workspace/memory-note.txt'],trigger:{actor:'native_user',job_id:'private-job-marker'},compile_status:'compiled'};
test('ordinary guidance, no-change assessments and startup records do not become runtime policies',()=>{
 assert.deepEqual(generatedRuntimePolicies([policy,{...policy,id:'guidance',effect:'guidance',policy_type:'semantic_only'},{...policy,id:'assessment',effect:'no_change'},{...policy,id:'startup',stage:'startup'}]),[policy]);
});
test('the default table has name, trigger and an explicit details action, with internal evidence absent',()=>{
 const html=renderToStaticMarkup(React.createElement(RuntimePolicies,{task:'exact-task',records:[policy],workspace:'/workspace',api:()=>{throw Error('render must not fetch')}}));
 assert.equal((html.match(/<th scope=/g)||[]).length,4);assert.match(html,/默认动作/);assert.match(html,/阻断/);assert.match(html,/策略名称/);assert.match(html,/由谁触发/);assert.match(html,/保护 memory-note.txt/);assert.match(html,/用户消息/);assert.match(html,/aria-label="操作"/);assert.match(html,/>详情<\/button>/);
 assert.doesNotMatch(html,/private-job-marker|核验|Hook|PID|参考模板|查看 DSL|禁止修改文件/);assert.match(html,/aria-expanded="false"/);
});
test('names use a saved name when available and never replace a trigger with the presence of memory',()=>{
 assert.equal(runtimePolicyName({...policy,name:'保护验收记录'},'/workspace'),'保护验收记录');
 assert.equal(runtimePolicyTrigger({...policy,trigger:{actor:'native_user',observations:[{category:'persistent_memory'}]}}),'用户消息');
 assert.equal(runtimePolicyTrigger({...policy,trigger:{actor:'persistent_memory'}}),'跨会话记忆');
 assert.equal(runtimePolicyTrigger({...policy,trigger:{}}),'未记录来源');
 assert.equal(runtimePolicyAction({effect:'restrict'}),'未记录');
 assert.equal(runtimePolicyAction({default_action:'kill'}),'终止');
});
