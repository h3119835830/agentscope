import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {policyAction,clauseAction} from './policyRecordPresentation.mjs';
const require=createRequire(import.meta.url),Module=require('node:module');
const source=new URL('./SessionSecurityPanel.jsx',import.meta.url).pathname;
const built=await build({entryPoints:[source],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
const mod=new Module(source);mod.paths=Module._nodeModulePaths(new URL('.',import.meta.url).pathname);mod._compile(built.outputFiles[0].text,source);

test('session combines inherited startup and applied runtime with common fields and neutral historical state',()=>{
 const data={loaded_policies:{records:[],loading_status:{state:'stopped'}},policy_records:{records:[
  {id:'base',name:'保护代码目录',stage:'startup',default_action:'block',source_label:'运行前 · Agent 继承',status:'historical_loaded'},
  {id:'delta',name:'保护用户指定文件',stage:'runtime',default_action:'block',source_label:'运行时 · 用户消息',status:'applied'}]}};
 const html=renderToStaticMarkup(React.createElement(mod.exports.default,{data}));
 for(const value of ['策略名称','默认动作','来源','状态','保护代码目录','保护用户指定文件','运行前 · Agent 继承','运行时 · 用户消息','历史加载','已追加 · 当前未核验'])assert.ok(html.includes(value),value);
 assert.doesNotMatch(html,/tone-good|策略名称／对象|归属|操作／处置|核验指标/);
 assert.equal((html.match(/>详情<\/button>/g)||[]).length,2);
});

test('missing action is not inferred from restriction intent and mixed clauses remain explicit',()=>{
 assert.equal(policyAction(undefined),'未记录');
 assert.equal(clauseAction([{effect:'notify'},{effect:'block'}]),'mixed');
 assert.equal(policyAction(clauseAction([{effect:'block'},{effect:'block'}])),'阻断');
});
