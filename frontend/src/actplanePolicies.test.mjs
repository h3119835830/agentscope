import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {navigationTarget,readNavigation} from './navigation.mjs';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'ActPlanePolicies.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
const filename=join(base,'.dsl-test.cjs'),module=new Module(filename);module.paths=Module._nodeModulePaths(base);module._compile(built.outputFiles[0].text,filename);
const {PolicyRecords,DslCode}=module.exports;
const render=(c,p)=>renderToStaticMarkup(React.createElement(c,p));
test('DSL records retain all declared actions, types and independent context/source',()=>{
 const html=render(PolicyRecords,{records:[{id:'r',statement:'前序测试通过后才允许提交',rule_name:'gate',effects:['block','kill','notify'],event_types:['per_event','cross_event'],scope_type:'system',context_requirement:'project',compile_status:'compiled',loaded:false,active:false,document_id:'d'}],onEdit:()=>{throw Error('Render must not edit');}});
 for(const value of ['block','kill','notify','单事件','跨事件','project','系统策略','编译通过 · 未加载','编辑 DSL'])assert.ok(html.includes(value),value);
 assert.doesNotMatch(html,/当前绑定已核验|允许修改与删除|已送达/);
});
test('older loading receipts are distinct from current verified bindings',()=>{
 const old=render(PolicyRecords,{records:[{id:'r',statement:'Old',loaded:true,active:false}]});
 assert.match(old,/历史已加载/);assert.doesNotMatch(old,/当前绑定已核验/);
 const current=render(PolicyRecords,{records:[{id:'r',statement:'Current',loaded:true,active:true}]});
 assert.match(current,/当前绑定已核验/);
});
test('source DSL displays literal text safely and preserves line numbers',()=>{
 const html=render(DslCode,{text:'rule danger:\n notify read file "<script>alert(1)</script>"\n because "Reason"',firstLine:7});
 assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
 assert.match(html,/>7<\/span>/);assert.match(html,/>9<\/span>/);
});
test('session deep links preserve Agent and workspace filters and retire runtime selection',()=>{
 const origin='http://localhost/?view=sessions&sessionAgent=dsh&sessionFilterInstance=i1&sessionWorkspace=%2Fprojects%2Fone&sessionQuery=fix&sessionCursor=30&sessionGeneration=old';
 const selected=navigationTarget(origin,{sessionInstance:'i1',sessionId:'same id',sessionGeneration:'g1',sessionTab:'syscalls'});
 const n=readNavigation('http://localhost'+selected);
 assert.equal(n.sessionId,'same id');assert.equal(n.sessionGeneration,undefined);assert.equal(n.sessionTab,'syscalls');
 assert.equal(n.sessionWorkspace,'/projects/one');assert.doesNotMatch(selected,/sessionGeneration/);
 const back=readNavigation('http://localhost'+navigationTarget('http://localhost'+selected,{sessionInstance:'',sessionId:'',sessionGeneration:''}));
 assert.equal(back.sessionAgent,'dsh');assert.equal(back.sessionQuery,'fix');assert.equal(back.sessionCursor,30);assert.equal(back.sessionFilterInstance,'i1');assert.equal(back.sessionWorkspace,'/projects/one');
});
