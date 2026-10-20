import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const target={id:'agent-one',agent_type:'dsh',mode:'controlled',status:'stopped'};
const nodes=t=>!t||typeof t!=='object'?[]:[t,...[t.props?.children].flat(Infinity).flatMap(nodes)];
async function harness(entry,initial=[]){
 const result=await build({entryPoints:[join(base,entry)],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const states=[...initial],refs=[];let i=0,j=0;
 const react={...React,useState:init=>{const key=i++;if(!(key in states))states[key]=typeof init==='function'?init():init;return [states[key],v=>states[key]=typeof v==='function'?v(states[key]):v]},useEffect:()=>{},useRef:init=>refs[j++]||={current:init}};
 const name=join(base,'.unified-scope-test.cjs'),module=new Module(name);module.paths=Module._nodeModulePaths(base);const original=module.require.bind(module);module.require=id=>id==='react'?react:original(id);module._compile(result.outputFiles[0].text,name);
 return props=>{i=0;j=0;globalThis.document={activeElement:null};return module.exports.default(props);};
}
const props=(navigation={},navigate=()=>{})=>({api:async()=>({}),post:async()=>{throw Error('unexpected write')},navigation:{policyAgent:target.id,policyScope:'agent',...navigation},navigate});

test('changing to all Agents clears workspace provenance and never posts a policy',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[target],'',0,null]),changes=[];
 const tree=render(props({policyWorkspace:'old-workspace'},p=>changes.push(p)));
 const scope=nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='策略作用范围');
 scope.props.onChange({target:{value:'system'}});
 assert.deepEqual(changes,[{policyScope:'system',policyWorkspace:'',policySession:'',agentPolicyTab:'assistant'}]);
 const assistant=nodes(tree).find(n=>n.type?.name==='TemplatePolicyAssistant');
 assert.equal(assistant.props.scope,'agent');assert.equal(assistant.props.workspaceId,null);assert.equal(assistant.props.referenceWorkspaceId,null);
});
test('all-Agent scope works without a selected or connected Agent and uses the existing system contract',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[],'',0,null]);
 const tree=render(props({policyScope:'system',policyAgent:''}));
 const assistant=nodes(tree).find(n=>n.type?.name==='TemplatePolicyAssistant');
 assert.equal(assistant.props.scope,'system');assert.equal(assistant.props.target.id,'system');
 assert.ok(!nodes(tree).some(n=>n.type==='select'&&n.props['aria-label']==='策略目标 Agent'));
});
test('legacy workspace links cannot mount the generator or promote their candidates',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[target],'',0,null]);
 const tree=render(props({policyScope:'workspace',policyWorkspace:'workspace-one'}));
 const legacy=nodes(tree).find(n=>n.type?.name==='LegacyWorkspacePolicies');
 assert.equal(legacy.props.targetId,'agent-one');assert.equal(legacy.props.workspaceId,'workspace-one');
 assert.ok(!nodes(tree).some(n=>['TemplatePolicyAssistant','ActPlanePolicies'].includes(n.type?.name)));
 assert.ok(!('post' in legacy.props));
});
test('switching exact Agent identity clears workspace context without deriving a target from its name',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[target,{...target,id:'agent-two'}],'',0,null]),changes=[];
 const tree=render(props({},p=>changes.push(p)));
 nodes(tree).find(n=>n.type==='select'&&n.props['aria-label']==='策略目标 Agent').props.onChange({target:{value:'agent-two'}});
 assert.deepEqual(changes,[{policyAgent:'agent-two',policyWorkspace:'',policySession:'',policyScope:'agent'}]);
});
test('legacy Agent configuration links return to the preflight assistant',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[target],'',0,null]);
 const tree=render(props({agentPolicyTab:'policies'}));
 assert.ok(nodes(tree).some(n=>n.type?.name==='TemplatePolicyAssistant'));
 assert.ok(!nodes(tree).some(n=>n.type?.name==='ActPlanePolicies'));
});
test('legacy records expose only original approval navigation and explicit fresh configuration',async()=>{
 const render=await harness('LegacyWorkspacePolicies.jsx',[{configs:[{id:'c',name:'原工作区限制',approval_id:'approval-old'}],drafts:[]},'',0]),opened=[];
 const tree=render({targetId:'agent-one',workspaceId:'workspace-one',api:async()=>({}),onApprovals:id=>opened.push(id),onCreate(){}});
 assert.ok(!nodes(tree).some(n=>n.type==='form'));
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='查看原审批').props.onClick();
 assert.deepEqual(opened,['approval-old']);
});
test('legacy workspace tab links return to automatic preflight context selection',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[target],'',0,null]);
 const tree=render(props({agentPolicyTab:'workspaces'}));
 const assistant=nodes(tree).find(n=>n.type?.name==='TemplatePolicyAssistant');
 assert.equal(assistant.props.referenceWorkspaceId,null);
 assert.ok(!nodes(tree).some(n=>n.type?.name==='NativeAgentWorkspaces'));
});
test('Agent policy tabs retain only generation runtime and verified load facts',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[target],'',0,null]);
 const tree=render(props({agentPolicyTab:'assistant'})),labels=nodes(tree).filter(n=>n.props?.role==='tab').map(n=>n.props.children);
 assert.deepEqual(labels,['运行前策略助手','运行时策略','当前加载记录']);
 assert.ok(!nodes(tree).some(n=>['PolicyReferenceWorkspaceSelect','ActPlanePolicies','NativeAgentWorkspaces'].includes(n.type?.name)));
});
test('Agent page sends configuration management to the System module with the exact target',async()=>{
 const render=await harness('AgentPolicyWorkbench.jsx',[[target],'',0,null]),changes=[];
 const tree=render(props({},patch=>changes.push(patch)));
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='管理策略配置 ↗').props.onClick();
 assert.deepEqual(changes,[{page:'strategies',systemTab:'policies',policyAgent:target.id}]);
});
test('runtime Hook list keeps source semantics without exposing raw session identities',async()=>{
 const events=[{seq:9,kind:'tool_start',generation:'generation-a',tool:'read_file',session_id:'private-session-uuid',created_at:'2026-10-20T00:00:00Z'}];
 const render=await harness('AgentRuntimePolicyAssistant.jsx',[events,'',0]);
 const html=renderToStaticMarkup(render({target:{...target,connected:true,generation:'generation-a',gate:'open'},api:async()=>({}),post:async()=>{},onApprovals(){}}));
 assert.match(html,/来自一个 Agent 会话（仅作来源）/);assert.doesNotMatch(html,/private-session-uuid/);
 assert.match(html,/等待自动评估器/);assert.match(html,/尚未接通/);
 assert.doesNotMatch(html,/作为生成依据|可人工触发 Pi|运行时策略助手对话/);
});
test('saved generation without a current connection never claims that runtime Hook is connected',async()=>{
 const render=await harness('AgentRuntimePolicyAssistant.jsx',[[],'',0]);
 const html=renderToStaticMarkup(render({target:{...target,connected:false,generation:'generation-a',gate:'open'},api:async()=>({})}));
 assert.match(html,/当前未运行/);assert.doesNotMatch(html,/运行时 Hook<!-- -->已接入/);
});
