import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createHandoff,createSystemHandoff,appendHandoff} from './agentPolicyHandoff.mjs';
import {assistantInput,generatedHandoff} from './policyAssistant.mjs';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const configurations=JSON.parse(readFileSync(new URL('./system-policy-configurations.json',import.meta.url)));
const catalogue=JSON.parse(readFileSync(new URL('./rq1-agent-templates.json',import.meta.url)));
const target={id:'agent-1',mode:'controlled',product:'dsh',resources:['/actual/project']};
function elements(tree){if(!tree||typeof tree!=='object')return [];return [tree,...[tree.props?.children].flat(Infinity).flatMap(elements)]}
async function harness(entry,exported='default'){
 const built=await build({entryPoints:[join(base,entry)],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
 const states=[],refs=[];let index=0,refIndex=0;const react={...React,useState:init=>{const i=index++;if(!(i in states))states[i]=typeof init==='function'?init():init;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v]},useRef:init=>{const i=refIndex++;return refs[i]||={current:init}},useEffect:()=>{}};
 const name=join(base,'.policy-redesign-test.cjs'),mod=new Module(name);mod.paths=Module._nodeModulePaths(base);const original=mod.require.bind(mod);mod.require=id=>id==='react'?react:original(id);mod._compile(built.outputFiles[0].text,name);
 return props=>{globalThis.document={activeElement:null};index=0;refIndex=0;return mod.exports[exported](props)};
}
test('templates open as a structured record table, with configuration deferred until a record is selected',async()=>{
 const render=await harness('AgentPolicyTemplates.jsx');let writes=0;const props={agents:[target],onHandoff:()=>writes++};let tree=render(props),nodes=elements(tree);
 assert.equal(nodes.filter(e=>e.type==='table').length,1);assert.equal(nodes.filter(e=>e.type==='tr').length,7);assert.equal(nodes.filter(e=>e.type==='form').length,0);
 const html=renderToStaticMarkup(tree);for(const field of ['策略名称 / 编号','匹配对象 / 操作','处置方式','适用范围'])assert.ok(html.includes(field));assert.doesNotMatch(html,/template-card/);
 nodes.find(e=>e.type==='button'&&e.props['aria-label']==='配置 敏感配置访问限制').props.onClick();tree=render(props);assert.ok(elements(tree).some(e=>e.props?.template?.id==='RQ1-ENV'));assert.equal(writes,0);
});
test('system configurations are explicit system candidates and cannot be imported as Agent templates',()=>{
 assert.equal(configurations.length,3);
 for(const t of configurations){const values=Object.fromEntries(t.parameters.map(p=>[p.key,p.value]));const candidate=createSystemHandoff(t,values,'test','system-draft',[{pattern:'**/node'}]);assert.equal(candidate.targetId,'system');assert.equal(appendHandoff({scope_id:'system',documents:[]},candidate,'system').length,1);assert.throws(()=>appendHandoff({scope_id:target.id,documents:[]},candidate,target.id));assert.throws(()=>createHandoff(t,values,'',target));}
 assert.throws(()=>createSystemHandoff(catalogue.templates[0],{}));
});
test('detail configuration uses the exact selected Agent resource, resets parameters when target changes and writes only on submit',async()=>{
 const render=await harness('PolicyTemplateDetail.jsx'),other={...target,id:'agent-2',resources:['/other/project']};let candidate=null;
 const props={template:catalogue.templates[0],agents:[target,other],targetId:target.id,onHandoff:c=>candidate=c};let tree=render(props);
 assert.equal(candidate,null);let nodes=elements(tree);assert.ok(nodes.some(e=>e.type==='input'&&e.props.value==='/actual/project/.env'));
 nodes.find(e=>e.type==='select').props.onChange({target:{value:other.id}});tree=render(props);nodes=elements(tree);assert.ok(nodes.some(e=>e.type==='input'&&e.props.value==='/other/project/.env'));
 await nodes.find(e=>e.type==='form').props.onSubmit({preventDefault(){}});assert.equal(candidate.targetId,other.id);assert.ok(candidate.document.original_dsl.includes('/other/project/.env'));
});
test('Agent assistant has a conversation and one composer, without a duplicated template table or write on mount',async()=>{
 const render=await harness('AgentPolicyAssistant.jsx');let calls=[];const props={target,api:async()=>{throw Error('not used on initial view')},post:async(path,body)=>{calls.push({path,body});return path.endsWith('/inputs')?{id:'input-one'}:{id:'run-one',status:'queued'}}};let tree=render(props),nodes=elements(tree);
 assert.equal(nodes.filter(e=>e.type==='table').length,0);assert.equal(nodes.filter(e=>e.type==='textarea').length,1);assert.equal(calls.length,0);
 nodes.find(e=>e.type==='textarea').props.onChange({target:{value:'保护一个明确指定的文件'}});tree=render(props);await elements(tree).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
 assert.deepEqual(calls.map(c=>c.path),['/api/history/inputs','/api/history/generations']);assert.equal(calls[0].body.text,'保护一个明确指定的文件');assert.equal(calls[0].body.context_requirement,'self_contained');assert.doesNotMatch(calls[0].body.text,/agent_id|resources|verified_task_environment/);assert.equal(calls[1].body.statement_version_id,'input-one');assert.ok(calls.every(c=>!c.path.includes('/confirm')&&!c.path.includes('/review')));
});
test('assistant rejects observed targets and missing DSL, while generated DSL remains an exact-target unapplied handoff',()=>{
 assert.throws(()=>assistantInput('保护敏感配置', {...target,mode:'observed'}));assert.throws(()=>generatedHandoff({},target));
 const result={artifact:{actplane_dsl:'rule generated:\n  block open file "/actual/project/.env" if AGENT\n  because "Use sample"'},record:{statement:{text_zh:'保护敏感配置',context_requirement:'project'}}};
 const candidate=generatedHandoff(result,target,'generated');assert.equal(candidate.targetId,target.id);assert.equal(candidate.scopeType,'agent');assert.ok(candidate.document.original_dsl.startsWith('source AGENT'));assert.ok(candidate.document.metadata.generated.statement);assert.throws(()=>appendHandoff({scope_id:'agent-2',documents:[]},candidate,'agent-2'));
});

test('conversation template selection creates a local exact-Agent candidate, can be edited, and never saves or applies on selection',async()=>{
 const render=await harness('AgentPolicyAssistant.jsx');let writes=0,imported=null;
 const props={target,post:async()=>writes++,onHandoff:c=>imported=c};
 let tree=render(props),nodes=elements(tree);
 nodes.find(e=>e.type==='select'&&e.props['aria-label']==='选择策略').props.onChange({target:{value:'RQ1-ENV'}});
 tree=render(props);const panel=elements(tree).find(e=>e.props?.conversation===true);assert.ok(panel);assert.equal(panel.props.targetId,target.id);assert.equal(writes,0);
 const candidate=createHandoff(catalogue.templates[0],{target:'/actual/project/.env'},'',target,'chat-draft');candidate.presentation={name:candidate.document.name,template:catalogue.templates[0],values:{target:'/actual/project/.env'},operation:'open',effect:'block',reason:'Use sample'};
 panel.props.onHandoff(candidate);tree=render(props);nodes=elements(tree);
 assert.ok(nodes.some(e=>e.type==='strong'&&e.props.children===candidate.document.name));assert.equal(writes,0);assert.equal(imported,null);
 nodes.find(e=>e.type==='button'&&e.props.children==='检查并导入 →').props.onClick();assert.equal(imported.targetId,target.id);assert.match(imported.document.original_dsl,/source AGENT = exec "\*\*\/node"/);assert.equal(writes,0);
 nodes.find(e=>e.type==='button'&&e.props.children==='调整配置').props.onClick();tree=render(props);assert.equal(elements(tree).find(e=>e.props?.conversation===true).props.initialCandidate.id,'chat-draft');
});

test('follow-up generation receives the selected candidate configuration as context, without pretending it is approved or verified',()=>{
 const payload=assistantInput('改为只提醒，保留相同路径',target,[{kind:'template',text:'配置策略',candidate:{presentation:{name:'敏感文件保护',values:{target:'/actual/project/.env'},operation:'open',effect:'block',reason:'Use sample'}}}]);
 assert.match(payload.text,/\/actual\/project\/\.env/);assert.match(payload.text,/尚未应用/);assert.ok(payload.text.startsWith('改为只提醒'));assert.doesNotMatch(payload.text,/agent_id|verified_task_environment/);
});
