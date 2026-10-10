import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';

const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'SecurityConfiguration.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
const path=join(base,'.security-configuration-test.cjs'),module=new Module(path);
module.paths=Module._nodeModulePaths(base);module._compile(built.outputFiles[0].text,path);
const {default:SecurityConfiguration,SystemSecurityConfiguration,SystemSecurityRules}=module.exports;
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
const row={id:'dsh',mode:'controlled',policy:{network:'disabled',rules:[{action:'tool',effect:'deny',target:'dsh_only_tool',text:''}]},resources:[],policy_hash:'hash',generation:'gen',active:false};

test('scope tabs default to this Agent and never include another Agent policy',()=>{
 let calls=0;const html=render(SecurityConfiguration,{row,onPropose:()=>calls++,onConfirm:()=>calls++});
 assert.match(html,/aria-label="安全配置作用范围"/);
 assert.match(html,/id="security-scope-system"[^>]*aria-selected="false"/);
 assert.match(html,/id="security-scope-agent"[^>]*aria-selected="true"/);
 assert.match(html,/role="tabpanel" id="security-scope-panel-agent" aria-labelledby="security-scope-agent"/);
 assert.match(html,/所有 Agent 共用/);assert.match(html,/所有工作区共用/);
 assert.doesNotMatch(html,/dsh_only_tool/);assert.match(html,/导入 DSL/);assert.doesNotMatch(html,/基础保护|控制心跳超过/);
 const hermes=render(SecurityConfiguration,{row:{...row,id:'hermes',policy:{network:'model_only',rules:[]}}});
 assert.doesNotMatch(hermes,/dsh_only_tool/);assert.equal(calls,0);
});

const shared={id:'system',generation:'2',policy_hash:'shared',phase:'ready',policy:{network:'model_only',rules:[{action:'tool',effect:'deny',target:'shared_tool',text:''}]},policy_records:[{action:'tool',effect:'deny',target:'shared_tool',text:'',result:'已核验 1 / 2 个连接'}],network_result:'已核验 1 / 2 个连接',resources:[],proposals:[]};

test('system configuration shows editable shared rules and actual aggregate verification',()=>{
 let calls=0;const html=render(SystemSecurityRules,{data:shared,onPropose:()=>calls++,onConfirm:()=>calls++});
 assert.match(html,/由你配置的共同限制/);assert.match(html,/shared_tool/);
 assert.match(html,/已核验 1 \/ 2 个连接/);
 assert.match(html,/>添加规则</);assert.match(html,/>编辑</);assert.match(html,/>删除</);
 assert.doesNotMatch(html,/运行隔离|控制面访问|控制失联处理|只读|dsh_only_tool|基础保护/);
 assert.equal(calls,0);
});

test('loading and error states never invent or retain verified shared rules',()=>{
 const loading=render(SystemSecurityConfiguration,{});
 assert.match(loading,/正在读取系统规则/);assert.doesNotMatch(loading,/已核验|添加规则/);
 const error=render(SystemSecurityRules,{error:'连接失败'});
 assert.match(error,/role="alert"/);assert.match(error,/重新读取/);assert.doesNotMatch(error,/已核验|shared_tool/);
 const blocked=render(SystemSecurityRules,{data:{...shared,phase:'blocked',network_result:'应用未完成'}});
 assert.match(blocked,/执行保持暂停/);assert.match(blocked,/重新核验并应用/);
});

test('system change preview lists the affected Agents and requires explicit confirmation',()=>{
 const proposal={id:'p',policy:{...shared.policy,network:'disabled'},targets:[{name:'DSH',affected:true},{name:'Hermes',affected:false}]};
 const html=render(SystemSecurityRules,{data:{...shared,proposals:[proposal]}});
 assert.match(html,/待确认的系统规则变更/);assert.match(html,/受影响连接：DSH/);
 assert.doesNotMatch(html,/受影响连接：DSH、Hermes/);
 assert.match(html,/当前规则尚未被替换/);assert.match(html,/未运行的连接在下次启动时应用/);
 assert.match(html,/确认此变更并应用/);
});

test('current Agent editor uses its own rules and shared restrictions remain separately identified',()=>{
 const html=render(SecurityConfiguration,{row:{...row,system_network:'disabled',local_policy:{network:'model_only',rules:[]},policy:{...row.policy,rules:[{action:'tool',effect:'deny',target:'shared_tool',text:''}]}}});
 assert.doesNotMatch(html,/shared_tool/);assert.match(html,/本连接所有工作区与会话共用/);assert.match(html,/ActPlane DSL/);
});

test('observed connections expose no editable Agent policy',()=>{
 const html=render(SecurityConfiguration,{row:{...row,mode:'observed'}});
 assert.match(html,/当前 Agent 尚未接管执行/);
 assert.doesNotMatch(html,/dsh_only_tool|添加规则|>编辑<|>删除</);
});
