import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {policyRecord,policyRecordFields,approvalPolicyRows} from './policyRecords.mjs';
import {navigationTarget,readNavigation} from './navigation.mjs';

const row={id:'tc-one',revision:1,name:'报告由指定程序生成',scope:{label:'指定 Agent'},template:{name:'生成文件写入约束',version:2,parameters:[{key:'target',label:'保护对象',type:'path'},{key:'producer',label:'生成程序',type:'program'}]},parameters:{target:'/w/0/reports/change-report.md',producer:'python3'},execution:{effective_operations:['write','unlink'],effect:'block'}};
test('the same exact configuration has identical fields across saved and frozen forms',()=>{
 const snapshot=policyRecord({...row,approval_status:'pending'});
 const saved=policyRecord({id:row.id,revision:1,name:row.name,scope:'agent',scope_label:'指定 Agent',template_definition:row.template,parameters:row.parameters,...row.execution,status:'pending'});
 assert.deepEqual(snapshot,saved);
 assert.equal(snapshot.target,'保护对象：/w/0/reports/change-report.md');
 assert.equal(snapshot.conditions,'生成程序：python3');
 assert.deepEqual(policyRecordFields,['策略名称','作用范围','匹配对象','限制操作','触发条件','处置','状态']);
});
test('exceptions remain conditions rather than a second protection target',()=>{
 const record=policyRecord({...row,template:{...row.template,parameters:[{key:'target',label:'受约束范围',type:'path'},{key:'exception',label:'例外范围',type:'path'}]},parameters:{target:'/w/0/**',exception:'/w/0/src/**'}});
 assert.equal(record.target,'受约束范围：/w/0/**');assert.equal(record.conditions,'例外范围：/w/0/src/**');
});
test('unsupported and unavailable snapshots cannot claim a normal approvable state',()=>{
 assert.equal(policyRecord({...row,approval_status:'draft',execution_support:{applicable:false}}).status,'暂不支持 · 仅参数草案');
 const missing=policyRecord({id:'missing',revision:1,unavailable:true});
 assert.equal(missing.scope,'范围待核验');assert.equal(missing.target,'对象待核验');
});
test('independent approval records retain distinct authority identities and exact revisions',()=>{
 const base={target_name:'DSH',scope_label:'全部会话',status:'approved',configuration_status:{label:'已批准待应用'}};
 const approvals=[{...base,id:'approval-a',configuration_records:[row]},{...base,id:'approval-b',configuration_records:[{...row,id:'tc-two',name:'另一策略',revision:4}]}];
 const result=approvalPolicyRows(approvals);
 assert.equal(result.length,2);assert.equal(new Set(result.map(r=>r.record_key)).size,2);
 assert.deepEqual(result.map(r=>r.id),['approval-a','approval-b']);assert.ok(result.every(r=>r.batch_size===1));
 assert.equal(result[1].policy_record.revision,4);assert.equal(result[1].policy_record.status,'已批准待应用');
});
test('record navigation round trips and changing batches clears the previous focus',()=>{
 const base='http://127.0.0.1/?view=approvals';
 const path=navigationTarget(base,{approvalId:'batch-a',approvalRecordId:'tc-one'});
 assert.equal(readNavigation(new URL(path,base)).approvalRecordId,'tc-one');
 assert.equal(readNavigation(new URL(navigationTarget(new URL(path,base),{approvalId:'batch-b'}),base)).approvalRecordId,'');
});

const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const bundle=await build({entryPoints:[join(base,'PolicyApprovals.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
const filename=join(base,'.policy-records-test.cjs'),loaded=new Module(filename);loaded.paths=Module._nodeModulePaths(base);loaded._compile(bundle.outputFiles[0].text,filename);
test('each policy renders one approval record with inline decisions and no detail dialog',()=>{
 const data={target_name:'DSH',scope_label:'全部会话',scope_type:'agent',status:'pending',can_approve:true,can_reject:true,created_at:'2026-10-26T00:00:00Z',configuration_status:{label:'待审批'}};
 const rows=[{...data,id:'approval-a',configuration_records:[row]},{...data,id:'approval-b',configuration_records:[{...row,id:'tc-two',name:'第二项策略'}]}];
 const html=renderToStaticMarkup(React.createElement(loaded.exports.ApprovalRecords,{rows,navigate(){}}));
 assert.equal((html.match(/<tr\b/g)||[]).length,3);assert.doesNotMatch(html,/同批|整批|审批详情|<dialog|查看并审批/);
 for(const field of policyRecordFields)assert.ok(html.includes('<th>'+field+'</th>'));
 assert.match(html,/生成程序：python3/);assert.doesNotMatch(html,/报告由指定程序生成、第二项策略/);
});
test('old grouped objects cannot be disguised as multiple independent records',()=>{
 const data={id:'old-group',name:'旧合并审批',configuration_records:[row,{...row,id:'tc-two'}]};
 assert.equal(approvalPolicyRows([data]).length,1);
 const html=renderToStaticMarkup(React.createElement(loaded.exports.ApprovalRecordActions,{row:data}));
 assert.match(html,/拆分记录/);assert.doesNotMatch(html,/>批准<|>应用<|<dialog/);
});
