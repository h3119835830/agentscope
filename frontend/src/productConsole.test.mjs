import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {productReadUrl,unknownAgentSummary} from './productConsole.mjs';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
async function render(file,props,states=[]){
 const built=await build({entryPoints:[join(base,file)],bundle:true,platform:'node',format:'cjs',external:['react','react-dom'],loader:{'.css':'empty'},write:false});
 globalThis.document={body:{}};let index=0;const hooks={...React,useState:initial=>[index in states?states[index++]:((index++,typeof initial==='function'?initial():initial)),()=>{}]};
 const filename=join(base,'.product-test.cjs'),module=new Module(filename);module.paths=Module._nodeModulePaths(base);const original=module.require.bind(module);module.require=id=>id==='react'?hooks:id==='react-dom'?{...original(id),createPortal:()=>null}:original(id);module._compile(built.outputFiles[0].text,filename);
 return renderToStaticMarkup(React.createElement(module.exports.default,props));
}
test('product reads use retained projections while writes and original DSL paths preserve contracts',()=>{
 for(const [input,output] of [['/api/agent-instances/a/sessions/s/kernel-events?before=4','/api/console/agents/a/sessions/s/kernel-events?before=4'],['/api/sessions?workspace=%2Fa','/api/console/sessions?workspace=%2Fa'],['/api/task-archives?page=2','/api/console/task-archives?page=2'],['/api/history/records?offset=20','/api/console/history/records?offset=20']])assert.equal(productReadUrl(input),output);
 assert.equal(productReadUrl('/api/security/system/dsl'),'/api/console/security/system/dsl');
 for(const path of ['/api/history/records/id','/api/history/generations/id'])assert.equal(productReadUrl(path),path);
 assert.equal(productReadUrl('/api/security/system/dsl/proposals','POST'),'/api/security/system/dsl/proposals');
 assert.equal(productReadUrl('/api/agent-instances/a/dsl/proposals','POST'),'/api/agent-instances/a/dsl/proposals');
});
test('overview reflects current Agent PID and does not promote historical task counters or environment diagnostics',async()=>{
 const html=await render('ProductOverview.jsx',{dash:{agents:[{id:'hidden-key',name:'RQ5 alias',agent_type:'dsh',pid:42,connected:true,active:true}],stats:{agents:1,verified_agents:1,strategies:0,pending_strategies:0,active_tasks:57}},status:{broker:{available:true},bpf_lsm:true},onNav:()=>{},onSessions:()=>{}});
 assert.match(html,/DeepSeek Harness/);assert.match(html,/PID 42/);assert.match(html,/策略绑定已核验/);assert.doesNotMatch(html,/RQ5 alias|hidden-key|57|治理候选|历史策略|Linux 内核|ActPlane CLI|DSH CLI|执行后端可用/);
});
test('workbench uses native Agent sessions without internal runtime identifiers or inferred empty workspace',async()=>{
 const directory={connections:[{id:'internal-key',agent_type:'hermes',name:'fixture-alias',pid:88,connected:true}],records:[{id:'s',name:'处理采购问题',instance_id:'internal-key',status:'idle'}],workspaces:[]};
 const html=await render('ConsoleWorkbench.jsx',{api:()=>{},onConfigure:()=>{},onSessions:()=>{}},[directory,'internal-key','','',false,0]);
 assert.match(html,/Hermes/);assert.match(html,/PID 88/);assert.match(html,/处理采购问题/);assert.doesNotMatch(html,/fixture-alias|运行代次|连接实例|工作区<select|<th>工作区/);
});
test('workbench displays the native workspace title separately from its project path',async()=>{
 const directory={connections:[{id:'agent',agent_type:'dsh',pid:42}],records:[{id:'s',name:'检查订单',instance_id:'agent',resource:'/projects/orders',workspace_name:'交易平台',status:'stored'}],workspaces:['/projects/orders'],workspace_records:[{path:'/projects/orders',name:'交易平台'}]};
 const html=await render('ConsoleWorkbench.jsx',{api:()=>{},onConfigure:()=>{},onSessions:()=>{}},[directory,'agent','','',false,0]);
 assert.match(html,/交易平台/);assert.match(html,/\/projects\/orders/);assert.doesNotMatch(html,/\/w\/0|实例资源/);
});
test('empty generations do not render diagnostic panels or empty table columns',async()=>{
 const html=await render('ProductGenerationHistory.jsx',{api:()=>{},onSelectRun:()=>{},onContinueReview:()=>{}},[{items:[],total:0},0,'']);
 assert.match(html,/尚无生成记录/);assert.doesNotMatch(html,/<thead|后台作业|操作日志|JSON|0 条记录/);
});
test('policy search remains editable after a query matches no records',async()=>{
 const data={phase:'ready',scope_id:'system',revision:1,records:[{id:'p',statement:'保护项目配置',rule_name:'protect',effects:['block'],event_types:['per_event'],scope_type:'system'}]};
 const props={scopeId:'system',api:()=>{},post:()=>{}};
 const filtered=await render('ActPlanePolicies.jsx',props,[data,'',false,null,null,'没有匹配']);
 assert.match(filtered,/aria-label="搜索策略语句"/);assert.match(filtered,/value="没有匹配"/);assert.match(filtered,/没有匹配的策略/);assert.doesNotMatch(filtered,/<thead/);
 const cleared=await render('ActPlanePolicies.jsx',props,[data,'',false,null,null,'']);
 assert.match(cleared,/保护项目配置/);assert.doesNotMatch(cleared,/没有匹配的策略/);
});
test('failed live refresh withdraws historical PID and verification without inventing a stopped process',async()=>{
 const prior={agents:[{id:'a',agent_type:'dsh',connected:true,active:true,pid:42}],stats:{agents:1,verified_agents:1}};
 const stale=unknownAgentSummary(prior);assert.equal(stale.agents[0].pid,null);assert.equal(stale.stats.verified_agents,0);assert.equal(prior.agents[0].pid,42);
 const html=await render('ProductOverview.jsx',{dash:stale,status:{error:'read failed'},onNav:()=>{},onSessions:()=>{}});
 assert.match(html,/状态未知|状态读取失败/);assert.doesNotMatch(html,/PID 42|策略绑定已核验|<td>未运行/);
});
