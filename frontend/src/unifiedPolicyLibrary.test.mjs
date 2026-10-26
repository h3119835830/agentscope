import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {configurationRecordSummary,configurationRecordActions} from './policyConfigurationPresentation.mjs';
import {PRIMARY_TYPES,primaryType,primaryTypeLabel,templateFacets} from './policyTemplatePrimaryType.mjs';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const nodes=t=>t&&typeof t==='object'?[t,...[t.props?.children].flat(Infinity).flatMap(nodes)]:[];
async function harness(entry,initial=[],exportName='default'){
 const built=await build({entryPoints:[join(base,entry)],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const states=[...initial],refs=[];let index=0,ref=0;
 const react={...React,useEffect:()=>{},useState:init=>{const n=index++;if(!(n in states))states[n]=typeof init==='function'?init():init;return [states[n],v=>states[n]=typeof v==='function'?v(states[n]):v]},useRef:init=>refs[ref++]||={current:init}};
 const mod=new Module(join(base,'.unified-catalog-test.cjs'));mod.paths=Module._nodeModulePaths(base);const original=mod.require.bind(mod);mod.require=id=>id==='react'?react:original(id);mod._compile(built.outputFiles[0].text,join(base,'.unified-catalog-test.cjs'));
 return props=>{globalThis.document={activeElement:null};index=0;ref=0;return mod.exports[exportName](props);};
}
const template={description:'场景明确要求隔离无关资料时使用，填写目标路径，不额外禁止修改或删除。',id:'FILE-READ',version:2,name:'文件读取限制',category:'文件保护',scopes:['system','agent'],parameters:[],operation:'open',effect:'block'};
const child={id:'tc_a',template_id:'FILE-READ',template_version:2,name:'禁止日报读取员工资料',scope_id:'a',scope:'agent',revision:1,parameters:{},status:'draft',can_submit:true};
test('read-only template details show supplied defaults, allowed choices and the server preview without help metadata',async()=>{
 const definition={...template,name:'环境凭据文件',parameters:[{key:'values',label:'匹配对象（每行一个）',type:'lines',default:'.env'},{key:'operations',label:'触发操作',type:'operations',default:['open']},{key:'effect',label:'匹配后的动作',type:'effect',default:'notify'}],allowed_operations:['open','write','unlink'],dsl_preview:{state:'complete',dsl:'rule server-default:\n  block open file "**/*.env" if AGENT'},reason:'核对已登记的脱敏示例。'};
 const original=structuredClone(definition),render=await harness('TemplateDefinitionDialog.jsx',[],'TemplateDefinitionContent');
 const html=renderToStaticMarkup(render({template:definition}));
 for(const text of ['匹配对象（每行一个）','.env','打开文件','写入','删除','阻止并反馈','记录并提醒','终止违规进程','每行填写一项','反馈原因',definition.reason,'server-default'])assert.ok(html.includes(text),text);
 assert.ok(!/<(?:input|textarea|select|form)\b/.test(html));
 assert.match(html,/服务端提供的模板默认参数预览/);
 assert.deepEqual(definition,original);
});
test('template details preserve zero, empty defaults, fixed Git commands and explicit field guidance',async()=>{
 const definition={...template,fixed_fields:{program:'git',command:'commit'},allowed_effects:['notify','kill'],parameters:[{key:'target',label:'代码路径',type:'path',default:'',help:'此路径仅用于检查失效。'},{key:'exit',label:'成功退出码',type:'integer',default:0,minimum:0,maximum:255},{key:'tokens',label:'Git 操作',type:'choices',default:['reset','clean'],options:['reset','clean','stash']}],dsl_preview:{state:'incomplete',missing:['代码路径'],dsl:'rule placeholder:\n  notify exec "{{代码路径}}"'}};
 const render=await harness('TemplateDefinitionDialog.jsx',[],'TemplateDefinitionContent'),html=renderToStaticMarkup(render({template:definition}));
 for(const text of ['git commit','未设置，由子配置填写','此路径仅用于检查失效。','取值范围：0 ～ 255','reset、clean','reset、clean、stash','待填写：代码路径','双花括号表示尚未填写的参数'])assert.ok(html.includes(text),text);
 assert.match(html,/upl-template-default">0<\/div>/);
});
test('read-only DSL preview states distinguish missing data, invalid defaults and unsupported templates',async()=>{
 const render=await harness('TemplateDslPreview.jsx',[],'TemplateDslPreviewResult');
 for(const [result,message] of [[{state:'unavailable'},'尚未提供'],[{state:'unsupported'},'暂不支持此执行语义'],[{state:'invalid',errors:['默认值失效']},'模板默认参数未通过预览校验']]){
  const html=renderToStaticMarkup(render({result,readOnly:true}));assert.ok(html.includes(message));assert.ok(!html.includes('dsl-code'));
 }
 const content=await harness('TemplateDefinitionDialog.jsx',[],'TemplateDefinitionContent');
 const html=renderToStaticMarkup(content({template}));assert.ok(html.includes('没有可填写的配置项'));assert.ok(html.includes('尚未提供此模板的默认参数预览'));
});
test('three main groups follow the affected OS operation, not legacy category or scope',()=>{
 assert.deepEqual(PRIMARY_TYPES.map(type=>type.label),['文件与目录操作','程序与命令执行','网络连接']);
 for(const operation of ['open','read','write','unlink'])assert.equal(primaryType({operation,category:'跨事件保护'}),'file');
 assert.equal(primaryType({id:'GIT-COMMIT-CHECK',operation:'exec',category:'Git 操作'}),'exec');
 assert.equal(primaryType({id:'SYS-secret-egress',operation:'connect',category:'系统 · 跨事件保护'}),'network');
 assert.equal(primaryTypeLabel({operation:'exec'}),'程序与命令执行');
 assert.equal(primaryType({custom:true,operation:'exec'}),'');
 assert.equal(primaryTypeLabel({custom:true}),'自定义策略 · 操作见详情');
 assert.deepEqual(templateFacets({id:'SYS-secret-egress',operation:'connect',category:'系统 · 跨事件保护',execution_support:{event_type:'跨事件'}}),['系统预设','跨事件']);
});
test('system template selector offers only three main groups and preserves exact child scope',async()=>{
 const definitions=[
  template,
  {...template,id:'SYS-env',name:'环境凭据文件',category:'系统 · 凭据保护'},
  {...template,id:'GIT-COMMIT',name:'Git 提交执行约束',category:'Git 操作',operation:'exec'},
  {...template,id:'SECRET-EGRESS',name:'敏感资料外发限制',category:'跨事件保护',operation:'connect'},
 ];
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:definitions,items:[child]},{catalog:[],items:[]}]),writes=[];
 const props={api(){},post:()=>writes.push('write'),onApprovals(){}};
 let tree=render(props),selector=nodes(tree).find(n=>n.props?.['aria-label']==='策略主分类');
 assert.deepEqual(nodes(selector).filter(n=>n.type==='option').map(n=>n.props.children),['全部主分类',...PRIMARY_TYPES.map(type=>type.label)]);
 tree=templateDetails(render,props);
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']===child.name+'：提交审批'));
 selector.props.onChange({target:{value:'exec'}});tree=render(props);
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']==='Git 提交执行约束：详情'));
 assert.ok(!nodes(tree).some(n=>n.props?.['aria-label']==='环境凭据文件：详情'));
 selector=nodes(tree).find(n=>n.props?.['aria-label']==='策略主分类');selector.props.onChange({target:{value:'file'}});tree=render(props);
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']==='环境凭据文件：详情'));
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']===child.name+'：提交审批'));
 assert.deepEqual(writes,[]);
});
test('expanded catalogue has one add action and shares the policy record fields',async()=>{
 const def={...template,parameters:[{key:'target',label:'保护对象路径',type:'path'}]},item={...child,parameters:{target:'/w/0/only-in-details.txt'}};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[def],items:[item]},{catalog:[],items:[]}]),props={api(){},post(){},onApprovals(){}};
 let tree=templateDetails(render,props),all=nodes(tree);
 assert.equal(all.filter(n=>n.type==='button'&&n.props['aria-label']?.includes('新增子配置')).length,1);
 assert.ok(!all.some(n=>n.props?.className==='upl-child-target'));
 const table=all.find(n=>n.type==='table'&&n.props['aria-label']===template.name+' 的子配置');
 assert.equal(nodes(table).filter(n=>n.type==='th').length,9);
 const html=renderToStaticMarkup(tree);assert.match(html,/only-in-details.txt/);
 all.find(n=>n.props?.['aria-label']===child.name+'的详情').props.onClick();tree=render(props);
 assert.equal(nodes(tree).find(n=>n.type?.name==='TemplateConfigurationDialog').props.item.parameters.target,item.parameters.target);
});
function templateDetails(render,props,name=template.name){
 let tree=render(props);const button=nodes(tree).find(n=>n.props?.['aria-label']===name+'：子配置');
 if(!button.props['aria-expanded'])button.props.onClick();return render(props);
}
test('old templates URL resolves to one policy page without a second assistant or library',async()=>{
 const render=await harness('SystemWorkbench.jsx');const tree=render({api(){},post(){},navigation:{systemTab:'templates'},navigate(){}}),all=nodes(tree);
 assert.equal(all.filter(n=>n.props?.role==='tab').length,3);
 assert.deepEqual(all.filter(n=>n.props?.role==='tab').map(n=>n.props.children),['策略与配置','标签管理','生成记录']);
 assert.equal(all.filter(n=>n.type?.name==='UnifiedPolicyLibrary').length,1);
 assert.ok(!all.some(n=>['AgentPolicyTemplates','TemplatePolicyAssistant'].includes(n.type?.name)));
});
test('an Agent configuration link opens the unified System library at that exact scope',async()=>{
 const other={...child,id:'tc_b',scope_id:'b',name:'另一个 Agent 的配置'};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child,other]},{catalog:[],items:[]}]);
 const props={targetId:'a',agents:[{id:'a',agent_type:'dsh',mode:'controlled'},{id:'b',agent_type:'dsh',mode:'controlled'}],api(){},post(){},onApprovals(){}};
 let tree=render(props);assert.equal(nodes(tree).find(n=>n.props?.['aria-label']==='配置范围').props.value,'a');
 tree=templateDetails(render,props);assert.ok(nodes(tree).some(n=>n.props?.['aria-label']===child.name+'：提交审批'));assert.ok(!nodes(tree).some(n=>n.props?.['aria-label']===other.name+'：提交审批'));
});
test('exact Agent scope keeps legacy DSL management inside the unified System module',async()=>{
 const writes=[],agent={id:'a',agent_type:'dsh',mode:'controlled'};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]);
 const props={targetId:'a',agents:[agent],api(){},post:(...args)=>writes.push(args),onApprovals(){}};
 let tree=render(props);assert.ok(!nodes(tree).some(n=>n.type?.name==='ActPlanePolicies'));
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='管理 Agent DSL').props.onClick();tree=render(props);
 const manager=nodes(tree).find(n=>n.type?.name==='ActPlanePolicies');assert.equal(manager.props.scopeId,'a');assert.equal(manager.props.ownedOnly,true);assert.equal(writes.length,0);
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='收起').props.onClick();tree=render(props);assert.ok(!nodes(tree).some(n=>n.type?.name==='ActPlanePolicies'));
});
test('template catalogue omits parameter operation values and expands child fields only on the arrow',async()=>{
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]);
 const props={api(){},post(){},agents:[{id:'a',agent_type:'dsh',mode:'controlled'}],onApprovals(){}};
 let tree=render(props),table=nodes(tree).find(n=>n.type==='table'&&n.props['aria-label']==='策略模板目录');
 assert.deepEqual(nodes(table).filter(n=>n.type==='th').map(n=>[n.props.children].flat().find(v=>typeof v==='string')),['策略模板','说明','默认动作','子配置','操作']);
 assert.ok(!nodes(tree).some(n=>n.props?.['aria-label']===child.name+'：提交审批'));
 assert.ok(nodes(table).some(n=>n.type==='p'&&n.props.children===template.description));
 tree=templateDetails(render,props);table=nodes(tree).find(n=>n.type==='table'&&n.props['aria-label']==='文件读取限制 的子配置');
 assert.deepEqual(nodes(table).filter(n=>n.type==='th'&&!n.props.className?.includes('spl-check')).map(n=>n.props.children),['策略名称','作用范围','匹配对象','限制操作','触发条件','处置','状态','操作']);
 nodes(table).find(n=>n.props?.['aria-label']===child.name+'的详情').props.onClick();tree=render(props);
 const editor=nodes(tree).find(n=>n.type?.name==='TemplateConfigurationDialog');assert.equal(editor.props.item.name,child.name);assert.equal(editor.props.template.id,template.id);
});
test('row submit freezes this child and exact Agent without opening the detail or granting approval',async()=>{
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]),calls=[];
 const props={api:async()=>({revision:4,document_hash:'b'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'row-proposal',state:'pending'};},onApprovals:id=>calls.push({opened:id})};
 let tree=templateDetails(render,props);nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：提交审批').props.onClick();tree=render(props);
 assert.ok(!nodes(tree).some(n=>n.type?.name==='TemplateConfigurationDialog'));assert.equal(calls.length,0);
 const dialog=nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog');assert.equal(dialog.props.confirmLabel,'提交审批');await dialog.props.onConfirm();
 assert.equal(calls[0].path,'/api/policy-template-configurations/proposals');assert.equal(calls[0].body.operation,'apply');assert.equal(calls[0].body.scope_id,'a');assert.deepEqual(calls[0].body.selections,[{id:child.id,revision:1}]);assert.deepEqual(calls[1],{opened:'row-proposal'});
});
test('view approval uses the exact linked ID and never performs a write',async()=>{
 const row={...child,status:'pending',approval_id:'approval-exact',approval_revision:1,approval_current:true};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[row]},{catalog:[],items:[]}]),calls=[];
 const tree=templateDetails(render,{api(){},post:()=>calls.push('write'),onApprovals:id=>calls.push(id)});
 assert.equal(nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：提交审批').props.disabled,true);
 nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：查看审批').props.onClick();assert.deepEqual(calls,['approval-exact']);
});
test('disable row previews the applied version, preserves draft binding and only submits a removal candidate',async()=>{
 const row={...child,revision:2,applied_revision:1,applied:false,parameters:{target:'/w/0/new-draft'},effect:'notify',applied_configuration:{name:'已应用员工资料保护',parameters:{target:'/w/0/staff.csv'},effective_operations:['open'],effect:'block'}};
 const def={...template,parameters:[{key:'target',type:'path'}]};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[def],items:[row]},{catalog:[],items:[]}]),calls=[];
 const props={api:async()=>({revision:7,document_hash:'c'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'off-proposal',state:'pending'};},onApprovals:id=>calls.push({opened:id})};
 let tree=templateDetails(render,props);nodes(tree).find(n=>n.props?.['aria-label']===child.name+'：停用').props.onClick();tree=render(props);
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
 let tree=templateDetails(render,props);const view=nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：查看审批');assert.equal(view.props.disabled,false);assert.match(view.props.title,/v1/);
 nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：停用').props.onClick();tree=render(props);await nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog').props.onConfirm();assert.equal(calls[0].body.scope_id,'system');assert.equal(calls[0].body.operation,'disable');
});
test('unapplied unsupported and in-flight rows cannot offer misleading lifecycle actions',()=>{
 assert.equal(configurationRecordActions(child).canDisable,false);
 assert.equal(configurationRecordActions({...child,scope:'workspace',applied_revision:1}).canDisable,false);
 for(const status of ['pending','approved','applying']){const state=configurationRecordActions({...child,status,applied_revision:1,approval_current:true});assert.equal(state.canSubmit,false);assert.equal(state.canDisable,false);}
 assert.equal(configurationRecordActions({...child,applied:true,applied_revision:1}).canSubmit,false);
 assert.equal(configurationRecordActions({...child,applied:true,applied_revision:1}).canDisable,true);
});
test('delete is available for unused rejected drafts, never for any still-applied version',()=>{
 for(const status of ['draft','rejected','invalid','failed','stale']){
  assert.equal(configurationRecordActions({...child,status}).canDelete,true);
 }
 for(const status of ['pending','approved','applying']){
  const controls=configurationRecordActions({...child,status,approval_current:true});
  assert.equal(controls.canDelete,false);assert.match(controls.deleteReason,/审批/);
 }
 for(const applied of [{applied_revision:1},{applied:true},{has_applied_document:true}]){
  const controls=configurationRecordActions({...child,revision:2,status:'rejected',...applied});
  assert.equal(controls.canDelete,false);assert.equal(controls.hasApplied,true);assert.match(controls.deleteReason,/停用/);
 }
 assert.equal(configurationRecordActions({...child,scope:'workspace'}).canDelete,false);
 assert.equal(configurationRecordActions({...child,archived:1}).canDelete,false);
 assert.equal(configurationRecordActions({...child,can_submit:false,read_only:true}).canDelete,true);
});
test('unused child deletion requires confirmation and archives only the exact selected version',async()=>{
 const row={...child,status:'rejected',approval_id:'old-approval'};
 const other={...row,id:'tc_other',scope_id:'b',name:'另一目标'};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[row,other]},{catalog:[],items:[]}]),calls=[];
 const props={targetId:'a',api:async()=>({catalog:[],items:[]}),post:async(path,body)=>{calls.push({path,body});return {id:row.id,archived:true};},onApprovals:()=>calls.push('approval')};
 let tree=templateDetails(render,props);
 assert.ok(!nodes(tree).some(n=>n.props?.['aria-label']===row.name+'：停用'));
 assert.equal(nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：删除').props.disabled,false);
 nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：删除').props.onClick();tree=render(props);
 let dialog=nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog');
 assert.equal(dialog.props.title,'删除子配置');assert.equal(calls.length,0);
 assert.match(nodes(dialog).flatMap(n=>[n.props?.children].flat(Infinity).filter(v=>typeof v==='string')).join(' '),/历史版本、审批和应用记录保留/);
 dialog.props.onClose();tree=render(props);assert.equal(calls.length,0);
 nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：删除').props.onClick();tree=render(props);
 await nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog').props.onConfirm();
 assert.deepEqual(calls,[{path:'/api/policy-template-configurations/tc_a/archive',body:{revision:1}}]);
 assert.ok(!nodes(render(props)).some(n=>n.type?.name==='PolicyLifecycleDialog'));
});
test('legacy rejected child uses its existing archival endpoint and shows errors without hiding the record',async()=>{
 const row={id:'legacy',name:'全局凭据保护',revision:2,applied:false,status:'rejected',config:{template_id:'env',values:'.env',ops:['open'],effect:'notify'}};
 const def={...template,id:'SYS-env'};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[def],items:[]},{catalog:[],items:[row]}]),calls=[];
 const props={api(){},post:async(path,body)=>{calls.push({path,body});throw Error('请先停用当前已应用策略');},onApprovals(){}};
 let tree=templateDetails(render,props);
 nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：删除').props.onClick();tree=render(props);
 await nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog').props.onConfirm();tree=render(props);
 assert.deepEqual(calls,[{path:'/api/security/system/policy-library/legacy/archive',body:{revision:2}}]);
 assert.ok(nodes(tree).some(n=>n.type?.name==='PolicyLifecycleDialog'));
 assert.ok(nodes(tree).some(n=>n.props?.role==='alert'&&n.props.children==='请先停用当前已应用策略'));
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']===row.name+'：删除'));
});
test('a rejected new version with an applied old version offers disable, not deletion',async()=>{
 const row={...child,revision:2,status:'rejected',applied:false,applied_revision:1};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[row]},{catalog:[],items:[]}]);
 const tree=templateDetails(render,{api(){},post(){},onApprovals(){}});
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']===row.name+'：停用'));
 assert.ok(!nodes(tree).some(n=>n.props?.['aria-label']===row.name+'：删除'));
});
test('legacy child action and target come from saved configuration, not parent defaults',()=>{
 const row={legacy:true,configuration_status:{state:'draft',label:'草案'},config:{values:'.ssh/id_rsa\n.ssh/id_ed25519',ops:['open'],effect:'notify'},applied:false};
 const summary=configurationRecordSummary(row,{...template,parameters:[{key:'values',type:'lines'}]});
 assert.deepEqual(summary.effects,['notify']);assert.equal(summary.target,'.ssh/id_rsa 等 2 项');assert.equal(summary.targetTitle,'.ssh/id_rsa\n.ssh/id_ed25519');assert.equal(summary.operation,'打开文件');assert.equal(summary.status,'草案');
});
test('actual child parameters preserve multi-condition context and effective operation coverage',()=>{
 const definition={...template,parameters:[{key:'target',label:'限制范围',type:'path'},{key:'exception',label:'允许范围',type:'path'}]};
 const summary=configurationRecordSummary({...child,parameters:{target:'/w/0/a,b',exception:'/w/0/reports'},effective_operations:['write','unlink']},definition);
 assert.equal(summary.target,'限制范围：/w/0/a,b 等 2 项');assert.equal(summary.targetTitle,'限制范围：/w/0/a,b\n允许范围：/w/0/reports');assert.equal(summary.operation,'写入、删除');
});
test('approval and historical application never masquerade as current application or kernel enforcement',()=>{
 assert.equal(configurationRecordSummary({...child,status:'approved',configuration_status:{state:'approved',label:'待应用'}},template).status,'待应用');
 const old=configurationRecordSummary({...child,revision:2,applied_revision:1,applied:false,status:'pending',configuration_status:{state:'pending',label:'待审批'}},template);
 assert.equal(old.status,'待审批');assert.equal(old.note,'旧版仍应用');
 assert.equal(configurationRecordSummary({...child,status:'applied',applied:false},template).status,'状态待核验');
 assert.equal(configurationRecordSummary({...child,status:'applied',applied:true,applied_revision:1,configuration_status:{state:'applied',label:'已应用'}},template).status,'已应用');
 assert.equal(configurationRecordSummary({legacy:true,applied:true,has_changes:true,revision:2,applied_revision:1,configuration_status:{state:'draft',label:'草案'}}).status,'草案');
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
 let tree=templateDetails(render,props);nodes(tree).find(n=>n.type==='input'&&n.props['aria-label']==='选择 '+child.name).props.onChange();tree=render(props);
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='校验并提交审批 →').props.onClick();tree=render(props);
 await nodes(tree).find(n=>n.type?.name==='PolicyLifecycleDialog').props.onConfirm();
 assert.equal(calls[0].path,'/api/policy-template-configurations/proposals');assert.equal(calls[0].body.scope_id,'a');assert.deepEqual(calls[0].body.selections,[{id:'tc_a',revision:1}]);assert.equal(calls[1].opened,'proposal');assert.ok(calls.every(c=>!c.path||!/(approve|apply|confirm)$/.test(c.path)));
});
test('shared mutation access requires an explicit acknowledgement before submission',async()=>{
 const covered={...child,coverage_warning:'修改与删除共用访问组'};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[covered]},{catalog:[],items:[]}]),calls=[];
 const props={agents:[],api:async()=>({revision:1,document_hash:'a'.repeat(64)}),post:async(path,body)=>{calls.push({path,body});return {id:'p',state:'pending'};},onApprovals(){}};
 let tree=templateDetails(render,props);nodes(tree).find(n=>n.props?.['aria-label']==='选择 '+child.name).props.onChange();tree=render(props);
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

test('description search finds a template and preserves its scoped children',async()=>{
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[child]},{catalog:[],items:[]}]);const props={api(){},post(){},onApprovals(){}};
 let tree=render(props);nodes(tree).find(n=>n.props?.['aria-label']==='搜索系统策略').props.onChange({target:{value:'隔离无关资料'}});tree=render(props);
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']===template.name+'：详情'));tree=templateDetails(render,props);
 assert.ok(nodes(tree).some(n=>n.props?.['aria-label']===child.name+'：提交审批'));
});
test('the arrow expands children while details exclusively opens the template editor',async()=>{
 const def={...template,parameters:[{key:'target',label:'保护对象路径',type:'path',default:''}]};const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[def],items:[]},{catalog:[],items:[]}]);
 const props={api(){},post(){},onApprovals(){}};let tree=render(props);
 const toggle=()=>nodes(tree).find(n=>n.props?.['aria-label']===template.name+'：子配置');
 const arrow=()=>nodes(toggle()).find(n=>n.props?.className==='upl-catalog-chevron');
 assert.equal(toggle().props['aria-expanded'],false);assert.equal(arrow().props.children,'▸');
 toggle().props.onClick();tree=render(props);
 assert.equal(toggle().props['aria-expanded'],true);assert.equal(arrow().props.children,'▾');
 assert.ok(!nodes(tree).some(n=>n.props?.className==='upl-template-description'||n.props?.className==='upl-parameter-schema'));
 assert.equal(nodes(tree).filter(n=>n.type==='p'&&n.props.children===template.description).length,1);
 assert.ok(nodes(tree).some(n=>n.type==='td'&&n.props.children==='暂无子配置，新增后可在此查看、提交审批或停用。'));
 nodes(tree).find(n=>n.props?.['aria-label']===template.name+'：详情').props.onClick();tree=render(props);
 assert.equal(toggle().props['aria-expanded'],true);
 const editor=nodes(tree).find(n=>n.type?.name==='TemplateDefinitionDialog');assert.equal(editor.props.template.id,template.id);editor.props.onClose();tree=render(props);
 toggle().props.onClick();tree=render(props);
 assert.equal(toggle().props['aria-expanded'],false);assert.equal(arrow().props.children,'▸');
 assert.ok(!nodes(tree).some(n=>n.props?.className==='upl-template-detail'));
});

test('column drag changes only its column, clamps widths and stops at release without policy writes',async()=>{
 const initial=[{catalog:[template],items:[child]},{catalog:[],items:[]}],render=await harness('UnifiedPolicyLibrary.jsx',initial),writes=[];
 const props={api(){},post:()=>writes.push('write'),onApprovals(){}};let tree=render(props),captured=false;
 const handle=()=>nodes(tree).find(n=>n.props?.['aria-label']==='调整说明列宽');
 const widths=()=>nodes(tree).filter(n=>n.type==='col').map(n=>n.props.style.width);
 const defaults=widths(),target={focus(){},setPointerCapture(){captured=true},hasPointerCapture(){return captured},releasePointerCapture(){captured=false}};
 const event={button:0,pointerId:7,clientX:500,currentTarget:target,preventDefault(){},stopPropagation(){}};
 handle().props.onPointerDown({...event,button:2});handle().props.onPointerMove({...event,clientX:640});tree=render(props);assert.deepEqual(widths(),defaults);
 handle().props.onPointerDown(event);handle().props.onPointerMove({...event,pointerId:8,clientX:640});tree=render(props);assert.deepEqual(widths(),defaults);
 handle().props.onPointerMove({...event,clientX:640});tree=render(props);assert.deepEqual(widths(),defaults.map((w,i)=>i===1?w+140:w));
 handle().props.onPointerMove({...event,clientX:590});tree=render(props);assert.equal(widths()[1],390);
 handle().props.onPointerMove({...event,clientX:-500});tree=render(props);assert.equal(widths()[1],180);
 handle().props.onPointerUp(event);handle().props.onPointerMove({...event,clientX:2000});tree=render(props);assert.equal(widths()[1],180);assert.equal(captured,false);
 handle().props.onKeyDown({key:'ArrowRight',preventDefault(){}});tree=render(props);assert.equal(widths()[1],190);assert.deepEqual(writes,[]);
 nodes(tree).find(n=>n.type==='button'&&n.props.children==='刷新').props.onClick();tree=render(props);assert.deepEqual(widths(),defaults);
 const reloaded=await harness('UnifiedPolicyLibrary.jsx',initial);tree=reloaded(props);assert.deepEqual(widths(),defaults);
});

 test('template editor saves a template version with synchronized effect defaults, never a child or application',async()=>{
 const def={...template,parameters:[{key:'target',label:'保护对象',type:'path',default:''},{key:'effect',label:'动作',type:'effect',default:'block'}]};
 const render=await harness('TemplateDefinitionDialog.jsx'),calls=[],props={template:def,post:async(path,body)=>{calls.push({path,body});return {version:3}},onClose:()=>calls.push('close'),onSaved:value=>calls.push({saved:value})};let tree=render(props);
 assert.ok(!nodes(tree).some(n=>n.type==='form'));nodes(tree).find(n=>n.type==='button'&&n.props.children==='维护模板').props.onClick();tree=render(props);
 nodes(tree).find(n=>n.props?.['aria-label']==='模板名称').props.onChange({target:{value:'新模板名称'}});tree=render(props);
 nodes(tree).find(n=>n.props?.['aria-label']==='target 配置项名称').props.onChange({target:{value:'资料路径'}});tree=render(props);
 nodes(tree).find(n=>n.props?.['aria-label']==='模板默认动作').props.onChange({target:{value:'notify'}});tree=render(props);
 await nodes(tree).find(n=>n.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls[0].path,'/api/policy-templates/FILE-READ/versions');assert.equal(calls[0].body.base_version,2);assert.equal(calls[0].body.effect,'notify');assert.equal(calls[0].body.parameters[1].default,'notify');assert.equal(calls[0].body.parameters[0].label,'资料路径');assert.equal(calls[0].body.name,'新模板名称');assert.deepEqual(calls[1],{saved:{version:3}});
 assert.ok(!('scope_id' in calls[0].body));
 });

test('a saved policy approval link retains its configuration identity within the shared batch',async()=>{
 const row={...child,status:'pending',approval_current:true,approval_id:'approval-batch',approval_revision:1,revision:2};
 const render=await harness('UnifiedPolicyLibrary.jsx',[{catalog:[template],items:[row]},{catalog:[],items:[]}]),opened=[];
 const tree=templateDetails(render,{api(){},post(){assert.fail('viewing must not write')},onApprovals:(...args)=>opened.push(args)});
 nodes(tree).find(n=>n.props?.['aria-label']===row.name+'：查看审批').props.onClick();
 assert.deepEqual(opened,[['approval-batch',row.id]]);
});

test('the system shell preserves record focus and clears it for non-record approval links',async()=>{
 const render=await harness('SystemWorkbench.jsx'),opened=[],tree=render({api(){},post(){},navigation:{systemTab:'policies',policyAgent:'a'},navigate:value=>opened.push(value)});
 const library=nodes(tree).find(n=>n.type?.name==='UnifiedPolicyLibrary');
 library.props.onApprovals('approval-batch','tc-a');library.props.onApprovals('manual-batch');
 assert.deepEqual(opened,[{page:'approvals',approvalId:'approval-batch',approvalRecordId:'tc-a'},{page:'approvals',approvalId:'manual-batch',approvalRecordId:''}]);
});
