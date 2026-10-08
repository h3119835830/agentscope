import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {runtimeHooksPath,readRuntimeHooksPage,runtimeHooksState,runtimeHooksReducer,mergeRuntimeHookRecords,runtimeHookPosition,runtimeHookStatus} from './runtimeHooks.mjs';

const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'RuntimeHooks.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
const modulePath=join(base,'.runtime-hooks-test.cjs'),componentModule=new Module(modulePath);
componentModule.paths=Module._nodeModulePaths(base);componentModule._compile(built.outputFiles[0].text,modulePath);
const {default:RuntimeHooks,RuntimeHookOverview,RuntimeHookDetail,RuntimeHookList}=componentModule.exports;
const archiveBuilt=await build({entryPoints:[join(base,'TaskArchiveDetails.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
const archivePath=join(base,'.runtime-hook-archive-test.cjs'),archiveModule=new Module(archivePath);
archiveModule.paths=Module._nodeModulePaths(base);archiveModule._compile(archiveBuilt.outputFiles[0].text,archivePath);
const {ArchiveBody}=archiveModule.exports;
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
const mechanism={name:'DSH 运行时',events:['真实用户消息','ActPlane 内核拒绝'],sequence:['冻结上下文','Pi 评估增量'],source:'current_definition',configuration_status:'not_historical_configuration',historical_configuration:false};
const record=(id='hook-1')=>({id,job_id:'job-'+id,request_id:'request-'+id,time:'2026-10-08T00:00:00Z',generation_status:'completed',trigger:{name:'runtime_observation',actor:'agent',revision:0,turn:0,accepted_turn:0,observations_status:'recorded',observations:[{category:'kernel',type:'kernel_denial',seq:0,content_hash:'hash-'+id,status:'recorded',missing_fields:[]}]},evidence_refs:['evidence-'+id],status:'recorded',missing_fields:[]});
const page=(records=[record()])=>({mechanism,records,total:records.length,next_cursor:null,history_only:true,live:false});

test('Hook read path remains task scoped with encoded task and opaque cursor',()=>{
 const path=runtimeHooksPath('task/one','cursor+/=&?');
 const url=new URL(path,'http://localhost');
 assert.equal(url.pathname,'/api/tasks/task%2Fone/archive/runtime-hooks');
 assert.equal(url.searchParams.get('limit'),'50');
 assert.equal(url.searchParams.get('before'),'cursor+/=&?');
 assert.equal([...url.searchParams].length,2);
});

test('HTML fallbacks and current-state responses cannot become historical trigger records',()=>{
 for(const response of ['<!doctype html>',{}, {...page(),live:true},{...page(),history_only:false}]) {
  assert.throws(()=>readRuntimeHooksPage(response),/Hook 历史记录格式/);
 }
 assert.throws(()=>readRuntimeHooksPage({...page(),mechanism:{...mechanism,historical_configuration:true}}),/不能作为历史配置/);
 assert.throws(()=>readRuntimeHooksPage({...page(),mechanism:{...mechanism,events:[{name:'not the fixed contract'}]}}),/不能作为历史配置/);
});

test('only public trigger identifiers are retained, with zero-valued turns and revisions preserved',()=>{
 const source=record();source.private_reasoning='not-public';source.trigger.observations[0].content='raw observation must stay hidden';
 const result=readRuntimeHooksPage(page([source])).records[0];
 assert.equal(result.trigger.turn,0);assert.equal(result.trigger.accepted_turn,0);
 assert.equal(result.trigger.observations[0].seq,0);
 assert.equal(runtimeHookPosition(result),'轮次 0 / 修订 0');
 assert.equal('private_reasoning' in result,false);
 assert.equal('content' in result.trigger.observations[0],false);
});

test('switching tasks and refreshing the same task both isolate delayed request results',()=>{
 let state=runtimeHooksReducer(runtimeHooksState(),{type:'start',task:'old',request:1});
 state=runtimeHooksReducer(state,{type:'start',task:'new',request:2});
 const switched=state;
 state=runtimeHooksReducer(state,{type:'success',task:'old',request:1,page:readRuntimeHooksPage(page([record('old')]))});
 assert.equal(state,switched);assert.deepEqual(state.records,[]);
 state=runtimeHooksReducer(state,{type:'success',task:'new',request:2,page:readRuntimeHooksPage(page([record('new')]))});
 assert.equal(state.records[0].id,'new');
 state=runtimeHooksReducer(state,{type:'start',task:'new',request:3});
 const refreshed=state;
 assert.equal(runtimeHooksReducer(state,{type:'error',task:'new',request:2,error:'stale failure'}),refreshed);
 assert.equal(runtimeHooksReducer(state,{type:'success',task:'new',request:2,page:readRuntimeHooksPage(page([record('obsolete')]))}),refreshed);
});

test('overlapping pages deduplicate receipts while a failed older-page read retains saved rows',()=>{
 assert.deepEqual(mergeRuntimeHookRecords([record('3'),record('2')],[record('2'),record('1')]).map(r=>r.id),['3','2','1']);
 let state=runtimeHooksReducer(runtimeHooksState(),{type:'start',task:'t',request:1});
 state=runtimeHooksReducer(state,{type:'success',task:'t',request:1,page:readRuntimeHooksPage(page([record('3'),record('2')]))});
 state=runtimeHooksReducer(state,{type:'start',task:'t',request:2,append:true});
 state=runtimeHooksReducer(state,{type:'error',task:'t',request:2,error:'temporary error'});
 assert.deepEqual(state.records.map(r=>r.id),['3','2']);assert.equal(state.error,'temporary error');assert.equal(state.loaded,true);
 state=runtimeHooksReducer(state,{type:'start',task:'t',request:3,append:true});
 state=runtimeHooksReducer(state,{type:'success',task:'t',request:3,append:true,page:readRuntimeHooksPage(page([record('2'),record('1')]))});
 assert.deepEqual(state.records.map(r=>r.id),['3','2','1']);assert.equal(state.error,'');
});

test('current mechanism starts folded and never manufactures actual historical calls',()=>{
 const result=readRuntimeHooksPage(page([]));
 assert.equal(result.records.length,0);
 const overview=render(RuntimeHookOverview,{mechanism:result.mechanism});
 assert.match(overview,/当前接入说明，非历史冻结配置/);
 assert.match(overview,/当前触发来源：真实用户消息、ActPlane 内核拒绝/);
 assert.doesNotMatch(overview,/<details[^>]*\sopen(?:[\s=>])/);
 const list=render(RuntimeHookList,{records:result.records,total:result.total});
 assert.match(list,/未保存实际 Hook 触发记录/);
 assert.doesNotMatch(list,/触发已记录|job-hook/);
});

test('record detail escapes public source text and leaves hashes and evidence in closed disclosure',()=>{
 const unsafe=record();unsafe.trigger.name='<img src=x onerror=alert(1)>';unsafe.trigger.actor='<script>actor</script>';
 unsafe.trigger.observations[0].content_hash='<hash>';unsafe.evidence_refs=['<evidence>'];
 const html=render(RuntimeHookDetail,{record:readRuntimeHooksPage(page([unsafe])).records[0]});
 assert.doesNotMatch(html,/<script|<img|<details[^>]*\sopen(?:[\s=>])/);
 assert.match(html,/&lt;img src=x/);assert.match(html,/观测类别/);assert.match(html,/事件类型/);
 assert.ok(html.indexOf('&lt;hash&gt;')>html.indexOf('<details'));
 assert.ok(html.indexOf('&lt;evidence&gt;')>html.indexOf('<details'));
 assert.match(html,/<dt>执行轮次<\/dt><dd>0<\/dd>/);
});

test('list initially displays five saved records with explicit expansion rather than an endless stack',()=>{
 const records=readRuntimeHooksPage(page(Array.from({length:13},(_,i)=>record('record-'+i)))).records;
 const html=render(RuntimeHookList,{records,total:13});
 assert.equal((html.match(/>查看详情<\/button>/g)||[]).length,5);
 assert.match(html,/再显示 12 条触发记录/);assert.match(html,/共 13 条/);
 assert.doesNotMatch(html,/job-record-5|job-record-12/);
});

test('missing trigger material stays unrecorded and initial rendering performs no API or execution action',()=>{
 const missing=readRuntimeHooksPage(page([{...record(),trigger:{},status:'unrecorded',missing_fields:['trigger.name']}])).records[0];
 assert.equal(runtimeHookStatus(missing),'触发材料未记录');
 assert.match(render(RuntimeHookDetail,{record:missing}),/未记录字段：触发来源/);
 let calls=0;
 const html=render(RuntimeHooks,{task:'t',api:()=>{calls++;}});
 assert.equal(calls,0);assert.match(html,/Hook 触发点/);assert.match(html,/刷新触发记录/);
 assert.match(html,/正在读取触发记录/);
 assert.doesNotMatch(html,/加载并启动|最终审核通过|<input|<textarea/);
});

test('partial frozen observations retain missing-field status and are not presented as all newly triggered',()=>{
 const source=record();source.trigger.actor='native_context';source.trigger.observations_status='unrecorded';
 source.trigger.observations=[{category:'tools',type:'request/header',seq:null,content_hash:'',status:'unrecorded',missing_fields:['seq','content_hash']}];
 source.missing_fields=['accepted_turn','context','ambiguous_request_source'];
 const parsed=readRuntimeHooksPage(page([source])).records[0];
 assert.equal(parsed.trigger.observations_status,'unrecorded');
 assert.deepEqual(parsed.trigger.observations[0].missing_fields,['seq','content_hash']);
 const html=render(RuntimeHookDetail,{record:parsed});
 assert.match(html,/原生上下文变化/);assert.match(html,/请求工具定义/);
 assert.match(html,/保存于该次评估的上下文快照，条目不一定都是本轮新触发/);
 assert.match(html,/存在未记录字段/);assert.match(html,/接收轮次、冻结上下文快照、请求来源不唯一/);
 assert.match(html,/未记录字段：观测序号、内容 hash/);
});

test('archive runtime list exposes the Hook module without adding it to startup or issuing SSR requests',()=>{
 let calls=0;const props={task:'t',api:()=>{calls++;},data:{header:{},stages:[]}};
 const runtime=render(ArchiveBody,{...props,pane:'runtime'});
 assert.match(runtime,/Hook 触发点/);assert.match(runtime,/刷新触发记录/);assert.match(runtime,/不是实时事件流/);
 assert.doesNotMatch(render(ArchiveBody,{...props,pane:'startup'}),/Hook 触发点/);
 assert.equal(calls,0);
});
