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
test('scenario-only generation delegates bounded context selection to the exact Agent API',async()=>{
 const catalog={catalog:[],items:[],generations:[]},calls=[];
 const render=await harness('TemplatePolicyAssistant.jsx',[catalog,'请根据订单说明保护员工文件',[],'',false,[],false]);
 const props={target:{id:'agent-a',agent_type:'dsh'},scope:'agent',workspaceId:null,api:async()=>catalog,post:async(path,body)=>{calls.push({path,body});return {};},onApprovals(){}};
 await nodes(render(props)).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.ok(calls[0].path.endsWith('/template-configurations/generate'));
 assert.equal(calls[0].path,'/api/agent-instances/agent-a/template-configurations/generate');
 assert.equal(calls[0].body.context_mode,'auto');assert.equal(calls[0].body.scope,'agent');assert.equal(calls[0].body.workspace_id,null);
 assert.equal(calls[0].body.reference_read_id,undefined);assert.equal(calls[0].body.paths,undefined);
 assert.deepEqual(calls[0].body.materials,[]);assert.equal(calls[0].body.files,undefined);assert.equal(calls[0].body.workspace_reference,undefined);
});
test('scenario input has no mandatory manual file or workspace selection',async()=>{
 const catalog={catalog:[],items:[],generations:[]};
 const render=await harness('TemplatePolicyAssistant.jsx',[catalog,'请保护员工文件',[],'',false,[],false]);
 const props={target:{id:'agent-a'},scope:'agent',api:async()=>catalog,post:async()=>assert.fail('unexpected generation'),onApprovals(){}};
 let tree=render(props);assert.equal(nodes(tree).find(n=>n.type==='button'&&n.props['aria-label']==='发送').props.disabled,false);
 assert.equal(nodes(tree).filter(n=>n.type==='textarea').length,1);
 assert.ok(!nodes(tree).some(n=>n.props?.['aria-label']==='选择配置模板'));
 assert.doesNotMatch(renderToStaticMarkup(tree),/手工配置同一模板|按模板生成|补充参考材料/);
 assert.ok(!nodes(tree).some(n=>n.props?.['aria-label']==='参考文件路径'));
 assert.match(renderToStaticMarkup(tree),/无需填写参考文件路径/);
});
test('system scope does not authorize automatic reading of individual Agent workspaces',async()=>{
 const catalog={catalog:[],items:[],generations:[]},calls=[];
 const render=await harness('TemplatePolicyAssistant.jsx',[catalog,'请为所有 Agent 保护配置文件',[],'',false,[],false]);
 const props={target:{id:'system'},scope:'system',api:async()=>catalog,post:async(path,body)=>{calls.push({path,body});return {};},onApprovals(){}};
 await nodes(render(props)).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/policy-template-configurations/generate');
 assert.equal(calls[0].body.context_mode,'none');assert.equal(calls[0].body.scope_id,'system');
});
test('busy analysis prevents duplicate submits and displays ongoing context work',async()=>{
 const catalog={catalog:[],items:[],generations:[]};
 const render=await harness('TemplatePolicyAssistant.jsx',[catalog,'请保护员工文件',[],'',true,[],false]);
 const props={target:{id:'agent-a'},scope:'agent',api:async()=>catalog,post:async()=>assert.fail('unexpected generation'),onApprovals(){}};
 const tree=render(props);assert.ok(nodes(tree).find(n=>n.type==='button'&&n.props['aria-label']==='发送').props.disabled);
 await nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.match(renderToStaticMarkup(tree),/按需读取资料/);
});
test('automatic evidence reports actual sources and denied calls inside progressive disclosure',async()=>{
 const render=await harness('PolicyContextEvidence.jsx');
 const usage={file_count:1,sources:[{workspace:'订单资料',paths:['/w/0/<report>.md']}],activity:[{tool:'list_directory',workspace:'订单资料',status:'completed'},{tool:'read_files',workspace:'订单资料',status:'denied'}]};
 const tree=render({usage}),html=renderToStaticMarkup(tree);
 assert.equal(tree.type,'details');assert.match(html,/本次参考 · 1 个文件/);assert.match(html,/&lt;report&gt;/);
 assert.match(html,/已拒绝/);assert.match(html,/提交和应用前仍会核对/);assert.doesNotMatch(html,/<report>/);
});
test('directory-only analysis never claims that file bodies were read',async()=>{
 const render=await harness('PolicyContextEvidence.jsx');
 const html=renderToStaticMarkup(render({usage:{file_count:0,sources:[],activity:[{tool:'list_directory',workspace:'订单资料',status:'completed'}]}}));
 assert.match(html,/未读取正文/);assert.match(html,/查看目录/);assert.doesNotMatch(html,/已读取/);
});
test('legacy generation evidence remains readable without the new usage contract',async()=>{
 const catalog={catalog:[],items:[],generations:[{request_id:'old',scope:'agent',workspace_id:null,text:'保护员工资料',items:[],questions:[],gaps:[],reference_read:{workspace:'订单资料',paths:['README.md']}}]};
 const render=await harness('TemplatePolicyAssistant.jsx',[catalog,'',[],'',false,[],false]);
 const html=renderToStaticMarkup(render({target:{id:'agent-a'},scope:'agent',api:async()=>catalog,post:async()=>assert.fail('unexpected write'),onApprovals(){}}));
 assert.match(html,/参考资料：订单资料/);assert.match(html,/README.md/);
});
test('project text is escaped and only displayed inside an expandable evidence section',async()=>{
 const value={...receipt,files:[{...receipt.files[0],text:'<script>doSomething()</script>'}]};
 const render=await harness('WorkspaceReferenceInput.jsx',[data,'workspace-a','README.md',value,false,'']);
 const html=renderToStaticMarkup(render(childProps()));assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.ok(nodes(render(childProps())).some(n=>n.type==='details'&&nodes(n).some(v=>v.type==='pre')));
});
