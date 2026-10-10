import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {agentProcessLabel} from './agentInstancePresentation.mjs';

const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'AgentSessions.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
function render(navigation,states){
 let index=0;
 const hookReact={...React,useState:initial=>[index in states?states[index++]:((index++,typeof initial==='function'?initial():initial)),()=>{}]};
 const filename=join(base,'.session-test.cjs'),module=new Module(filename);module.paths=Module._nodeModulePaths(base);
 const original=module.require.bind(module);module.require=id=>id==='react'?hookReact:original(id);module._compile(built.outputFiles[0].text,filename);
 return renderToStaticMarkup(React.createElement(module.exports.default,{api:()=>{},navigate:()=>{},navigation,onConfigure:()=>{}}));
}
test('DSH process labels use product and current PID, never a fixture alias or internal ID',()=>{
 assert.equal(agentProcessLabel({agent_type:'dsh',name:'RQ5 fixture',id:'internal',pid:42}),'DeepSeek Harness · PID 42');
 assert.equal(agentProcessLabel({agent_type:'dsh',name:'RQ5 fixture',pid:null}),'DeepSeek Harness · 未运行');
});
test('session directory preserves native titles and product identity without workspace or process filters',()=>{
 const connection={id:'instance-internal',name:'RQ5 fixture',agent_type:'dsh',pid:42};
 const directory={records:[{id:'native-session',name:'RQ5 原生会话名称',resource:'/projects/one',workspace_name:'订单服务',instance_id:connection.id,instance_name:connection.name,agent_type:'dsh',agent_pid:42,process_ids:[],status:'stored'}],connections:[connection],workspace_available:true,workspaces:['/projects/one'],workspace_records:[{path:'/projects/one',name:'订单服务'}],count_complete:true,total:1};
 const html=render({},[directory,null,null,'',false]);
 assert.match(html,/DeepSeek Harness/);assert.match(html,/RQ5 原生会话名称/);assert.doesNotMatch(html,/\/projects\/one/);
 assert.doesNotMatch(html,/RQ5 fixture|instance-internal|连接实例|运行代次|Agent 产品|进程（PID）/);
 assert.doesNotMatch(html,/工作区<select|Agent 进程/);
 assert.doesNotMatch(html,/订单服务/);
 const migrated=render({sessionWorkspace:'/host/project'},[{...directory,selected_workspace:'/projects/one'},null,null,'',false]);
 assert.doesNotMatch(migrated,/<option value="\/projects\/one"/);
 assert.doesNotMatch(migrated,/\/host\/project/);
});
test('session details use current Agent context and do not offer internal runtime selection',()=>{
 const instance={id:'instance-internal',name:'RQ5 fixture',agent_type:'dsh'};
 const root='/api/agent-instances/'+instance.id+'/sessions/native-session';
 const summary={_key:root,session:{name:'修复登录表单',resource:'/projects/one'},instance,agent_pid:42,pid:42,active:true,domain_id:7,executor_shared:true,generations:[{generation:'generation-internal'}],records:[]};
 const html=render({sessionInstance:instance.id,sessionId:'native-session',sessionTab:'policies',sessionGeneration:'old'},[null,summary,{...summary,_key:root+'policies'},'',false]);
 for(const text of ['修复登录表单','DeepSeek Harness','PID 42','继承的 Agent 保护已核验'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/RQ5 fixture|instance-internal|generation-internal|运行代次|当前代次/);
});

test('product filter stays available with a single filtered Agent and missing mapping is unknown',()=>{
 const directory={records:[],connections:[{id:'h',agent_type:'hermes'}],errors:[],count_complete:false,total:0};
 const html=render({sessionAgent:'hermes'},[directory,null,null,'',false,0,null,null,'',[{id:'d',agent_type:'dsh'},{id:'h',agent_type:'hermes'}]]);
 assert.match(html,/DeepSeek Harness/);assert.match(html,/<option value="hermes" selected="">Hermes/);assert.match(html,/尚未取得会话映射，数量未知/);assert.doesNotMatch(html,/没有匹配的会话/);
});
