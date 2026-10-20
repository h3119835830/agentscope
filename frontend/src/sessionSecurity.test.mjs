import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {changeRequest,visibleControls,impact} from './sessionSecurity.mjs';
const rule={id:'typed-a',kind:'typed',scope:'agent',rule:{action:'tool',effect:'deny',target:'bash',text:'保护工具'},title:'工具使用',target:'bash',method:'工具准入',status:'工具准入检查已配置',can_configure:true,can_disable:true};
const view={basis_hash:'hash-a',can_propose:true,controls:[rule],checks:[],coverage_complete:true,session_local_reason:'共享执行器暂不支持局部应用'};
const draft={basisHash:'hash-a',control:rule,operation:'disable'};
test('loaded policy detail shows readable rules without runtime identifiers or raw DSL',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module'),source=new URL('./SessionSecurityPanel.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);globalThis.document={activeElement:null};
 const record={name:'配置文件保护',scope:'agent',configuration_revision:2,document_id:'internal-document',original_dsl:'internal-raw-dsl',evidence:{generation:'internal-run',pid:34567,domain_id:91,bundle_hash:'internal-hash'},clauses:[{operation:'read',effect:'block',target:'/w/0/protected.txt'}]};
 const html=renderToStaticMarkup(React.createElement(mod.exports.LoadedPolicyDetails,{record,onClose(){}}));
 assert.match(html,/配置文件保护/);assert.match(html,/当前加载配置 v2/);assert.match(html,/protected.txt/);
 assert.doesNotMatch(html,/运行代次|执行域|PID|策略哈希|internal-run|internal-hash|internal-raw-dsl|internal-document|34567/);
 assert.equal(record.evidence.generation,'internal-run');
});
test('structured removal is scoped and never contains approval or application authority',()=>{
 const request=changeRequest(view,draft,{ack:true},'test-request');
 assert.deepEqual(request,{scope:'agent',operation:'disable',basis_hash:'hash-a',constraint_id:'typed-a',request_key:'test-request',acknowledge_scope:true});
 assert.ok(!('approved' in request)&&!('rule' in request));
 assert.equal(impact('agent'),'此 Agent 的全部工作区、会话和子进程');
});
test('acknowledgement, exact basis and available owner are required',()=>{
 assert.throws(()=>changeRequest(view,draft,{ack:false},'key'),/核对/);
 assert.throws(()=>changeRequest({...view,basis_hash:'new'},draft,{ack:true},'key'),/变化/);
 assert.throws(()=>changeRequest(view,{basisHash:'hash-a',operation:'add'},{scope:'session',ack:true},'key'),/共享/);
 assert.throws(()=>changeRequest(view,{...draft,control:{...rule,id:'foreign'}},{ack:true},'key'),/变化/);
});
test('read only boundaries cannot produce removal candidates',()=>{
 const fixed={...rule,can_disable:false,scope:'system',system_builtin:true,reason:'系统内置保护不可停用'};
 assert.throws(()=>changeRequest({...view,controls:[fixed]},{...draft,control:fixed},{ack:true},'key'),/系统内置保护/);
});
test('guidance preserves text and has no invented file or kernel operation',()=>{
 const request=changeRequest(view,{basisHash:'hash-a',operation:'add'},{scope:'agent',ack:true,action:'behavior',effect:'allow',text:'注明信息来源',target:'ignored'},'key');
 assert.deepEqual(request.rule,{action:'behavior',effect:'deny',text:'注明信息来源',target:''});
 assert.throws(()=>changeRequest(view,{basisHash:'hash-a'},{scope:'agent',ack:true,action:'behavior',text:''},'key'),/行为/);
});
test('filtering does not drop constraints from the authoritative view',()=>{
 const system={...rule,id:'system',scope:'system'};const original={...view,controls:[rule,system]};
 assert.deepEqual(visibleControls(original,{scope:'system'}),[system]);assert.equal(original.controls.length,2);
});
test('panel renders only current loaded policy names and never legacy controls or edit actions',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionSecurityPanel.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 const loaded={loading_status:{state:'loaded',label:'已加载',expires_at:new Date(Date.now()+8000).toISOString()},state:'verified',coverage_complete:true,records:[{id:'doc',name:'保护配置文件',scope:'agent',status:'loaded',source_kind:'configuration',clauses:[{operation:'read',effect:'block',target:'/w/0/.env'}]}],notice:'同一 Agent 进程内的会话共享策略'};
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data:{security:view,loaded_policies:loaded}}));
 for(const text of ['保护配置文件','/w/0/.env','Agent 策略','读取','阻断','已加载','共享策略'])assert.ok(html.includes(text),text);
 for(const text of ['工具使用','执行方式','添加约束','检查当前配置','工作区继承','本会话','>停用<','>配置<'])assert.ok(!html.includes(text),text);
 assert.equal((html.match(/<option /g)||[]).length,3);
 const missing=renderToStaticMarkup(React.createElement(mod.exports.default,{data:{security:view}}));
 assert.match(missing,/未取得当前加载证据/);assert.ok(!missing.includes('工具使用'));
});
test('expired or temporarily unreadable loading evidence keeps the last snapshot without a green claim',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionSecurityPanel.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 const loaded={loading_status:{state:'loaded',label:'已加载',expires_at:new Date(Date.now()-1000).toISOString()},state:'verified',coverage_complete:true,records:[{id:'doc',name:'上次保护配置',scope:'agent',status:'loaded',clauses:[{operation:'write',effect:'block',target:'/project/tests'}]}]};
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data:{loaded_policies:loaded},error:'读取超时'}));
 for(const text of ['上次核验策略','上次保护配置','/project/tests','当前未核验','不代表当前仍在 ActPlane 中加载','上次核验'])assert.match(html,new RegExp(text));
 assert.doesNotMatch(html,/record-badge good|当前已加载策略/);
});
test('domain view only displays two owners of a shared domain, including unknown counts',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionDomainView.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 const data={coverage_complete:false,notice:'同一 Agent 进程共享策略',nodes:[
  {id:'system',title:'系统策略',count:2,count_label:'2 项已加载策略',status:'加载快照已核验'},
  {id:'agent',title:'Agent 策略',count:null,count_label:'加载数量尚未完整核验',status:'当前加载证据不完整'},
  {id:'workspace',title:'工作区约束',count:0,count_label:'无独立约束',status:'暂不支持独立应用'},
  {id:'session',title:'会话约束',count:null,count_label:'数量未完整取得',status:'暂不支持独立应用'}]};
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data}));
 for(const text of ['2 项已加载策略','加载数量尚未完整核验'])assert.ok(html.includes(text));
 assert.equal((html.match(/class="session-domain-node scope-/g)||[]).length,2);
 for(const text of ['工作区约束','会话约束','无独立约束','暂不支持独立应用','0 条策略','null 条策略'])assert.ok(!html.includes(text));
 assert.match(html,/当前加载证据不完整/);
});

test('unverified loading never falls back to configured builtins or a green status',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionSecurityPanel.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 const builtin={...rule,id:'fixed',kind:'system_builtin',scope:'system',system_builtin:true,title:'保护控制目录',can_configure:false,can_disable:false};
 const configured={...rule,id:'sys',scope:'system'};const data={...view,controls:[builtin,configured,rule]};
 assert.deepEqual(visibleControls(data,{scope:'system'}),[builtin,configured]);
 assert.throws(()=>changeRequest(data,{basisHash:'hash-a',control:builtin,operation:'disable'},{ack:true},'key'),/不能停用/);
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data:{security:data,loaded_policies:{state:'unverified',coverage_complete:false,records:[],message:'当前加载证据尚未核验'}}}));
 assert.match(html,/当前加载证据未核验或已过期/);assert.match(html,/暂无上次核验记录/);
 assert.ok(!html.includes('保护控制目录')&&!html.includes('record-badge good'));
});
