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
test('panel renders all inherited controls by default and marks local application unavailable',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionSecurityPanel.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data:{security:view,records:[]},post(){},onRefresh(){},onConfigure(){}}));
 assert.match(html,/当前会话全部已接入安全约束/);assert.match(html,/工具使用/);assert.match(html,/会话独立配置与停用：暂不支持/);
 assert.ok(!html.includes('继承约束 ·'));assert.match(html,/>停用<\/button>/);assert.ok(!html.includes('应用策略'));
});
test('domain view distinguishes inherited constraints, empty scopes and incomplete counts',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionDomainView.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 const data={coverage_complete:false,notice:'没有额外约束不表示停用',nodes:[
  {id:'system',title:'系统策略',count:2,count_label:'2 项已接入约束',status:'继承约束已核验'},
  {id:'agent',title:'Agent 策略',count:15,count_label:'15 项已接入约束',status:'继承约束已核验'},
  {id:'workspace',title:'工作区约束',count:0,count_label:'无独立约束',status:'暂不支持独立应用'},
  {id:'session',title:'会话约束',count:null,count_label:'数量未完整取得',status:'暂不支持独立应用'}]};
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data}));
 for(const text of ['2 项已接入约束','15 项已接入约束','无独立约束','数量未完整取得','暂不支持独立应用'])assert.ok(html.includes(text));
 assert.equal((html.match(/class="session-domain-node scope-/g)||[]).length,4);assert.ok(!html.includes('平台底线'));
 assert.ok(!html.includes('0 条策略')&&!html.includes('null 条策略'));assert.match(html,/约束信息尚不完整/);
});

test('system filter includes builtins and configured rules without a fifth scope',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionSecurityPanel.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 const builtin={...rule,id:'fixed',kind:'system_builtin',scope:'system',system_builtin:true,title:'保护控制目录',can_configure:false,can_disable:false};
 const configured={...rule,id:'sys',scope:'system'};const data={...view,controls:[builtin,configured,rule]};
 assert.deepEqual(visibleControls(data,{scope:'system'}),[builtin,configured]);
 assert.throws(()=>changeRequest(data,{basisHash:'hash-a',control:builtin,operation:'disable'},{ack:true},'key'),/不能停用/);
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data:{security:data,records:[]},post(){},onRefresh(){},onConfigure(){}}));
 assert.match(html,/系统内置保护/);assert.ok(!html.includes('平台底线')&&!html.includes('value="platform"'));
 const fixedRow=html.match(/<tr><td><strong>保护控制目录[\s\S]*?<\/tr>/)[0];
 assert.ok(fixedRow.includes('只读')&&!fixedRow.includes('>停用<')&&!fixedRow.includes('>配置<'));
});
