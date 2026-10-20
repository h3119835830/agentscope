import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {flowTime,staleSourceSelections} from './informationFlowPresentation.mjs';

async function component(){
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionInformationFlow.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 return mod.exports;
}

function record(overrides={}){return {
 id:123,time:'1792475035675378404',labels:['SECRET'],provenance_state:'reported_first_origin',
 provenance:{label:'SECRET',origin_pid:100,origin_op:'open',origin_target:'/fixture/demo-secret.txt',origin_timestamp_ns:'1792475035000000000'},
 match:{operation:'connect',target:'127.0.0.1',pid:100,rule_id:7,rule_name:'deny-secret',policy_name:'阻止敏感信息外发',effect:'block',actual_action:'block'},
 binding:{domain_id:41,bundle_hash:'approved-hash',session_id:null,attribution:'shared_executor_unattributed'},
 source_configuration:{names:['阻止敏感信息外发'],documents:[{id:'config-a',name:'阻止敏感信息外发',label:'SECRET',sources:[]}]},evidence_ref:123,...overrides};}

test('audit u64 nanosecond strings render a date without treating them as ISO dates',()=>{
 assert.equal(flowTime('1792475035675378404'),flowTime(1792475035675));
 assert.equal(flowTime('bad-date'),'时间未记录');
 assert.equal(flowTime(null),'时间未记录');
});

test('an old or archived source remains an explicit pinned selection, never silently upgraded',()=>{
 const selected=[{id:'a',version:1},{id:'b',version:2},{id:'c',version:1}];
 assert.deepEqual(staleSourceSelections(selected,[{id:'a',version:2},{id:'b',version:2},{id:'c',version:1,archived:true}]),[selected[0],selected[2]]);
});

test('information flow UI uses the native evidence contract and contains no chain renderer',()=>{
 const source=readFileSync(new URL('./SessionInformationFlow.jsx',import.meta.url),'utf8');
 for(const text of ['shared_domain','当前会话','Agent 共享执行域','records','next_cursor','reported_first_origin','来源未由 ActPlane 报告','不代表完整逐跳传播链','技术证据'])assert.ok(source.includes(text),text);
 for(const obsolete of ['<svg','WitnessGraph','data.edges','anchor=','完整性状态','展开更早来源链'])assert.ok(!source.includes(obsolete),obsolete);
 assert.ok(!source.includes('Math.random'));
});

test('native evidence states distinguish empty and collection failure',async()=>{
 const mod=await component();
 const empty=renderToStaticMarkup(React.createElement(mod.NativeEvidenceStatus,{state:'empty',collection:{available:true},view:'session'}));
 assert.match(empty,/暂无可信归属/);
 const shared=renderToStaticMarkup(React.createElement(mod.NativeEvidenceStatus,{state:'empty',collection:{available:true},view:'shared_domain'}));
 assert.match(shared,/共享执行域暂无/);
 const failed=renderToStaticMarkup(React.createElement(mod.NativeEvidenceStatus,{state:'collection_failed',collection:{available:false},view:'session'}));
 assert.match(failed,/采集失败/);assert.match(failed,/不能据此判断没有信息流/);
 const stale=renderToStaticMarkup(React.createElement(mod.NativeEvidenceStatus,{state:'available',collection:{available:false},view:'session'}));
 assert.match(stale,/此前已保存/);
});

test('evidence table shows source, hit, policy, action and honest scope',async()=>{
 const mod=await component();
 const html=renderToStaticMarkup(React.createElement(mod.EvidenceTable,{records:[record()],onDetail(){}}));
 assert.match(html,/ActPlane 原生命中证据/);
 for(const text of ['/fixture/demo-secret.txt','127.0.0.1','阻止敏感信息外发','已阻止','Agent 共享执行域','未归属单会话'])assert.ok(html.includes(text),text);
 const missing=renderToStaticMarkup(React.createElement(mod.EvidenceTable,{records:[record({provenance_state:'not_reported',provenance:null,binding:{session_id:'s1',attribution:'trusted_tool_tag'}})],onDetail(){}}));
 assert.match(missing,/来源未由 ActPlane 报告/);assert.match(missing,/当前会话/);assert.match(missing,/可信工具标签关联/);
 assert.equal(renderToStaticMarkup(React.createElement(mod.EvidenceTable,{records:[],onDetail(){}})),'');
});

test('scope explanation is collapsed help and never claims shared evidence is session-only',async()=>{
 const mod=await component();
 for(const value of ['session','shared_domain']){
  const html=renderToStaticMarkup(React.createElement(mod.FlowScopeControl,{value,onChange(){}}));
  assert.match(html,/<details class="flow-scope-help">/);
  assert.match(html,/aria-label="查看范围说明"/);
  assert.doesNotMatch(html,/<details[^>]*\bopen\b|inline-notice|warning/);
  assert.match(html,value==='shared_domain'?/不代表当前会话独有行为/:/唯一可信工具标签/);
  assert.match(html,/<label for="([^"]+)">查看范围<\/label>/);
 }
});

test('detail drawer restores focus and exposes native provenance separately from configuration references',()=>{
 const source=readFileSync(new URL('./SessionInformationFlow.jsx',import.meta.url),'utf8');
 for(const text of ['origin.current.focus()','首个可用来源','内核单调时间','来源配置引用','不表示某一条就是此次精确来源','AgentScope 不根据 PID、时间或路径推断来源'])assert.ok(source.includes(text),text);
});

test('label UI separates registration, selection, approval and application',()=>{
 const source=readFileSync(new URL('./LabelManagement.jsx',import.meta.url),'utf8');
 for(const text of ['AGENT','SECRET','系统保留','来源数量','引用配置','登记只保存资料','已保存配置继续引用旧版本','登记 → 配置引用 → 批准 → 单独应用'])assert.ok(source.includes(text),text);
 assert.ok(!source.includes('/apply'));
});
