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
const {default:SecurityConfiguration,SystemSecurityConfiguration}=module.exports;
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));
const row={id:'dsh',mode:'controlled',policy:{network:'disabled',rules:[{action:'tool',effect:'deny',target:'dsh_only_tool',text:''}]},resources:[],policy_hash:'hash',generation:'gen',active:false};

test('scope tabs default to this Agent and never include another Agent policy',()=>{
 let calls=0;const html=render(SecurityConfiguration,{row,onPropose:()=>calls++,onConfirm:()=>calls++});
 assert.match(html,/aria-label="安全配置作用范围"/);
 assert.match(html,/id="security-scope-system"[^>]*aria-selected="false"/);
 assert.match(html,/id="security-scope-agent"[^>]*aria-selected="true"/);
 assert.match(html,/role="tabpanel" id="security-scope-panel-agent" aria-labelledby="security-scope-agent"/);
 assert.match(html,/所有 Agent 共用/);assert.match(html,/所有工作区共用/);
 assert.match(html,/dsh_only_tool/);assert.doesNotMatch(html,/基础保护|控制心跳超过/);
 const hermes=render(SecurityConfiguration,{row:{...row,id:'hermes',policy:{network:'model_only',rules:[]}}});
 assert.doesNotMatch(hermes,/dsh_only_tool/);assert.equal(calls,0);
});

test('system settings are shared, read-only, and never claim live verification from an Agent state',()=>{
 let calls=0;const props={onPropose:()=>calls++,onConfirm:()=>calls++};
 const dsh=render(SystemSecurityConfiguration,{...props,row:{...row,active:true}});
 const hermes=render(SystemSecurityConfiguration,{...props,row:{...row,id:'hermes',active:false}});
 assert.equal(dsh,hermes);
 assert.match(dsh,/由系统统一管理 · 只读/);assert.match(dsh,/仅观测的连接需接管执行后才能应用/);
 assert.doesNotMatch(dsh,/已核验|待启动核验|dsh_only_tool|添加规则|编辑|删除|<button|<input|<select/);
 assert.equal(calls,0);
});

test('observed connections expose no editable Agent policy',()=>{
 const html=render(SecurityConfiguration,{row:{...row,mode:'observed'}});
 assert.match(html,/当前 Agent 尚未接管执行/);
 assert.doesNotMatch(html,/dsh_only_tool|添加规则|>编辑<|>删除</);
});
