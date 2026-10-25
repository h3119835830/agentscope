import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {readNavigation} from './navigation.mjs';
import {publicAuditText} from './auditPresentation.mjs';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'SessionAudit.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
const filename=join(base,'.audit-test.cjs'),module=new Module(filename);module.paths=Module._nodeModulePaths(base);module._compile(built.outputFiles[0].text,filename);
test('audit route remains selected and records do not expose internal IDs or imply damage',()=>{
 assert.equal(readNavigation('http://localhost/?view=sessions&sessionTab=audit').sessionTab,'audit');
 const html=renderToStaticMarkup(React.createElement(module.exports.AuditRecords,{data:{configuration:{enabled:true},records:[{id:'internal-job-id',stage:'postrun',state:'completed',created_at:'2026-10-25',result:{summary:'已阻止修改',findings:[{id:'0',category:'integrity',severity:'medium',outcome:'blocked_attempt',evidence_ids:['kernel:999'],explanation:'内核拒绝了修改'}],integrity:[{path:'release.json',unchanged:true}]}}],reviews:[]}}));
 assert.match(html,/评估|审计/);assert.match(html,/尝试已被阻止/);assert.match(html,/与登记基线一致/);assert.match(html,/尚未人工复核/);assert.doesNotMatch(html,/internal-job-id|kernel:999|已经受到损害/);
});
test('unknown integrity is not presented as a change and public prose hides technical IDs',()=>{
 const html=renderToStaticMarkup(React.createElement(module.exports.AuditRecords,{data:{records:[{id:'private',stage:'postrun',state:'completed',created_at:'2026-10-25',result:{integrity:[{path:'missing.json',unchanged:null}]}}]}}));
 assert.match(html,/完整性未知/);assert.doesNotMatch(html,/发生变化，需核实/);
 assert.equal(publicAuditText('instance-751ad8a6165f4357 kernel:50'),'当前 Agent 关联证据');
});
