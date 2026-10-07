import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'TaskArchiveDetails.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
const module=new Module(join(base,'.archive-policy-render.cjs'));module.paths=Module._nodeModulePaths(base);module._compile(built.outputFiles[0].text,join(base,'.archive-policy-render.cjs'));
const {PolicyStatementEvidence}=module.exports;
const render=record=>renderToStaticMarkup(React.createElement(PolicyStatementEvidence,{record}));
test('selected statement DSL is visible and inherited whole package starts in a separate closed disclosure',()=>{
 const html=render({compilation:{scope:'statement',dsl:'rule own-statement'},bundle_compilation:{scope:'candidate_bundle',dsl:'rule inherited-package'}});
 assert.ok(html.indexOf('rule own-statement')<html.indexOf('<details'));assert.match(html,/<details[^>]*><summary>完整候选包（包含继承规则）<\/summary>/);assert.doesNotMatch(html,/<details[^>]*open/);assert.match(html,/rule inherited-package/);
});
test('candidate bundle-only material is never the default statement code block',()=>{
 const html=render({compilation:{scope:'candidate_bundle',dsl:'rule inherited-package'}});assert.ok(html.indexOf('未保存该语句')<html.indexOf('<details'));assert.ok(html.indexOf('rule inherited-package')>html.indexOf('<details'));
});
test('guidance states that no OS rule is generated while output expansion shows only recorded boolean change',()=>{
 const guidance=render({policy_type:'content',compilation:{scope:'statement',dsl:'unexpected-os-rule'}});assert.match(guidance,/行为指导，不生成 OS 规则/);assert.doesNotMatch(guidance,/unexpected-os-rule/);
 const expansion=render({change_status:'permission_changed',dsl_diff:{status:'not_recorded',removed_clauses:[]},permission_delta:{target:'/output',allow_output_before:false,allow_output_after:true}});assert.match(expansion,/禁止 → 允许/);assert.doesNotMatch(expansion,/规则已移除|变更前/);
});
