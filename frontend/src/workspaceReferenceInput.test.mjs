import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const nodes=t=>!t||typeof t!=='object'?[]:[t,...[t.props?.children].flat(Infinity).flatMap(nodes)];
async function harness(entry,initial=[]){
 const result=await build({entryPoints:[join(base,entry)],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const states=[...initial],refs=[];let i=0,j=0;
 const react={...React,useState:init=>{const key=i++;if(!(key in states))states[key]=typeof init==='function'?init():init;return [states[key],v=>states[key]=typeof v==='function'?v(states[key]):v]},useEffect:()=>{},useRef:init=>refs[j++]||={current:init}};
 const name=join(base,'.workspace-reference-test.cjs'),module=new Module(name);module.paths=Module._nodeModulePaths(base);const original=module.require.bind(module);module.require=id=>id==='react'?react:original(id);module._compile(result.outputFiles[0].text,name);
 return props=>{i=0;j=0;globalThis.document={activeElement:null};return module.exports.default(props);};
}
const data={workspaces:[{id:'workspace-a',name:'订单资料',execution_path:'/w/0'}]};
const receipt={id:'read-a',workspace_name:'订单资料',files:[{relative_path:'README.md',byte_size:120,text:'订单说明'}]};
const childProps=(extra={})=>({targetId:'agent-a',api:async()=>data,post:async()=>receipt,onChange(){},...extra});

test('reference component never reads body or writes on mount',async()=>{
 let calls=0;const render=await harness('WorkspaceReferenceInput.jsx');
 const tree=render(childProps({api:async()=>calls++,post:async()=>calls++}));
 assert.equal(calls,0);assert.ok(nodes(tree).find(n=>n.type==='details'));
 assert.ok(!nodes(tree).some(n=>n.type==='textarea'));
});
test('explicit read uses the exact Agent and relative selection, without generating or applying',async()=>{
 const render=await harness('WorkspaceReferenceInput.jsx',[data,'workspace-a','README.md\ndocs/requirements.md',null,false,'']);const calls=[],changed=[];
 const props=childProps({post:async(path,body)=>{calls.push({path,body});return receipt;},onChange:v=>changed.push(v)});
 let tree=render(props);await nodes(tree).find(n=>n.type==='button'&&n.props.children==='读取参考文件').props.onClick();
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/agent-instances/agent-a/policy-workspace-reads');
 assert.deepEqual(calls[0].body.paths,['README.md','docs/requirements.md']);assert.equal(calls[0].body.workspace_id,'workspace-a');
 assert.deepEqual(changed.at(-1),{pending:false,receipt});
 assert.match(renderToStaticMarkup(render(props)),/已读取 订单资料/);
});
test('editing a selected file clears evidence and requires a fresh read',async()=>{
 const render=await harness('WorkspaceReferenceInput.jsx',[data,'workspace-a','README.md',receipt,false,'']);const changed=[];
 const props=childProps({onChange:v=>changed.push(v)});let tree=render(props);
 nodes(tree).find(n=>n.type==='textarea').props.onChange({target:{value:'other.md'}});
 tree=render(props);assert.deepEqual(changed,[{pending:true,receipt:null}]);
 assert.doesNotMatch(renderToStaticMarkup(tree),/已读取 订单资料/);
});
test('a late body response cannot replace changed file selection',async()=>{
 let resolve;const response=new Promise(r=>resolve=r),changed=[];
 const render=await harness('WorkspaceReferenceInput.jsx',[data,'workspace-a','README.md',null,false,'']);
 const props=childProps({post:()=>response,onChange:v=>changed.push(v)});
 let tree=render(props);const pending=nodes(tree).find(n=>n.type==='button'&&n.props.children==='读取参考文件').props.onClick();
 tree=render(props);nodes(tree).find(n=>n.type==='textarea').props.onChange({target:{value:'other.md'}});
 resolve(receipt);await pending;assert.ok(changed.every(v=>v.receipt===null));
});
test('read failure keeps the pending requirement and does not fall back silently',async()=>{
 const render=await harness('WorkspaceReferenceInput.jsx',[data,'workspace-a','README.md',null,false,'']);const changed=[];
 const props=childProps({post:async()=>{throw Error('读取被当前策略拒绝');},onChange:v=>changed.push(v)});
 const tree=render(props);await nodes(tree).find(n=>n.type==='button'&&n.props.children==='读取参考文件').props.onClick();
 assert.deepEqual(changed,[{pending:true,receipt:null}]);assert.match(renderToStaticMarkup(render(props)),/读取被当前策略拒绝/);
});
test('canceling the reference is an explicit local action without a request',async()=>{
 const render=await harness('WorkspaceReferenceInput.jsx',[data,'workspace-a','README.md',receipt,false,'']);const changed=[];
 const props=childProps({post:async()=>assert.fail('unexpected request'),onChange:v=>changed.push(v)});
 nodes(render(props)).find(n=>n.type==='button'&&n.props.children==='取消参考').props.onClick();
 assert.deepEqual(changed,[{pending:false,receipt:null}]);
});
test('template generation submits only the read receipt, never file bodies or workspace application scope',async()=>{
 const catalog={catalog:[],items:[],generations:[]},calls=[];
 const render=await harness('TemplatePolicyAssistant.jsx',[catalog,'请根据订单说明保护员工文件','','',false,'',[],{pending:false,receipt}]);
 const props={target:{id:'agent-a',agent_type:'dsh'},scope:'agent',workspaceId:null,api:async()=>catalog,post:async(path,body)=>{calls.push({path,body});return {};},onApprovals(){}};
 await nodes(render(props)).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.ok(calls[0].path.endsWith('/template-configurations/generate'));
 assert.equal(calls[0].body.reference_read_id,'read-a');assert.equal(calls[0].body.scope,'agent');assert.equal(calls[0].body.workspace_id,null);
 assert.deepEqual(calls[0].body.materials,[]);assert.equal(calls[0].body.files,undefined);assert.equal(calls[0].body.workspace_reference,undefined);
});
test('pending reference blocks generation through both button and direct form submission',async()=>{
 const catalog={catalog:[],items:[],generations:[]};
 const render=await harness('TemplatePolicyAssistant.jsx',[catalog,'请保护员工文件','','',false,'',[],{pending:true,receipt:null}]);
 const props={target:{id:'agent-a'},scope:'agent',api:async()=>catalog,post:async()=>assert.fail('unexpected generation'),onApprovals(){}};
 let tree=render(props);assert.ok(nodes(tree).find(n=>n.type==='button'&&n.props['aria-label']==='生成策略').props.disabled);
 await nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});assert.match(renderToStaticMarkup(render(props)),/请先读取参考文件/);
});
test('project text is escaped and only displayed inside an expandable evidence section',async()=>{
 const value={...receipt,files:[{...receipt.files[0],text:'<script>doSomething()</script>'}]};
 const render=await harness('WorkspaceReferenceInput.jsx',[data,'workspace-a','README.md',value,false,'']);
 const html=renderToStaticMarkup(render(childProps()));assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.ok(nodes(render(childProps())).some(n=>n.type==='details'&&nodes(n).some(v=>v.type==='pre')));
});
