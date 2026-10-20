import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import React from 'react';
import {materializeTemplate,createHandoff,appendHandoff,previewMatches,templateDefaults} from './agentPolicyHandoff.mjs';
import {readNavigation,navigationTarget} from './navigation.mjs';
const identity={generation:'gen-a',pid:55,start_ticks:'100',domain_id:99,host_id:'host',boot_id:'boot'};
const verifiedTarget=(id,type='dsh',executable='/opt/agentscope/bin/node')=>({id,mode:'controlled',agent_type:type,connected:true,...identity,policy_source:{ready:true,instance_id:id,...identity,pattern:'**/'+executable.split('/').at(-1),entry:'/opt/agent/launcher',executable,basis:'verified-process-executable'}});
const catalogue=JSON.parse(readFileSync(new URL('./rq1-agent-templates.json',import.meta.url),'utf8'));
const t=catalogue.templates[0],values={target:'/project/.env'},target=verifiedTarget('agent-one'),handoff=()=>createHandoff(t,values,'该项目的秘密配置',target,'draft-one');
test('all six curated candidates preserve evidence and do not inherit historical compilation',()=>{
 assert.equal(catalogue.verified_records,607);assert.equal(catalogue.templates.length,6);
 for(const item of catalogue.templates){assert.equal(item.scope_type,'agent');assert.equal(item.adapted_compile_status,'not_run');assert.ok(item.evidence.directive);assert.ok(item.caveat);const doc=materializeTemplate(item,Object.fromEntries(item.parameters.map(p=>[p.key,p.value])),'','d',[{pattern:'**/node'}]);assert.doesNotMatch(doc.original_dsl,/\{\{/);assert.ok(Object.keys(doc.metadata).length);}
});
test('template arguments reject unsupported quotes, backslashes, control, relative and traversal paths',()=>{
 assert.throws(()=>materializeTemplate(t,{target:'/project/"quote"'},'','d'),/引号/);
 assert.throws(()=>materializeTemplate(t,{target:'/project/\\file'},'','d'),/反斜杠/);
 for(const path of ['../.env','/project/../.env','/project/\n.env',''])assert.throws(()=>materializeTemplate(t,{target:path},'','d'));
});
test('handoff requires exact controlled target and cannot point to system or observed connections',()=>{
 for(const row of [null,{id:'system',mode:'controlled'},{id:'agent-one',mode:'observed'}])assert.throws(()=>createHandoff(t,values,'',row,'d'));
 const data={scope_id:target.id,documents:[]};for(const id of ['system','agent-two'])assert.throws(()=>appendHandoff(data,handoff(),id));
 assert.throws(()=>appendHandoff({...data,scope_id:'agent-two'},handoff(),target.id));
});
test('import appends to a fresh current snapshot without mutating or replacing existing documents',()=>{
 const data={scope_id:target.id,revision:7,document_hash:'current',documents:[{id:'existing',name:'保持原策略',original_dsl:'original',metadata:{}}]};
 const before=structuredClone(data),merged=appendHandoff(data,handoff(),target.id);
 assert.equal(merged.length,2);assert.deepEqual(merged[0],before.documents[0]);assert.deepEqual(data,before);merged[0].name='changed';assert.equal(data.documents[0].name,'保持原策略');
 assert.throws(()=>appendHandoff({...data,documents:merged},handoff(),target.id),/已存在/);
});
test('import enforces aggregate document and UTF8 byte limits',()=>{
 assert.throws(()=>appendHandoff({scope_id:target.id,documents:Array.from({length:20},(_,i)=>({id:String(i),original_dsl:'x'}))},handoff(),target.id),/20/);
 assert.throws(()=>appendHandoff({scope_id:target.id,documents:[{id:'old',original_dsl:'中'.repeat(17000)}]},handoff(),target.id),/50000/);
});
test('DSL or metadata edits and stale current revisions disable application',()=>{
 const docs=[handoff().document],checked=JSON.stringify(docs),pending={state:'pending'};
 assert.ok(previewMatches(pending,checked,docs));assert.ok(!previewMatches(pending,checked,docs,true));assert.ok(!previewMatches({state:'invalid'},checked,docs));
 for(const patch of [{original_dsl:'changed'},{metadata:{}}])assert.ok(!previewMatches(pending,checked,[{...docs[0],...patch}]));
});
test('new Agent/System aliases and scoped handoff routes retain browser-history and old generation links',()=>{
 assert.equal(readNavigation('http://localhost/?view=agent').page,'workbench');assert.equal(readNavigation('http://localhost/?view=system').page,'strategies');
 const href='http://localhost'+navigationTarget('http://localhost/?view=system',{page:'agent',policyAgent:target.id,agentPolicyTab:'policies'});
 const n=readNavigation(href);assert.equal(n.policyAgent,target.id);assert.equal(n.agentPolicyTab,'policies');assert.equal(readNavigation('http://localhost/?view=strategies&section=audit').systemTab,'generations');
 for(const tab of ['assistant','runtime','policies','loaded','workspaces'])assert.equal(readNavigation('http://localhost/?view=workbench&agentPolicyTab='+tab).agentPolicyTab,tab);
 assert.equal(readNavigation('http://localhost/?view=system&systemTab=unknown').systemTab,'policies');
});
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const built=await build({entryPoints:[join(base,'ActPlanePolicies.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
function editorHarness(){
 const states=[],refs=[];let index=0,refIndex=0;const react={...React,useState:init=>{const i=index++;if(!(i in states))states[i]=typeof init==='function'?init():init;return [states[i],value=>states[i]=typeof value==='function'?value(states[i]):value]},useRef:init=>{const i=refIndex++;return refs[i]||=( {current:init})},useEffect:()=>{}};
 const filename=join(base,'.editor-handoff-test.cjs'),mod=new Module(filename);mod.paths=Module._nodeModulePaths(base);const original=mod.require.bind(mod);mod.require=id=>id==='react'?react:original(id);mod._compile(built.outputFiles[0].text,filename);
 return props=>{index=0;refIndex=0;globalThis.document={activeElement:null};return mod.exports.DslEditor(props)};
}
function elements(tree){if(!tree||typeof tree!=='object')return [];return [tree,...[tree.props?.children].flat(Infinity).flatMap(elements)]}
function button(tree,label){return elements(tree).find(e=>e.type==='button'&&[e.props.children].flat(Infinity).filter(x=>typeof x==='string').join('').includes(label))}
test('real DSL editor opens a candidate without writes, only validates on click and hands off to approval on separate explicit click',async()=>{
 const render=editorHarness(),data={scope_id:target.id,documents:[{id:'old',name:'Old',original_dsl:'old',metadata:{}}],records:[]};let validates=0,applies=0;
 const props={data,seed:handoff(),onClose:()=>{},onValidate:async docs=>{validates++;assert.equal(docs.length,2);return {state:'pending',documents:docs,result:{},targets:[]}},onReview:async()=>{applies++}};
 let tree=render(props);assert.equal(validates,0);assert.equal(applies,0);assert.equal(elements(tree).find(e=>e.type==='textarea').props.value,handoff().document.original_dsl);assert.equal(button(tree,'前往审批'),undefined);
 await button(tree,'保存并校验').props.onClick();tree=render(props);assert.equal(validates,1);assert.equal(applies,0);assert.equal(button(tree,'前往审批').props.disabled,false);
 tree=render({...props,baseStale:true});assert.equal(button(tree,'前往审批').props.disabled,true);
 tree=render(props);elements(tree).find(e=>e.type==='textarea').props.onChange({target:{value:'edited'}});tree=render(props);assert.equal(button(tree,'前往审批').props.disabled,true);assert.equal(applies,0);
 await button(tree,'保存并校验').props.onClick();tree=render(props);await button(tree,'前往审批').props.onClick();assert.equal(validates,2);assert.equal(applies,1);
});

test('template defaults use the selected Agent real resource and reset when the target changes',()=>{
 assert.equal(templateDefaults(t,{resources:['/projects/one/']}).target,'/projects/one/.env');
 assert.equal(templateDefaults(t,{resources:['/projects/two']}).target,'/projects/two/.env');
 assert.equal(templateDefaults(t,{}).target,'/workspace/.env');
});
