import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const nodes=t=>t&&typeof t==='object'?[t,...[t.props?.children].flat(Infinity).flatMap(nodes)]:[];
async function harness(entry,initial=[],exportName='default'){
 const built=await build({entryPoints:[join(base,entry)],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const states=[...initial],refs=[];let index=0,ref=0;
 const react={...React,useEffect:()=>{},useState:init=>{const n=index++;if(!(n in states))states[n]=typeof init==='function'?init():init;return [states[n],v=>states[n]=typeof v==='function'?v(states[n]):v]},useRef:init=>refs[ref++]||={current:init}};
 const mod=new Module(join(base,'.unified-catalog-test.cjs'));mod.paths=Module._nodeModulePaths(base);const original=mod.require.bind(mod);mod.require=id=>id==='react'?react:original(id);mod._compile(built.outputFiles[0].text,join(base,'.unified-catalog-test.cjs'));
 return props=>{globalThis.document={activeElement:null};index=0;ref=0;return mod.exports[exportName](props);};
}
const template={id:'FILE-READ',version:2,name:'文件读取限制',category:'文件保护',scopes:['system','agent'],parameters:[],operation:'open',effect:'block'};
const child={id:'tc_a',template_id:'FILE-READ',template_version:2,name:'禁止日报读取员工资料',scope_id:'a',scope:'agent',revision:1,parameters:{},status:'draft',can_submit:true};
test('old templates URL resolves to one policy page without a second assistant or library',async()=>{
 const render=await harness('SystemWorkbench.jsx');const tree=render({api(){},post(){},navigation:{systemTab:'templates'},navigate(){}}),all=nodes(tree);
 assert.equal(all.filter(n=>n.props?.role==='tab').length,2);
 assert.equal(all.filter(n=>n.type?.name==='UnifiedPolicyLibrary').length,1);
 assert.ok(!all.some(n=>['AgentPolicyTemplates','TemplatePolicyAssistant'].includes(n.type?.name)));
});
test('child records expose actual name scope and the shared template detail',async()=>{
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]);
 const props={api(){},post(){},agents:[{id:'a',agent_type:'dsh',mode:'controlled'}],onApprovals(){}};
 let tree=render(props);const table=nodes(tree).find(n=>n.type==='table'&&n.props['aria-label']==='文件读取限制 的子配置');
 assert.equal(nodes(table).filter(n=>n.type==='th').length,3);
 nodes(table).find(n=>n.type==='button'&&n.props.children==='详情 / 编辑 ↗').props.onClick();tree=render(props);
 const editor=nodes(tree).find(n=>n.type?.name==='TemplateConfigurationDialog');assert.equal(editor.props.item.name,child.name);assert.equal(editor.props.template.id,template.id);
});
test('batch submit freezes selected instance and never approves or loads on its own',async()=>{
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]),calls=[];
 const props={agents:[{id:'a',agent_type:'dsh',mode:'controlled'}],api:async()=>({revision:3,document_hash:'a'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'proposal',state:'pending'};},onApprovals:id=>calls.push({opened:id})};
 let tree=render(props);nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='选择 '+child.name).props.onChange();tree=render(props);
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='校验并提交审批 →').props.onClick();tree=render(props);
 await nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog').props.onConfirm();
 assert.equal(calls[0].path,'/api/policy-template-configurations/proposals');assert.equal(calls[0].body.scope_id,'a');assert.deepEqual(calls[0].body.selections,[{id:'tc_a',revision:1}]);assert.equal(calls[1].opened,'proposal');assert.ok(calls.every(c=>!c.path||!/(approve|apply|confirm)$/.test(c.path)));
});
test('shared mutation access requires an explicit acknowledgement before submission',async()=>{
 const covered={...child,coverage_warning:'修改与删除共用访问组'};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[covered]},{catalog:[],items:[]}]),calls=[];
 const props={agents:[],api:async()=>({revision:1,document_hash:'a'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'p',state:'pending'};},onApprovals(){}};
 let tree=render(props);nodes(tree).find(n=>n.props?.['aria-label']==='选择 '+child.name).props.onChange();tree=render(props);
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='校验并提交审批 →').props.onClick();tree=render(props);
 let confirm=nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog');assert.equal(confirm.props.confirmDisabled,true);
 await confirm.props.onConfirm();assert.equal(calls.length,0);
 nodes(tree).find(n=>n.props?.['aria-label']==='接受修改与删除的共同覆盖').props.onChange({target:{checked:true}});tree=render(props);
 confirm=nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog');assert.equal(confirm.props.confirmDisabled,false);
 await confirm.props.onConfirm();assert.equal(calls[0].body.acknowledge_coverage,true);
});
test('legacy system review navigates to approvals without calling confirmation or application',async()=>{
 const render=await harness('SecurityConfiguration.jsx',[{policy:{network:'disabled',rules:[]},proposals:[],phase:'ready'}],'SystemSecurityConfiguration'),calls=[];
 const tree=render({api(){},post:()=>calls.push('write'),onApprovals:id=>calls.push(id)});
 const rules=nodes(tree).find(n=>n.type?.name==='SystemSecurityRules');
 await rules.props.onConfirm({id:'pending-policy'});
 assert.deepEqual(calls,['pending-policy']);
});
