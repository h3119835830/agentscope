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
import {readNavigation,navigationTarget} from './navigation.mjs';
import {candidateView} from './policyExperience.mjs';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
const configurations=JSON.parse(readFileSync(new URL('./system-policy-configurations.json',import.meta.url)));
const identity={generation:'gen-a',pid:55,start_ticks:'100',domain_id:99,host_id:'host',boot_id:'boot'};
const verifiedTarget=(id,type='dsh',executable='/opt/agentscope/bin/node')=>({id,mode:'controlled',agent_type:type,connected:true,...identity,policy_source:{ready:true,instance_id:id,...identity,pattern:'**/'+executable.split('/').at(-1),entry:'/opt/agent/launcher',executable,basis:'verified-process-executable'}});
const catalogue=JSON.parse(readFileSync(new URL('./rq1-agent-templates.json',import.meta.url)));
const target={...verifiedTarget('agent-1'),resources:['/actual/project']};

test('baseline draft generation persists exact scope without any selected native session or application',async()=>{
 const render=await harness('AgentPolicyDrafts.jsx'),calls=[];
 const props={target,scope:'agent',workspaceId:null,context:{ready:true},api:async()=>({records:[]}),post:async(path,body)=>{calls.push({path,body});return path.endsWith('/generate')?{id:'run'}:{id:'draft',revision:1,latest_revision:1};}};
 let tree=render(props);elements(tree).find(e=>e.type==='textarea').props.onChange({target:{value:'只读取明确的文件，不修改'}});tree=render(props);
 await elements(tree).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls.length,2);assert.equal(calls[0].body.scope,'agent');assert.equal(calls[0].body.workspace_id,null);assert.equal(calls[0].body.session_id,undefined);
 assert.ok(calls[1].path.endsWith('/draft/generate'));assert.ok(calls.every(c=>!c.path.includes('/apply')&&!c.path.includes('/approve')));
});

test('unverified baseline permits explicit saving but blocks generation even through form submission',async()=>{
 const render=await harness('AgentPolicyDrafts.jsx'),calls=[];
 const props={target,scope:'agent',context:{ready:false},api:async()=>({records:[]}),post:async(path,body)=>{calls.push({path,body});return {id:'saved',revision:1};}};
 let tree=render(props);elements(tree).find(e=>e.type==='textarea').props.onChange({target:{value:'保存长期约束需求'}});tree=render(props);
 await elements(tree).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});assert.equal(calls.length,0);
 await elements(tree).find(e=>e.type==='button'&&e.props.children==='保存草案').props.onClick();assert.equal(calls.length,1);assert.ok(calls[0].path.endsWith('/policy-drafts'));
});

test('approved detail offers only explicit application and session inheritance stays collapsed',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalDetail');const tree=render({data:{id:'p',scope_type:'agent',status:'approved',can_approve:false,can_apply:true,documents:[],records:[],targets:[]},onClose(){},onDecision(){}});
 assert.ok(!elements(tree).some(e=>e.type==='button'&&e.props.children==='批准变更'));
 assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='应用策略').props.disabled);
 const groups=await harness('SessionPolicyGroups.jsx');const session=groups({records:[{id:'inherited',scope_type:'agent'}],onDetail(){},onConfigure(){}});
 assert.match(renderToStaticMarkup(session),/本会话没有独立新增约束/);
 const details=elements(session).find(e=>e.type==='details');assert.equal(details.props.open,undefined);
});

test('compiled candidates blocked by server validation require regeneration and have no submit action',async()=>{
 const result={compile_state:'compiled',submission_blockers:['原文权限校验未通过，请重新生成'],
  artifact:{actplane_dsl:'rule old:\n  block read file "/actual/project/input.csv" if AGENT',policy_ir:{rules:[{clauses:[{operation:'read',pattern:'/actual/project/input.csv',effect:'block'}]}]}},
  record:{statement:{text_original:'Read input.csv without changing it.'}}};
 assert.equal(candidateView(result).ready,false);assert.equal(candidateView(result).stale,true);
 const render=await harness('PolicyCandidateDetail.jsx'),tree=render({result,agentName:'Test Agent',onClose(){},onRevise(){}}),html=renderToStaticMarkup(tree);
 assert.match(html,/待重新生成/);assert.doesNotMatch(html,/role="tab"[^>]*>DSL 配置|class="button primary"/);
 assert.equal(elements(tree).some(e=>e.type==='button'&&e.props.onClick===tree.props.onSubmit),false);
 const pending={...result,submission_blockers:[],load_blockers:['尚未最终人工审核'],review_status:'pending_review'};
 assert.equal(candidateView(pending).ready,true);assert.equal(candidateView(pending).stale,false);
});
function elements(tree){if(!tree||typeof tree!=='object')return [];return [tree,...[tree.props?.children].flat(Infinity).flatMap(elements)]}
test('manual child configuration sends only template parameters to the shared API without approving',async()=>{
 const render=await harness('TemplateConfigurationDialog.jsx'),calls=[];
 const template={id:'FILE-CHANGE',version:1,name:'文件修改与删除限制',summary:'文件保护',reason:'保留原件',scopes:['agent'],effect:'block',parameters:[{key:'target',label:'对象',type:'path',default:'/w/0/staff.csv'},{key:'operations',label:'操作',type:'operations',default:['unlink','write']}]};
 const props={template,agents:[target],targetId:target.id,post:async(path,body)=>{calls.push({path,body});return {id:'tc_child'};},onSaved(){},onClose(){}};
 let tree=render(props);assert.equal(elements(tree).filter(e=>e.type==='input'&&e.props.type==='checkbox'&&e.props.checked).length,2);
 await elements(tree).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.equal(calls[0].path,'/api/policy-template-configurations');assert.equal(calls[0].body.scope_id,target.id);assert.equal(calls[0].body.template_id,'FILE-CHANGE');assert.equal(calls[0].body.document,undefined);assert.equal(calls[0].body.original_dsl,undefined);
});
test('template assistant uses the parameter generation API even for a stopped Agent and never calls legacy generation',async()=>{
 const templates=[{id:'FILE-READ',version:1,name:'文件读取限制',scopes:['agent'],parameters:[]}],data={catalog:templates,items:[],generations:[]};
 const render=await harness('TemplatePolicyAssistant.jsx','default',[data]),calls=[];
 const props={target:{...target,connected:false},scope:'agent',api:async()=>data,post:async(path,body)=>{calls.push({path,body});return {items:[],questions:['请补充路径'],gaps:[]};},onApprovals(){}};
 let tree=render(props);elements(tree).find(e=>e.props?.['aria-label']==='策略需求').props.onChange({target:{value:'禁止读取 /w/0/staff.csv'}});tree=render(props);
 await elements(tree).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
 assert.equal(calls.length,1);assert.ok(calls[0].path.endsWith('/agent-1/template-configurations/generate'));assert.equal(calls[0].body.scope,'agent');assert.equal(calls[0].body.document,undefined);assert.ok(!calls[0].path.includes('/history/'));
});
test('static template groups independent sibling configurations without displaying internal DSL',async()=>{
 const templates=[{id:'FILE-CHANGE',version:1,name:'文件修改与删除限制',category:'文件保护',summary:'保护指定文件',scopes:['agent'],parameters:[],operation:'write',effect:'block'}];
 const row={template_id:'FILE-CHANGE',scope_label:'此 Agent',parameters:{target:'/w/0/staff.csv'},effective_operations:['write','unlink'],status:'draft',can_submit:true,coverage_warning:'共用访问组',effect:'block'};
 const data={catalog:templates,items:[{...row,id:'one',name:'员工资料禁止删除',requested_operations:['unlink']},{...row,id:'two',name:'员工资料禁止修改',requested_operations:['write']}]};
 const render=await harness('AgentPolicyTemplates.jsx','default',[data]);const tree=render({api:async()=>data,post:async()=>{},onApprovals(){}}),html=renderToStaticMarkup(tree);
 assert.match(html,/员工资料禁止删除/);assert.match(html,/员工资料禁止修改/);assert.match(html,/2 项子配置/);assert.match(html,/实际影响修改与删除/);assert.doesNotMatch(html,/source AGENT|original_dsl/);
});
async function harness(entry,exported='default',initialStates=[]){
 const built=await build({entryPoints:[join(base,entry)],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const states=[...initialStates],refs=[];let index=0,refIndex=0;const react={...React,useState:init=>{const i=index++;if(!(i in states))states[i]=typeof init==='function'?init():init;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v]},useRef:init=>{const i=refIndex++;return refs[i]||={current:init}},useEffect:()=>{}};
 const name=join(base,'.policy-redesign-test.cjs'),mod=new Module(name);mod.paths=Module._nodeModulePaths(base);const original=mod.require.bind(mod);mod.require=id=>id==='react'?react:original(id);mod._compile(built.outputFiles[0].text,name);
 return (...props)=>{globalThis.document={activeElement:null};index=0;refIndex=0;return mod.exports[exported](...props)};
}
test('templates open as a structured record table, with configuration deferred until a record is selected',async()=>{
 const templates=catalogue.templates.map(t=>({...t,version:1,scopes:['agent','workspace'],parameters:t.parameters.map(p=>({...p,default:p.value,type:'path'}))}));
 const render=await harness('AgentPolicyTemplates.jsx','default',[{catalog:templates,items:[]}]);let writes=0;const props={agents:[target],api:async()=>({catalog:templates,items:[]}),post:async()=>writes++,onApprovals:()=>{}};let tree=render(props),nodes=elements(tree);
 assert.equal(nodes.filter(e=>e.type==='table').length,1);assert.equal(nodes.filter(e=>e.type==='tr').length,7);assert.equal(nodes.filter(e=>e.type==='form').length,0);
 const html=renderToStaticMarkup(tree);for(const field of ['模板 / 子配置','保护对象','操作与处置','配置状态'])assert.ok(html.includes(field));assert.doesNotMatch(html,/template-card|RQ\d/i);
 nodes.find(e=>e.type==='button'&&e.props['aria-label']==='配置 敏感配置访问限制').props.onClick();tree=render(props);assert.ok(elements(tree).some(e=>e.props?.template?.id==='RQ1-ENV'));assert.equal(writes,0);
});
test('system configurations are explicit system candidates and cannot be imported as Agent templates',()=>{
 assert.equal(configurations.length,3);
 for(const t of configurations){const values=Object.fromEntries(t.parameters.map(p=>[p.key,p.value]));const candidate=createSystemHandoff(t,values,'test','system-draft',[{pattern:'**/node'}]);assert.equal(candidate.targetId,'system');assert.equal(appendHandoff({scope_id:'system',documents:[]},candidate,'system').length,1);assert.throws(()=>appendHandoff({scope_id:target.id,documents:[]},candidate,target.id));assert.throws(()=>createHandoff(t,values,'',target));}
 assert.throws(()=>createSystemHandoff(catalogue.templates[0],{}));
});
test('detail configuration uses the exact selected Agent resource, resets parameters when target changes and writes only on submit',async()=>{
 const render=await harness('PolicyTemplateDetail.jsx'),other={...verifiedTarget('agent-2'),resources:['/other/project']};let candidate=null;
 const props={template:catalogue.templates[0],agents:[target,other],targetId:target.id,onHandoff:c=>candidate=c};let tree=render(props);
 assert.equal(candidate,null);let nodes=elements(tree);assert.ok(nodes.some(e=>e.type==='input'&&e.props.value==='/actual/project/.env'));
 nodes.find(e=>e.type==='select').props.onChange({target:{value:other.id}});tree=render(props);nodes=elements(tree);assert.ok(nodes.some(e=>e.type==='input'&&e.props.value==='/other/project/.env'));
 await nodes.find(e=>e.type==='form').props.onSubmit({preventDefault(){}});assert.equal(candidate.targetId,other.id);assert.ok(candidate.document.original_dsl.includes('/other/project/.env'));
});
test('Agent assistant has a conversation and one composer, without a duplicated template table or write on mount',async()=>{
 const render=await harness('AgentPolicyAssistant.jsx');let calls=[];const context={ready:true,session_id:'session-one',context_hash:'a'.repeat(64),sessions:[{id:'session-one',name:'One'}]};const props={target,context,api:async()=>context,post:async(path,body)=>{calls.push({path,body});return path.endsWith('/inputs')?{id:'input-one'}:{id:'run-one',status:'queued'}}};let tree=render(props),nodes=elements(tree);
 assert.equal(nodes.filter(e=>e.type==='table').length,0);assert.equal(nodes.filter(e=>e.type==='textarea').length,1);assert.equal(calls.length,0);
 nodes.find(e=>e.type==='textarea').props.onChange({target:{value:'保护一个明确指定的文件'}});tree=render(props);await elements(tree).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});
 assert.deepEqual(calls.map(c=>c.path),['/api/history/inputs','/api/history/generations']);assert.equal(calls[0].body.text,'保护一个明确指定的文件');assert.equal(calls[0].body.context_requirement,'project');assert.deepEqual(calls[0].body.agent_context,{instance_id:target.id,session_id:'session-one',context_hash:'a'.repeat(64)});assert.doesNotMatch(calls[0].body.text,/agent_id|resources|verified_task_environment/);assert.equal(calls[1].body.statement_version_id,'input-one');assert.ok(calls.every(c=>!c.path.includes('/confirm')&&!c.path.includes('/review')));
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
 nodes.find(e=>e.type==='button'&&e.props['aria-label']==='选择策略').props.onClick();tree=render(props);elements(tree).find(e=>e.props?.onTemplate).props.onTemplate('RQ1-ENV');
 tree=render(props);const panel=elements(tree).find(e=>e.props?.conversation===true);assert.ok(panel);assert.equal(panel.props.targetId,target.id);assert.equal(writes,0);
 const candidate=createHandoff(catalogue.templates[0],{target:'/actual/project/.env'},'',target,'chat-draft');candidate.presentation={name:candidate.document.name,template:catalogue.templates[0],values:{target:'/actual/project/.env'},operation:'open',effect:'block',reason:'Use sample'};
 panel.props.onHandoff(candidate);tree=render(props);nodes=elements(tree);
 assert.ok(nodes.some(e=>e.type==='strong'&&e.props.children===candidate.document.name));assert.equal(writes,0);assert.equal(imported,null);
 assert.ok(nodes.some(e=>e.type==='button'&&e.props.children==='提交审批'));assert.equal(imported,null);assert.equal(writes,0);
 nodes.find(e=>e.type==='button'&&[e.props.children].flat(Infinity).join('')==='查看详情 ↗').props.onClick();tree=render(props);assert.equal(elements(tree).find(e=>e.props?.conversation===true).props.initialCandidate.id,'chat-draft');
});

test('follow-up generation receives the selected candidate configuration as context, without pretending it is approved or verified',()=>{
 const payload=assistantInput('改为只提醒，保留相同路径',target,[{kind:'template',text:'配置策略',candidate:{presentation:{name:'敏感文件保护',values:{target:'/actual/project/.env'},operation:'open',effect:'block',reason:'Use sample'}}}]);
 assert.match(payload.text,/\/actual\/project\/\.env/);assert.match(payload.text,/尚未应用/);assert.ok(payload.text.startsWith('改为只提醒'));assert.doesNotMatch(payload.text,/agent_id|verified_task_environment/);
});


test('an unverified environment disables free-form generation and cannot write even on manual form submission',async()=>{
 const render=await harness('AgentPolicyAssistant.jsx');let writes=0;const props={target,post:async()=>writes++};let tree=render(props);elements(tree).find(e=>e.type==='textarea').props.onChange({target:{value:'保护当前工作目录的文件'}});tree=render(props);assert.ok(elements(tree).find(e=>e.type==='button'&&e.props['aria-label']==='生成策略').props.disabled);await elements(tree).find(e=>e.type==='form').props.onSubmit({preventDefault(){}});assert.equal(writes,0);
});
test('Agent/session selection round-trips without putting DSL or environment data into the URL',()=>{
 const n=readNavigation('http://localhost'+navigationTarget('http://localhost/?view=workbench',{policyAgent:'agent-a',policySession:'native-session'}));assert.equal(n.policyAgent,'agent-a');assert.equal(n.policySession,'native-session');
});


test('strategy selection is a searchable record dialog and never a native template option menu',async()=>{
 const render=await harness('AssistantPolicyLibrary.jsx');let selected='',writes=0;
 const tree=render({templates:catalogue.templates,generated:[],drafts:[],onTemplate:id=>selected=id,onClose:()=>writes++});
 assert.equal(elements(tree).filter(e=>e.type==='select').length,0);assert.equal(elements(tree).filter(e=>e.type==='table').length,1);
 assert.ok(elements(tree).some(e=>e.type==='input'&&e.props.type==='search'));
 elements(tree).find(e=>e.type==='button'&&[e.props.children].flat(Infinity).join('')==='配置并使用 ↗').props.onClick();assert.equal(selected,'RQ1-ENV');assert.equal(writes,0);
});
test('incomplete generated candidates remain readable but cannot submit or pretend to have executable DSL',async()=>{
 const render=await harness('PolicyCandidateDetail.jsx');const tree=render({result:{record:{statement:{text_zh:'明确需要保护的文件'}}},agentName:'Target',sessionName:'Session'});
 assert.match(renderToStaticMarkup(tree),/明确需要保护的文件/);assert.ok(!elements(tree).some(e=>e.type==='button'&&e.props.children==='提交审批'));
});
test('reopening a validated draft preserves its preview and explicit confirmation action',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor'),doc={id:'d',name:'Existing draft',original_dsl:'rule r:\n notify read file "/w/0/a" if AGENT\n because "reason"',metadata:{}},proposal={id:'p',state:'pending',documents:[doc],result:{compilations:[],error:null},targets:[]};
 const installed={...doc,original_dsl:'rule old:\n notify read file "/w/0/previous" if AGENT\n because "previous configuration"'};
 const tree=render({data:{scope_id:'agent',documents:[installed],records:[]},scopeLabel:'Target',proposal,onReview:()=>{}});
 assert.equal(elements(tree).find(e=>e.type==='textarea'&&e.props['aria-label']==='原始 DSL 文本').props.value,doc.original_dsl);
 assert.match(renderToStaticMarkup(tree),/previous configuration/);
 assert.ok(elements(tree).some(e=>e.type==='button'&&e.props.children==='前往审批'&&!e.props.disabled));
});

test('submitting a candidate only proposes validated changes, reuses a live matching approval, and never applies',async()=>{
 const {submitCandidate}=await import('./policyExperience.mjs');
 const c=createHandoff(catalogue.templates[0],{target:'/actual/project/.env'},'',target,'new-document');
 const current={scope_id:target.id,documents:[],revision:1,document_hash:'base',proposals:[]};let calls=[];
 const api=async path=>{calls.push(['GET',path]);return current;},post=async(path,body)=>{calls.push(['POST',path,body]);return {id:'new-approval',state:'pending'};};
 const result=await submitCandidate(c,api,post);assert.equal(result.state,'pending');assert.equal(calls.length,2);assert.ok(calls[1][1].endsWith('/dsl/proposals'));assert.equal(calls[1][2].base_revision,1);assert.deepEqual(calls[1][2].documents,[c.document]);
 const existing={id:'already-pending',state:'pending',base_revision:1,base_hash:'base',documents:[c.document]};current.proposals=[existing];calls=[];
 const reused=await submitCandidate(c,async path=>{calls.push(['GET',path]);return path.includes('/approvals/')?{can_apply:true}:current;},post);assert.equal(reused.id,existing.id);assert.ok(calls.every(c=>c[0]==='GET'));
 calls=[];await submitCandidate(c,async path=>path.includes('/approvals/')?{can_apply:false}:current,post);assert.equal(calls.length,1);assert.ok(calls[0][1].endsWith('/dsl/proposals'));
 await assert.rejects(()=>submitCandidate({...c,targetId:'wrong-agent'},api,post));assert.ok(calls.every(c=>!c[1].includes('/confirm')&&!c[1].includes('/apply')));
});
test('approval details expose change, targets and explicit decisions without writing on viewing or switching tabs',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalDetail');let decisions=[];
 const data={id:'proposal',scope_type:'agent',target_name:'DeepSeek Harness',status:'pending',can_approve:true,can_apply:false,created_at:'2026-10-11T01:00:00Z',documents:[{id:'d',name:'Protect secret',original_dsl:'source AGENT = exec "**/node"'}],previous_documents:[],records:[{id:'r',document_id:'d',statement:'Protect secret',clauses:[{effect:'block',operation:'open',target:'/w/0/.env'}]}],targets:[{id:'agent',name:'DeepSeek Harness',active:true}],total_affected_count:1};
 const props={data,onClose(){},onDecision:async(...args)=>decisions.push(args)};let tree=render(props);assert.equal(decisions.length,0);assert.match(renderToStaticMarkup(tree),/全部工作区与会话/);assert.match(renderToStaticMarkup(tree),/新增/);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='完整 DSL').props.onClick();tree=render(props);assert.equal(decisions.length,0);assert.match(renderToStaticMarkup(tree),/node/);
 assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='批准变更').props.disabled);elements(tree).find(e=>e.type==='input'&&e.props.type==='checkbox').props.onChange({target:{checked:true}});tree=render(props);await elements(tree).find(e=>e.type==='button'&&e.props.children==='批准变更').props.onClick();assert.equal(decisions[0][1],'approve');
 tree=render({...props,data:{...data,status:'stale',can_approve:false,can_apply:false}});assert.ok(!elements(tree).some(e=>e.props?.children==='批准变更'||e.props?.children==='应用策略'));
});
test('approval deep links retain only the record identity',()=>{
 const url=navigationTarget('http://localhost/?view=workbench',{page:'approvals',approvalId:'approval-one'}),n=readNavigation('http://localhost'+url);assert.equal(n.page,'approvals');assert.equal(n.approvalId,'approval-one');assert.doesNotMatch(url,/proposal_hash|documents/);
});
test('runtime approval shows an exact task scope and readable before/after without applying on view',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalDetail');let decisions=[];
 const data={id:'runtime:job',kind:'runtime',scope_type:'session',target_name:'Task A',status:'pending',can_approve:true,can_apply:false,can_reject:true,created_at:'2026-10-11T01:00:00Z',documents:[],records:[],change_items:[{label:'可写目录',before:'.',after:'src'}],targets:[{id:'task-a',name:'Task A',scope_label:'当前任务会话',application_label:'确认后重建当前任务执行域'}],total_affected_count:1};
 const tree=render({data,onClose(){},onDecision:async(...args)=>decisions.push(args)}),html=renderToStaticMarkup(tree);
 assert.match(html,/权限变更对照/);assert.match(html,/当前任务会话/);assert.match(html,/Task A/);assert.doesNotMatch(html,/全部工作区与会话|完整 DSL|PolicyIR|原始 JSON/);assert.equal(decisions.length,0);
 assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='批准变更').props.disabled);assert.equal(elements(tree).some(e=>e.props?.children==='应用策略'),false);await elements(tree).find(e=>e.type==='button'&&e.props.children==='批准变更').props.onClick();assert.equal(decisions[0][0].id,'runtime:job');assert.equal(decisions[0][1],'approve');
});
test('all approval origins use the same explicit decision endpoint',async()=>{
 const url=await harness('PolicyApprovals.jsx','approvalDecisionUrl');
 for(const id of ['dsl-one','instance:one','system:one','runtime:job'])assert.equal(url(id,'confirm'),'/api/console/approvals/'+encodeURIComponent(id)+'/confirm');
});

test('restored approvals based on old configuration cannot confirm until revalidated',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor'),doc={id:'d',name:'Old draft',original_dsl:'rule r:\n notify read file "/w/0/a" if AGENT\n because "reason"',metadata:{}},proposal={id:'p',state:'pending',base_revision:1,base_hash:'old',documents:[doc],result:{compilations:[],error:null},targets:[]};
 const tree=render({data:{scope_id:'agent',revision:2,document_hash:'current',documents:[doc],records:[]},scopeLabel:'Target',proposal,onReview:()=>{}});
 assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='前往审批').props.disabled);assert.match(renderToStaticMarkup(tree),/草案基于旧的策略配置/);
});
test('a restored removal proposal remains empty and clearly discloses removal',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor'),proposal={id:'p',state:'pending',documents:[],result:{compilations:[],error:null},targets:[]};
 const tree=render({data:{scope_id:'agent',documents:[],records:[]},scopeLabel:'Target',proposal,onReview:()=>{}});
 assert.equal(elements(tree).filter(e=>e.type==='textarea').length,0);assert.match(renderToStaticMarkup(tree),/候选不包含任何用户 DSL/);
});

test('DSL import uses a real button and reads a file into the local candidate without saving or applying',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor');let picked=0,writes=0;
 const props={data:{scope_id:'agent',documents:[],records:[]},scopeLabel:'DeepSeek Harness',onValidate:()=>writes++,onApply:()=>writes++};
 let tree=render(props),nodes=elements(tree),picker=nodes.find(e=>e.type==='input'&&e.props.type==='file');
 assert.equal(picker.props.hidden,true);assert.equal(picker.props['aria-label'],'选择 DSL 文件');assert.ok(!nodes.some(e=>e.type==='label'&&e.props.className?.includes('dsl-file-input')));
 picker.props.ref.current={click:()=>picked++};nodes.find(e=>e.type==='button'&&e.props.children==='导入 .dsl').props.onClick();assert.equal(picked,1);assert.equal(writes,0);
 const text='source AGENT = exec "**/node"\n\nrule toolbar-test:\n  notify open file "/w/0/toolbar-check.txt" if AGENT\n  because "Toolbar acceptance"';const event={target:{files:[{name:'toolbar-check.dsl',size:300,arrayBuffer:async()=>new TextEncoder().encode(text).buffer}],value:'chosen'}};
 await picker.props.onChange(event);tree=render(props);nodes=elements(tree);assert.equal(nodes.find(e=>e.type==='textarea'&&e.props['aria-label']==='原始 DSL 文本').props.value,text);assert.ok(nodes.some(e=>e.type==='input'&&e.props.value==='toolbar-check.dsl'));assert.equal(event.target.value,'');assert.equal(writes,0);
 tree=render({...props,busy:true});assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='导入 .dsl').props.disabled);
});


test('blank DSL drafts use the exact server runtime source and cannot validate a source-only stub',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor');let writes=0;
 const data={scope_id:target.id,documents:[],records:[],source_context:{scope_id:target.id,ready:true,sources:[{...target.policy_source,id:target.id,name:'DeepSeek Harness'}],unavailable:[]}};
 const tree=render({data,importing:true,onValidate:()=>writes++,onApply:()=>writes++});
 const nodes=elements(tree);assert.equal(nodes.find(e=>e.type==='textarea').props.value,'source AGENT = exec "**/node"\n\n');
 assert.ok(nodes.find(e=>e.type==='button'&&e.props.children==='保存并校验').props.disabled);assert.equal(writes,0);
 assert.match(renderToStaticMarkup(tree),/当前运行来源/);assert.doesNotMatch(renderToStaticMarkup(tree),/exec &quot;\*\*&quot;/);
});
test('a generic imported declaration is preserved for review and explicitly rebound without applying',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor');let writes=0;
 const data={scope_id:target.id,documents:[{id:'d',name:'Imported',original_dsl:'source AGENT = exec "**"\nsource SECRET = file "/w/0/secret"\nrule one:\n notify open file "/w/0/.env" if AGENT',metadata:{}}],records:[],source_context:{scope_id:target.id,ready:true,sources:[{...target.policy_source,id:target.id,name:'DeepSeek Harness'}],unavailable:[]}};
 const props={data,onValidate:()=>writes++,onApply:()=>writes++};let tree=render(props),nodes=elements(tree);
 assert.match(renderToStaticMarkup(tree),/此文档仍使用通用来源/);assert.ok(nodes.find(e=>e.type==='button'&&e.props.children==='保存并校验').props.disabled);
 nodes.find(e=>e.type==='button'&&e.props.children==='使用当前运行来源').props.onClick();tree=render(props);const text=elements(tree).find(e=>e.type==='textarea').props.value;
 assert.ok(text.startsWith('source AGENT = exec "**/node"'));assert.ok(text.includes('source SECRET = file'));assert.equal(writes,0);
 tree=render({...props,sourceStale:true});assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='保存并校验').props.disabled);
});
test('unavailable sources never create a generic executor declaration',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor');const tree=render({data:{scope_id:target.id,documents:[],records:[],source_context:{scope_id:target.id,ready:false,sources:[],unavailable:[{id:target.id,name:'DeepSeek Harness',message:'请连接并核验当前 Agent'}]}},importing:true});
 const textarea=elements(tree).find(e=>e.type==='textarea');assert.equal(textarea.props.value,'');assert.doesNotMatch(textarea.props.placeholder,/\*\*/);assert.match(renderToStaticMarkup(tree),/请连接并核验当前 Agent/);
});
test('a projected stale draft blocks approval handoff even when its raw state is pending',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor');let handoffs=0;
 const proposal={id:'p',state:'pending',documents:[],result:{compilations:[]},targets:[],approval:{status:'stale',can_approve:false,can_apply:false,reason:'Agent 环境已经变化，需要重新校验。'}};
 const tree=render({data:{scope_id:'agent',documents:[],records:[]},proposal,onReview:()=>handoffs++});
 assert.match(renderToStaticMarkup(tree),/需重新校验/);
 const button=elements(tree).find(e=>e.type==='button'&&e.props.children==='前往审批');assert.ok(button.props.disabled);
 await button.props.onClick();assert.equal(handoffs,0);
});
test('revalidating a stale draft uses the new proposal status and hands off only that proposal',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor');let handedOff='';
 const old={id:'old',state:'pending',documents:[],base_hash:'old-base',base_revision:1,result:{},targets:[],approval:{status:'stale',can_approve:false,can_apply:false}};
 const fresh={...old,id:'fresh',base_hash:'current',base_revision:2,approval:{status:'pending',can_apply:true}};
 const props={data:{scope_id:'agent',revision:2,document_hash:'current',documents:[],records:[]},proposal:old,approval:old.approval,onValidate:async()=>fresh,onReview:p=>{handedOff=p.id;},onClose:()=>{}};
 let tree=render(props);await elements(tree).find(e=>e.type==='button'&&e.props.children==='保存并校验').props.onClick();tree=render(props);
 const handoff=elements(tree).find(e=>e.type==='button'&&e.props.children==='前往审批');assert.equal(handoff.props.disabled,false);
 await handoff.props.onClick();assert.equal(handedOff,'fresh');
});


test('approval records show product, PID and native session with exact read navigation',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalRecords'),paths=[];
 const row={id:'proposal-a',name:'Protect secret',scope_type:'agent',document_count:1,status:'stale',created_at:'2026-10-11T01:00:00Z',target_name:'DeepSeek Harness',agents:[{id:'agent-a',name:'DeepSeek Harness',pid:54870}],origin_sessions:[{instance_id:'agent-a',session_id:'session-one',name:'Run native tests',available:true,generation_pid:54870}]};
 const tree=render({rows:[row],navigate:p=>paths.push(p)}),html=renderToStaticMarkup(tree);
 for(const value of ['适用 Agent','生成会话','DeepSeek Harness','54870','Run native tests','状态 / 提交时间'])assert.ok(html.includes(value));
 assert.doesNotMatch(html,/RQ5|受控实例|批准并应用/);assert.equal(paths.length,0);
 // Render the nested location components independently to exercise their buttons.
 const agentNode=elements(tree).find(e=>e.type?.name==='AgentLocation');
 elements(agentNode.type(agentNode.props)).find(e=>e.type==='button').props.onClick();
 const sessionNode=elements(tree).find(e=>e.type?.name==='SessionLocations');
 elements(sessionNode.type(sessionNode.props)).find(e=>e.type==='button').props.onClick();
 assert.deepEqual(paths,[{page:'connections',connectionInstance:'agent-a',connectionTab:'policy',approvalId:''},{page:'sessions',sessionInstance:'agent-a',sessionId:'session-one',sessionTab:'policies',approvalId:''}]);
});
test('approval search finds native session and both current and historical PID',async()=>{
 const {matchesApproval,processLabel,originLabel}=await import('./approvalPresentation.mjs');
 const r={name:'Protect',agents:[{name:'DeepSeek Harness',pid:77,submitted_pid:55}],origin_sessions:[{session_id:'session-one',name:'Native task',generation_pid:33}]};
 for(const q of ['PID 77','55','33','native task','session-one','DeepSeek','protect'])assert.ok(matchesApproval(r,q));
 assert.ok(!matchesApproval(r,'Hermes'));assert.equal(processLabel({pid:null,process_state:'offline'}),'未运行');
 assert.equal(originLabel({scope_type:'agent',origin_state:'unrecorded'}),'未关联会话');
});

test('system approvals present one global audience instead of enumerating every Agent and repeated scope',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalRecords');
 const row={id:'global',name:'保护环境凭据',scope_type:'system',scope_label:'全部受控 Agent',status:'pending',created_at:'2026-10-14T00:00:00Z',total_affected_count:4,agents:[{id:'one',name:'DeepSeek Harness',pid:44},{id:'two',name:'Hermes',pid:55},{id:'three',name:'DeepSeek Harness',pid:66},{id:'four',name:'DeepSeek Harness',pid:null}],origin_sessions:[]};
 const html=renderToStaticMarkup(render({rows:[row],navigate(){throw Error('read-only rendering');}}));
 assert.equal((html.match(/全部受控 Agent/g)||[]).length,1);
 assert.match(html,/提交时涉及 4 个实例/);assert.match(html,/系统配置/);
 assert.doesNotMatch(html,/DeepSeek Harness|Hermes|PID 44|PID 55|未运行/);
});

test('applied removal retains the removed policy name and accurate change count',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalDetail');
 const data={id:'removed',name:'停用 验收依据保护',scope_type:'system',status:'applied',kind:'dsl',created_at:'2026-10-14T00:00:00Z',documents:[],records:[],targets:[],agents:[],total_affected_count:0,document_changes:{removed:['验收依据保护']},can_apply:false};
 const html=renderToStaticMarkup(render({data,onClose(){}}));
 assert.match(html,/1 项变更/);assert.match(html,/移除<\/span>验收依据保护/);assert.doesNotMatch(html,/0 项变更/);
});

test('inactive system policy deletion is explicitly confirmed and uses archive without runtime confirmation',async()=>{
 const item={id:'saved',name:'中文测试策略',kind:'dsl',document:{id:'saved',name:'中文测试策略',original_dsl:'rule x:\n notify exec "git" if AGENT'},revision:3,applied:false,records:[]};
 const data={items:[item],catalog:[],targets:[],phase:'ready',base_hash:'a'.repeat(64),base_revision:0};
 const render=await harness('SystemPolicyLibrary.jsx','default',[data]),calls=[];
 const props={api:async()=>data,post:async(...args)=>{calls.push(args);return {archived:true};}};
 let tree=render(props);elements(tree).find(e=>e.type==='button'&&e.props.children==='删除配置…').props.onClick();
 assert.equal(calls.length,0);tree=render(props);
 const prompt=elements(tree).find(e=>e.type?.name==='PolicyLifecycleDialog');assert.match(renderToStaticMarkup(prompt.props.children),/历史版本、审批和执行记录/);
 await prompt.props.onConfirm();assert.deepEqual(calls,[['/api/security/system/policy-library/saved/archive',{revision:3}]]);
});

test('Agent policy stop creates a reviewed removal candidate and preserves every other document',async()=>{
 const first={id:'first',name:'项目测试保护',original_dsl:'source AGENT = exec "**/node"\nrule x:\n block write file "/w/0/tests/**" if AGENT'};
 const second={id:'second',name:'配置保护',original_dsl:first.original_dsl};
 const record={id:'r',document_id:first.id,document_name:first.name,rule_name:'x',statement:first.name,editable:true,effects:['block']};
 const data={scope_id:'agent-a',revision:2,document_hash:'a'.repeat(64),phase:'ready',documents:[first,second],records:[record],proposals:[]};
 const render=await harness('ActPlanePolicies.jsx','default',[data]),calls=[],approvals=[];
 const props={scopeId:'agent-a',scopeLabel:'DeepSeek Harness',api:async()=>data,post:async(...args)=>{calls.push(args);return {id:'remove-candidate',state:'pending'};},onApprovals:id=>approvals.push(id)};
 let tree=render(props);elements(tree).find(e=>e.type?.name==='ConfiguredPolicyRecords').props.onDisable(record);
 assert.equal(calls.length,0);tree=render(props);const prompt=elements(tree).find(e=>e.type?.name==='PolicyLifecycleDialog');
 await prompt.props.onConfirm();assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/agent-instances/agent-a/dsl/proposals');
 assert.deepEqual(calls[0][1].documents,[second]);assert.equal(calls[0][1].base_hash,data.document_hash);assert.deepEqual(approvals,['remove-candidate']);
});

test('assistant stops only the selected generation and waits for backend cancellation acknowledgement',async()=>{
 const turn={runId:'generation-one',text:'请生成中文项目保护策略',targetId:target.id};
 const render=await harness('AgentPolicyAssistant.jsx','default',[[turn],'',false,'',{'generation-one':{status:'running'}},{}]),calls=[];
 const props={target,api:async()=>({}),post:async(...args)=>{calls.push(args);return {status:'cancelling'};}};
 let tree=render(props);const button=elements(tree).find(e=>e.type==='button'&&e.props.children==='停止生成');assert.ok(button);
 await button.props.onClick();assert.deepEqual(calls,[['/api/history/generations/generation-one/cancel',{}]]);
 tree=render(props);assert.match(renderToStaticMarkup(tree),/正在停止生成，当前请求结束后退出/);
 assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='正在停止…').props.disabled);
});

test('current baseline draft assistant can cancel its own generation without applying a policy',async()=>{
 const draft={id:'draft-one',run_id:'baseline-run',revision:1,text:'禁止修改项目验收依据',state:'generating',materials:[]};
 const initial=['',[],null,null,[draft],{'baseline-run':{status:'running'}},{},'',false,true];
 const render=await harness('AgentPolicyDrafts.jsx','default',initial),calls=[];
 const props={target,scope:'agent',context:{ready:true},api:async()=>({records:[draft]}),post:async(...args)=>{calls.push(args);return {cancel_requested:true};}};
 let tree=render(props);await elements(tree).find(e=>e.type==='button'&&e.props.children==='停止生成').props.onClick();
 assert.deepEqual(calls,[['/api/history/generations/baseline-run/cancel',{}]]);
 tree=render(props);assert.match(renderToStaticMarkup(tree),/正在停止生成，当前请求结束后退出/);
 assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='正在停止…').props.disabled);
});

test('stop confirmation freezes the displayed generation instead of accepting a refreshed identity',async()=>{
 const row={...target,gate:'open',policy_hash:'a'.repeat(64),proposals:[],policy:{rules:[],network:'model_only'}};
 const render=await harness('AgentInstances.jsx','Drawer',[0,'connection',row,'','','','',null,'',[]]),calls=[];
 const props={id:row.id,api:async()=>row,post:async(...args)=>calls.push(args),onChanged(){}};
 let tree=render(props);elements(tree).find(e=>e.type==='button'&&e.props.children==='停止 Agent').props.onClick();
 row.generation='changed-after-dialog';row.policy_hash='b'.repeat(64);
 tree=render(props);const modal=elements(tree).find(e=>e.type?.name==='PolicyLifecycleDialog');
 await modal.props.onConfirm();assert.deepEqual(calls,[['/api/agent-instances/'+row.id+'/stop',{generation:identity.generation,policy_hash:'a'.repeat(64)}]]);
});

test('system library review sends separate idempotent approve and apply requests',async()=>{
 const pending={id:'system-review',scope_type:'system',status:'pending',proposal_hash:'a'.repeat(64),documents:[],records:[],targets:[],agents:[],total_affected_count:0,can_approve:true,can_apply:false,created_at:'2026-10-14T00:00:00Z'};
 const approved={...pending,status:'approved',can_approve:false,can_apply:true,approval_hash:'b'.repeat(64)};
 const data={items:[],catalog:[],targets:[],phase:'ready'};
 const render=await harness('SystemPolicyLibrary.jsx','default',[data,null,'','',false,'all','','全部类型',new Set(),null,pending]),calls=[];
 const props={api:async path=>path.includes('/approvals/')?approved:data,post:async(...args)=>{calls.push(args);return {state:'applied',resumed_count:0};}};
 let tree=render(props),detail=elements(tree).find(e=>e.type?.name==='ApprovalDetail');
 await detail.props.onDecision(pending,'approve');
 assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/console/approvals/system-review/approve');assert.ok(calls[0][1].request_key);
 tree=render(props);detail=elements(tree).find(e=>e.type?.name==='ApprovalDetail');assert.equal(detail.props.data.can_apply,true);
 assert.match(renderToStaticMarkup(tree),/当前运行策略尚未改变/);
 await detail.props.onDecision(approved,'apply');assert.equal(calls[1][0],'/api/console/approvals/system-review/apply');assert.equal(calls[1][1].approval_hash,approved.approval_hash);assert.ok(calls[1][1].request_key);
});

test('stale approval exposes revalidation and keeps original record read only',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalDetail'),chosen=[];
 const data={id:'old',name:'环境凭据文件',scope_type:'system',status:'stale',kind:'dsl',created_at:'2026-10-14T00:00:00Z',documents:[],records:[],targets:[],agents:[],total_affected_count:0,can_apply:false,can_approve:false,can_reject:true,reason:'配置从 v1 更新到 v2',revalidation:{available:true,destination:{page:'strategies'}}};
 const tree=render({data,onClose(){},onRevalidate:row=>chosen.push(row.id)});
 const html=renderToStaticMarkup(tree);assert.match(html,/重新校验/);assert.doesNotMatch(html,/>批准变更<|>应用策略</);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='重新校验').props.onClick();assert.deepEqual(chosen,['old']);
 const locations=[];const shared=render({data,onClose(){},navigate:target=>locations.push(target)});
 elements(shared).find(e=>e.type==='button'&&e.props.children==='重新校验').props.onClick();
 assert.deepEqual(locations,[{page:'approvals',approvalId:'old'}]);
});

test('revalidation previews current versions and creates only a fresh candidate after explicit acknowledgement',async()=>{
 const plan={plan_hash:'a'.repeat(64),scope_label:'全部受控 Agent',target_count:4,message:'创建新候选，旧记录保留',changed_content:true,comparisons:[{name:'环境凭据文件',before_version:1,after_version:2,same_content:false,before_summary:'记录通知',after_summary:'阻断操作',before_dsl:'notify open file "**/*.env" if AGENT',after_dsl:'block open file "**/*.env" if AGENT'}]};
 const render=await harness('ApprovalRevalidation.jsx','default',[plan,'',false,false,false]),calls=[],created=[];
 const props={data:{id:'old',name:'环境凭据文件',revalidation:{destination:{page:'strategies'}}},api:async()=>plan,post:async(...args)=>{calls.push(args);return {id:'new'};},onCreated:result=>created.push(result.id)};
 let tree=render(props),nodes=elements(tree);assert.ok(nodes.find(e=>e.type==='button'&&e.props.children==='校验并生成新候选').props.disabled);
 assert.match(renderToStaticMarkup(tree),/内容已变化，请核对/);assert.equal(calls.length,0);
 nodes.find(e=>e.type==='input'&&e.props.type==='checkbox').props.onChange({target:{checked:true}});
 tree=render(props);await elements(tree).find(e=>e.type==='button'&&e.props.children==='校验并生成新候选').props.onClick();
 assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/console/approvals/old/revalidate');assert.equal(calls[0][1].plan_hash,plan.plan_hash);assert.ok(calls[0][1].request_key);assert.deepEqual(created,['new']);
});

test('approval selection is limited to current filtered results and clears across tabs',async()=>{
 const records=[{id:'a',name:'员工保护',scope_id:'agent-a',scope_type:'agent',status:'pending',can_approve:true,created_at:'2026-10-19T00:00:00Z'},
  {id:'b',name:'订单保护',scope_id:'agent-b',scope_type:'agent',status:'pending',can_approve:true,created_at:'2026-10-19T00:00:00Z'},
  {id:'c',name:'过期配置',scope_id:'agent-c',scope_type:'agent',status:'stale',created_at:'2026-10-19T00:00:00Z'}];
 const render=await harness('PolicyApprovals.jsx','default',[null,{records},null,'pending','','',false,0,[],null]),calls=[];
 const props={api:async()=>({records}),post:async(...args)=>calls.push(args),navigation:{},navigate(){}};
 let tree=render(props);assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='批量批准').props.disabled);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='全选当前结果').props.onClick();tree=render(props);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='批量批准').props.onClick();tree=render(props);
 const batch=elements(tree).find(e=>e.type?.name==='ApprovalBatch');assert.deepEqual(batch.props.rows.map(r=>r.id),['a','b']);assert.equal(calls.length,0);
 batch.props.onClose();tree=render(props);elements(tree).find(e=>e.props?.role==='tab'&&String(e.props.children).includes('需要处理')).props.onClick();tree=render(props);
 assert.match(renderToStaticMarkup(tree),/应用未完成和暂不能应用/);assert.ok(elements(tree).find(e=>e.type==='button'&&e.props.children==='批量重新校验').props.disabled);
});
test('bulk approval confirmation is disabled until the displayed contents are acknowledged',async()=>{
 const data={id:'a',name:'员工资料保护',scope_id:'agent-a',scope_type:'agent',target_name:'DeepSeek Harness',status:'pending',documents:[],records:[],targets:[]};
 const batch={action:'approve',entries:[{id:'a',data,binding:'frozen',requestKey:'once'}]};
 const render=await harness('ApprovalBatch.jsx','default',[batch,'',false,false,null,false]),calls=[];
 const props={rows:[data],action:'approve',api:async()=>data,post:async(...args)=>calls.push(args),onClose(){},onFinished(){},onOpenRecord(){}};
 let tree=render(props);const confirm=elements(tree).find(e=>e.type==='button'&&String(e.props.children).includes('确认批量批准'));
 assert.ok(confirm.props.disabled);await confirm.props.onClick();assert.equal(calls.length,0);
 elements(tree).find(e=>e.type==='input'&&e.props.type==='checkbox').props.onChange({target:{checked:true}});tree=render(props);
 assert.equal(elements(tree).find(e=>e.type==='button'&&String(e.props.children).includes('确认批量批准')).props.disabled,false);
});
test('unsupported bulk recovery keeps its reason and exact configuration destination',async()=>{
 const destination={page:'sessions',sessionInstance:'agent-a',sessionId:'original-session',sessionTab:'policies',approvalId:''};
 const data={id:'a',name:'会话权限',scope_type:'session',status:'blocked',revalidation:{available:false,destination}},batch={action:'revalidate',entries:[{id:'a',data,error:'缺少可信会话执行目标，请返回所属配置重新生成。'}]};
 const render=await harness('ApprovalBatch.jsx','default',[batch,'',false,false,null,false]),navigations=[];
 const tree=render({rows:[data],action:'revalidate',onClose(){},onReturnConfig:value=>navigations.push(value)});
 assert.match(renderToStaticMarkup(tree),/缺少可信会话执行目标/);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='返回所属配置 ↗').props.onClick();assert.deepEqual(navigations,[destination]);
 assert.ok(elements(tree).find(e=>e.type==='button'&&String(e.props.children).includes('确认批量重新校验')).props.disabled);
});
test('one-click cleanup freezes only the current tab and search results',async()=>{
 const records=[{id:'a',name:'员工资料保护',scope_type:'agent',status:'applied',can_clear:true,created_at:'2026-10-19T00:00:00Z'},
  {id:'b',name:'预算保护',scope_type:'agent',status:'rejected',can_clear:true,created_at:'2026-10-19T00:00:00Z'},
  {id:'c',name:'员工资料新版',scope_type:'agent',status:'pending',can_clear:false,created_at:'2026-10-19T00:00:00Z'}];
 const render=await harness('PolicyApprovals.jsx','default',[null,{records},null,'processed','员工','',false,0,[],null,false]),calls=[];
 const props={api:async()=>({records}),post:async(...args)=>calls.push(args),navigation:{},navigate(){}};
 let tree=render(props);elements(tree).find(e=>e.type==='button'&&e.props.children==='清理当前结果').props.onClick();tree=render(props);
 let modal=elements(tree).find(e=>e.type?.name==='ApprovalBatch');assert.equal(modal.props.action,'clear');assert.deepEqual(modal.props.rows.map(r=>r.id),['a']);assert.equal(calls.length,0);
 modal.props.onClose();tree=render(props);elements(tree).find(e=>e.type==='button'&&e.props.children==='全选当前结果').props.onClick();tree=render(props);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='清理所选').props.onClick();tree=render(props);modal=elements(tree).find(e=>e.type?.name==='ApprovalBatch');assert.deepEqual(modal.props.rows.map(r=>r.id),['a']);
});
test('cleaned records can be selected and restored without an approval or apply action',async()=>{
 const records=[{id:'a',name:'员工资料保护',scope_type:'agent',status:'applied',can_clear:true,cleared:true,can_restore:true,created_at:'2026-10-19T00:00:00Z'}];
 const render=await harness('PolicyApprovals.jsx','default',[null,{records,cleared_count:1},null,'processed','','',false,0,[],null,true]);
 const props={api:async()=>({records}),navigation:{},navigate(){}};let tree=render(props),html=renderToStaticMarkup(tree);
 assert.match(html,/返回审批列表|正在查看已清理记录/);assert.doesNotMatch(html,/>清理所选<|>批量应用<|>批量批准</);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='恢复当前结果').props.onClick();tree=render(props);assert.equal(elements(tree).find(e=>e.type?.name==='ApprovalBatch').props.action,'restore');
});
test('cleanup confirmation explains retention and requires acknowledgement',async()=>{
 const data={id:'a',name:'员工资料保护',scope_id:'agent-a',scope_type:'agent',target_name:'DeepSeek Harness',status:'applied',can_clear:true,clearance_hash:'hash'},batch={action:'clear',entries:[{id:'a',data,requestKey:'once'}]};
 const render=await harness('ApprovalBatch.jsx','default',[batch,'',false,false,null,false]),calls=[];
 const tree=render({rows:[data],action:'clear',api:async()=>data,post:async()=>calls.push('write'),onClose(){}}),html=renderToStaticMarkup(tree);
 assert.match(html,/保留原始记录与审计/);assert.match(html,/已生效策略继续执行/);assert.doesNotMatch(html,/查看变更内容/);
 const button=elements(tree).find(e=>e.type==='button'&&String(e.props.children).includes('确认清理记录'));assert.ok(button.props.disabled);await button.props.onClick();assert.equal(calls.length,0);
});
