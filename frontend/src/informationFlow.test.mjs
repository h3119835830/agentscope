import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {flowTime,staleSourceSelections} from './informationFlowPresentation.mjs';
test('audit u64 nanosecond strings render a date without treating them as ISO dates',()=>{
 assert.equal(flowTime('1792475035675378404'),flowTime(1792475035675));
 assert.equal(flowTime('bad-date'),'时间未记录');
 assert.equal(flowTime(null),'时间未记录');
});
test('an old or archived source remains an explicit pinned selection, never silently upgraded',()=>{
 const selected=[{id:'a',version:1},{id:'b',version:2},{id:'c',version:1}];
 assert.deepEqual(staleSourceSelections(selected,[{id:'a',version:2},{id:'b',version:2},{id:'c',version:1,archived:true}]),[selected[0],selected[2]]);
});
test('flow UI exposes evidence boundaries, error states, paging and scope instead of fabricating edges',()=>{
 const source=readFileSync(new URL('./SessionInformationFlow.jsx',import.meta.url),'utf8');
 for(const status of ['empty','legacy','unsupported','collection_failed','incomplete'])assert.ok(source.includes(status),status);
 for(const text of ['shared_domain','当前会话','不代表当前会话独有行为','next_cursor','evidence_ref','实际 Hook'])assert.ok(source.includes(text),text);
 assert.ok(source.includes('const edges=data.edges'));
 assert.ok(!source.includes('Math.random'));
});
test('label UI separates registration, selection, approval and application',()=>{
 const source=readFileSync(new URL('./LabelManagement.jsx',import.meta.url),'utf8');
 for(const text of ['AGENT','SECRET','系统保留','来源数量','引用配置','登记只保存资料','已保存配置继续引用旧版本','登记 → 配置引用 → 批准 → 单独应用'])assert.ok(source.includes(text),text);
 assert.ok(!source.includes('/apply'));
});
test('rendered evidence statuses distinguish old, empty, failed, unsupported and incomplete',async()=>{
 const require=createRequire(import.meta.url),Module=require('node:module');
 const source=new URL('./SessionInformationFlow.jsx',import.meta.url).pathname;
 const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);
 for(const [state,text] of Object.entries({empty:'暂无带标签',legacy:'历史命中回执',unsupported:'不支持逐跳',collection_failed:'采集失败',incomplete:'链路不完整'})){
  const html=renderToStaticMarkup(React.createElement(mod.exports.FlowStatus,{integrity:{state,reasons:['missing_predecessor']}}));
  assert.ok(html.includes(text),state);
 }
 assert.equal(renderToStaticMarkup(React.createElement(mod.exports.WitnessGraph,{data:{nodes:[],edges:[]},onDetail(){}})),'');
});
