import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const bundle=await build({entryPoints:[join(base,'GenerationConfigurations.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
const filename=join(base,'.generation-configurations-test.cjs'),loaded=new Module(filename);loaded.paths=Module._nodeModulePaths(base);loaded._compile(bundle.outputFiles[0].text,filename);
const Component=loaded.exports.default;
const row={id:'config-a',revision:1,name:'员工资料读取保护',template:{id:'FILE-READ',version:2,name:'文件读取限制',parameters:[{key:'target',label:'保护对象的路径',type:'path'}]},parameters:{target:'/w/0/private/employees.csv'},scope:{id:'agent-a',type:'agent',label:'指定 Agent · DSH 测试连接'},approval_status:'draft',approval_operation:'apply'};
const render=(rows=[row])=>renderToStaticMarkup(React.createElement(Component,{generation:{items:rows.map(r=>({id:r.id,revision:r.revision})),configuration_snapshots:rows}}));

test('conversation table and its details use only the saved snapshot',()=>{
 const html=render();
 for(const value of ['策略名称','员工资料读取保护','选用模板','文件读取限制','v2','保护对象的路径','/w/0/private/employees.csv','作用范围','指定 Agent · DSH 测试连接','触发条件','状态','待提交审批'])assert.ok(html.includes(value),value);
 assert.match(html,/<table/);assert.equal((html.match(/<tr>/g)||[]).length,2);
 assert.doesNotMatch(html,/<button|<input|<textarea|<select|手工配置|新增子配置|FILE-READ|config-a/);
});
test('separate configurations keep different templates, parameters, scopes and approvals',()=>{
 const other={...row,id:'config-b',name:'共享环境保护',template:{...row.template,name:'环境凭据文件',version:3},parameters:{target:'.env'},scope:{id:'system',type:'system',label:'所有 Agent'},approval_status:'approved'};
 const html=render([row,other]);assert.match(html,/共享环境保护/);assert.match(html,/所有 Agent/);assert.match(html,/已批准 · 待应用/);assert.match(html,/v3/);
});
test('operation and disposition parameters are readable and escaped',()=>{
 const html=render([{...row,name:'<script>fake</script>',template:{...row.template,parameters:[{key:'operations',label:'触发操作',type:'operations'},{key:'effect',label:'匹配后的动作',type:'effect'}]},parameters:{operations:['write','unlink'],effect:'block'}}]);
 assert.match(html,/写入、删除/);assert.match(html,/阻止并反馈/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
test('disable approvals describe disable instead of claiming active protection',()=>{
 assert.match(render([{...row,approval_operation:'disable',approval_status:'pending'}]),/停用 · 待审批/);
 assert.match(render([{...row,approval_operation:'disable',approval_status:'applied'}]),/已停用/);
});
test('empty and unavailable history do not invent template or parameter values',()=>{
 assert.equal(render([]),'');
 const html=render([{id:'missing',revision:1,unavailable:true}]);assert.match(html,/快照暂不可用/);assert.doesNotMatch(html,/员工资料|文件读取限制/);
 assert.match(render([{...row,approval_status:'unavailable'}]),/审批状态暂不可用/);
});
test('effective operations and disposition come from the exact version, not requested intent',()=>{
 const html=render([{...row,parameters:{target:'/w/0/file'},execution:{requested_operations:['unlink'],effective_operations:['write','unlink'],effect:'notify',reason:'请保留发布清单',coverage_warning:'写入与删除共用执行访问组'}}]);
 assert.match(html,/写入、删除/);assert.match(html,/记录并提醒/);assert.match(html,/匹配后反馈/);assert.match(html,/请保留发布清单/);assert.match(html,/共用执行访问组/);
 assert.match(render(),/处置未记录/);
});
