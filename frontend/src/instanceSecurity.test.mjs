import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {displayTarget,ruleSentence,removeRule,replaceRule,policyChanges,proposalDraft,sameBaseline} from './instanceSecurity.mjs';

const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'InstanceSecurity.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
const path=join(base,'.instance-security-test.cjs'),componentModule=new Module(path);
componentModule.paths=Module._nodeModulePaths(base);componentModule._compile(built.outputFiles[0].text,path);
const {default:InstanceSecurity,PendingChange,RuleForm}=componentModule.exports;
const root='/s/instance-resources/rq5-dsh/transaction-verification-service';
const allow={action:'write',target:root,effect:'allow',text:'修复源码'};
const deny={action:'write',target:root+'/tests',effect:'deny',text:'保留测试'};
const policy={rules:[allow,deny],network:'model_only'};
const row={id:'instance',mode:'controlled',resources:[root],policy,policy_hash:'original',generation:'generation',active:false,policy_records:[]};
const render=(Component,props)=>renderToStaticMarkup(React.createElement(Component,props));

test('rule list offers per-rule operations, keeps inheritance read-only and performs no mutations on render',()=>{
 let calls=0;const html=render(InstanceSecurity,{row,onPropose:()=>calls++,onConfirm:()=>calls++});
 assert.match(html,/安全规则<\/th><th>当前状态<\/th><th>操作<\/th>/);
 assert.match(html,/禁止修改与删除「transaction-verification-service\/tests」。/);
 assert.doesNotMatch(html,/\/s\/instance-resources|策略哈希|连接身份与核验详情|执行方式<\/th>|来源<\/th>/);
 assert.equal((html.match(/>删除<\/button>/g)||[]).length,2);
 assert.equal((html.match(/>编辑<\/button>/g)||[]).length,3);
 assert.match(html,/基础保护（只读）/);
 assert.doesNotMatch(html,/<details[^>]*\sopen(?:[\s=>])/);
 assert.equal(calls,0);
});

test('deleting one rule preserves every other rule, network and original snapshot',()=>{
 const original=structuredClone(policy),candidate=removeRule(policy,1);
 assert.deepEqual(candidate,{network:'model_only',rules:[allow]});
 assert.deepEqual(policy,original);
 candidate.rules[0].text='edited';
 assert.equal(policy.rules[0].text,'修复源码');
 for(const index of [-1,2,undefined,NaN])assert.throws(()=>removeRule(policy,index));
});

test('editing and adding rules preserve unrelated permissions and captured concurrency guards',()=>{
 const changed={...deny,text:'新的约束'};
 assert.deepEqual(replaceRule(policy,1,changed).rules,[allow,changed]);
 assert.deepEqual(replaceRule(policy,null,changed).rules,[allow,deny,changed]);
 const draft=proposalDraft(row,policy);
 policy.rules[0].text='临时更新';
 assert.equal(draft.policy.rules[0].text,'修复源码');
 policy.rules[0].text='修复源码';
 assert.ok(sameBaseline(row,draft));
 assert.equal(sameBaseline({...row,policy_hash:'new'},draft),false);
 assert.equal(sameBaseline({...row,generation:'restarted'},draft),false);
});

test('display paths use exact resource boundaries and do not confuse same-name resources',()=>{
 assert.equal(displayTarget(root+'/tests',[root]),'transaction-verification-service/tests');
 assert.equal(displayTarget(root+'-other/tests',[root]),root+'-other/tests');
 assert.equal(displayTarget('/projects/a/app/tests',['/projects/a/app','/projects/b/app']),'/projects/a/app/tests');
 assert.equal(ruleSentence(deny), '禁止修改与删除「'+root+'/tests」；保留测试');
});

test('permission expansion review shows the exact deletion and requires explicit confirmation',()=>{
 const candidate=removeRule(policy,1),changes=policyChanges(policy,candidate);
 assert.deepEqual(changes,[{operation:'删除',sentence:ruleSentence(deny)}]);
 let calls=0;
 const html=render(PendingChange,{proposal:{id:'p',policy:candidate},current:policy,onConfirm:()=>calls++});
 assert.match(html,/当前规则尚未被替换/);
 assert.match(html,/禁止修改与删除/);
 assert.ok(html.includes(root+'/tests'));
 assert.match(html,/查看变更后的完整配置/);
 assert.match(html,/确认此变更并应用/);
 assert.doesNotMatch(html,/<details[^>]*\sopen(?:[\s=>])/);
 assert.equal(calls,0);
});

test('rule editor restricts invalid action decisions and stale drafts cannot submit',()=>{
 const html=render(RuleForm,{initial:deny,stale:true,onCancel:()=>{},onSubmit:()=>{}});
 assert.doesNotMatch(html,/<option value="confirm"/);
 assert.match(html,/<button[^>]*disabled[^>]*>提交更改/);
 assert.match(html,/配置已有更新/);
 const tool=render(RuleForm,{initial:{action:'tool',effect:'confirm',target:'bash',text:''}});
 assert.match(tool,/<option value="confirm" selected="">确认后允许/);
 const behavior=render(RuleForm,{initial:{action:'behavior',effect:'deny',target:'',text:'保留数据'}});
 assert.doesNotMatch(behavior,/目标文件或目录|<label>决定/);
});

test('policy content stays escaped in list and full candidate review',()=>{
 const attack={action:'behavior',effect:'deny',target:'',text:'<img src=x onerror=alert(1)>'};
 const html=render(InstanceSecurity,{row:{...row,policy:{...policy,rules:[attack]}}});
 assert.doesNotMatch(html,/<img/);
 assert.match(html,/&lt;img/);
});
