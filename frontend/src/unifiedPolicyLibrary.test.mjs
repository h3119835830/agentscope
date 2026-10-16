import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {configurationRecordSummary,configurationRecordActions} from './policyConfigurationPresentation.mjs';
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
test('child records expose six fields and retain the shared template detail',async()=>{
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]);
 const props={api(){},post(){},agents:[{id:'a',agent_type:'dsh',mode:'controlled'}],onApprovals(){}};
 let tree=render(props);const table=nodes(tree).find(n=>n.type==='table'&&n.props['aria-label']==='文件读取限制 的子配置');
 assert.deepEqual(nodes(table).filter(n=>n.type==='th').map(n=>n.props.children),['实际策略名称','范围','保护对象 / 操作','动作','状态','操作']);
 nodes(table).find(n=>n.type==='button'&&n.props.children==='详情 ↗').props.onClick();tree=render(props);
 const editor=nodes(tree).find(n=>n.type?.name==='TemplateConfigurationDialog');assert.equal(editor.props.item.name,child.name);assert.equal(editor.props.template.id,template.id);
});
test('row submit freezes this child and exact Agent without opening the detail or granting approval',async()=>{
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]),calls=[];
 const props={api:async()=>({revision:4,document_hash:'b'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'row-proposal',state:'pending'};},onApprovals:id=>calls.push({opened:id})};
 let tree=render(props);nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：提交审批').props.onClick();tree=render(props);
 assert.ok(!nodes(tree).some(n=>n.type?.name==='TemplateConfigurationDialog'));assert.equal(calls.length,0);
 const dialog=nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog');assert.equal(dialog.props.confirmLabel,'提交审批');await dialog.props.onConfirm();
 assert.equal(calls[0].path,'/api/policy-template-configurations/proposals');assert.equal(calls[0].body.operation,'apply');assert.equal(calls[0].body.scope_id,'a');assert.deepEqual(calls[0].body.selections,[{id:child.id,revision:1}]);assert.deepEqual(calls[1],{opened:'row-proposal'});
});
test('view approval uses the exact linked ID and never performs a write',async()=>{
 const row={...child,status:'pending',approval_id:'approval-exact',approval_revision:1,approval_current:true};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[row]},{catalog:[],items:[]}]),calls=[];
 const tree=render({api(){},post:()=>calls.push('write'),onApprovals:id=>calls.push(id)});
 assert.equal(nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：提交审批').props.disabled,true);
 nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：查看审批').props.onClick();assert.deepEqual(calls,['approval-exact']);
});
test('disable row previews the applied version, preserves draft binding and only submits a removal candidate',async()=>{
 const row={...child,revision:2,applied_revision:1,applied:false,parameters:{target:'/w/0/new-draft'},effect:'notify',applied_configuration:{name:'已应用员工资料保护',parameters:{target:'/w/0/staff.csv'},effective_operations:['open'],effect:'block'}};
 const def={...template,parameters:[{key:'target',type:'path'}]};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[def],items:[row]},{catalog:[],items:[]}]),calls=[];
 const props={api:async()=>({revision:7,document_hash:'c'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'off-proposal',state:'pending'};},onApprovals:id=>calls.push({opened:id})};
 let tree=render(props);nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：停用').props.onClick();tree=render(props);
 let dialog=nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog');assert.equal(dialog.props.title,'提交停用审批');assert.equal(calls.length,0);
 const text=nodes(dialog).flatMap(n=>[n.props?.children].flat(Infinity).filter(v=>typeof v==='string')).join(' ');assert.match(text,/staff\.csv/);assert.ok(!text.includes('/w/0/new-draft'));assert.match(text,/新版本草案保留/);
 dialog.props.onClose();assert.equal(calls.length,0);tree=render(props);assert.ok(!nodes(tree).some(n=>n.type?.name==='PolicyLifecycleDialog'));
 nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：停用').props.onClick();tree=render(props);dialog=nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog');await dialog.props.onConfirm();
 assert.equal(calls[0].body.operation,'disable');assert.equal(calls[0].body.scope_id,'a');assert.deepEqual(calls[0].body.selections,[{id:row.id,revision:2}]);assert.deepEqual(calls[1],{opened:'off-proposal'});assert.ok(calls.every(c=>!c.path||!/(approve|confirm|apply|disable)$/.test(c.path)));
});
test('legacy system rows expose exact approval and removal controls without changing scope',async()=>{
 const row={id:'legacy',name:'全局凭据保护',revision:2,applied:true,has_changes:true,applied_revision:1,approval_id:'legacy-receipt',approval_revision:1,approval_current:false,status:'library',config:{template_id:'env',values:'.env',ops:['open'],effect:'notify'}};
 const def={...template,id:'SYS-env'};const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[def],items:[]},{catalog:[],items:[row]}]),calls=[];
 const props={api:async()=>({revision:1,document_hash:'d'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'legacy-off',state:'pending'};},onApprovals:id=>calls.push({opened:id})};
 let tree=render(props);const view=nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：查看审批');assert.equal(view.props.disabled,false);assert.match(view.props.title,/v1/);
 nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：停用').props.onClick();tree=render(props);await nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog').props.onConfirm();assert.equal(calls[0].body.scope_id,'system');assert.equal(calls[0].body.operation,'disable');
});
test('unapplied unsupported and in-flight rows cannot offer misleading lifecycle actions',()=>{
 assert.equal(configurationRecordActions(child).canDisable,false);
 assert.equal(configurationRecordActions({...child,scope:'workspace',applied_revision:1}).canDisable,false);
 for(const status of ['pending','approved','applying']){const state=configurationRecordActions({...child,status,applied_revision:1,approval_current:true});assert.equal(state.canSubmit,false);assert.equal(state.canDisable,false);}
 assert.equal(configurationRecordActions({...child,applied:true,applied_revision:1}).canSubmit,false);
 assert.equal(configurationRecordActions({...child,applied:true,applied_revision:1}).canDisable,true);
});
test('legacy child action and target come from saved configuration, not parent defaults',()=>{
 const row={legacy:true,config:{values:'.ssh/id_rsa\n.ssh/id_ed25519',ops:['open'],effect:'notify'},applied:false};
 const summary=configurationRecordSummary(row,{...template,parameters:[{key:'values',type:'lines'}]});
 assert.deepEqual(summary.effects,['notify']);assert.equal(summary.target,'.ssh/id_rsa 等 2 项');assert.equal(summary.targetTitle,'.ssh/id_rsa\n.ssh/id_ed25519');assert.equal(summary.operation,'打开文件');assert.equal(summary.status,'未应用');
});
test('actual child parameters preserve multi-condition context and effective operation coverage',()=>{
 const definition={...template,parameters:[{key:'target',label:'限制范围',type:'path'},{key:'exception',label:'允许范围',type:'path'}]};
 const summary=configurationRecordSummary({...child,parameters:{target:'/w/0/a,b',exception:'/w/0/reports'},effective_operations:['write','unlink']},definition);
 assert.equal(summary.target,'限制范围：/w/0/a,b 等 2 项');assert.equal(summary.targetTitle,'限制范围：/w/0/a,b\n允许范围：/w/0/reports');assert.equal(summary.operation,'写入、删除');
});
test('approval and historical application never masquerade as current application or kernel enforcement',()=>{
 assert.equal(configurationRecordSummary({...child,status:'approved'},template).status,'已批准待应用');
 const old=configurationRecordSummary({...child,revision:2,applied_revision:1,applied:false,status:'pending'},template);
 assert.equal(old.status,'待审批');assert.equal(old.note,'旧版仍应用');
 assert.equal(configurationRecordSummary({...child,status:'applied',applied:false},template).status,'未应用');
 assert.equal(configurationRecordSummary({...child,status:'applied',applied:true,applied_revision:1},template).status,'已应用配置');
 assert.equal(configurationRecordSummary({legacy:true,applied:true,has_changes:true,revision:2,applied_revision:1}).status,'有未应用修改');
});
test('raw DSL without a structured projection stays unknown while mixed record effects are preserved',()=>{
 const row={legacy:true,document:{original_dsl:'unparsed DSL'},config:{}};
 const summary=configurationRecordSummary(row,{custom:true});
 assert.equal(summary.target,'查看详情');assert.equal(summary.operation,'操作见详情');assert.deepEqual(summary.effects,[]);
 assert.deepEqual(configurationRecordSummary({...row,records:[{effects:['notify','block']},{effect:'notify'}]},{custom:true}).effects,['notify','block']);
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
