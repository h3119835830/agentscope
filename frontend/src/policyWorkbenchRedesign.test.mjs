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
async function harness(entry,exported='default'){
 const built=await build({entryPoints:[join(base,entry)],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
 const states=[],refs=[];let index=0,refIndex=0;const react={...React,useState:init=>{const i=index++;if(!(i in states))states[i]=typeof init==='function'?init():init;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v]},useRef:init=>{const i=refIndex++;return refs[i]||={current:init}},useEffect:()=>{}};
 const name=join(base,'.policy-redesign-test.cjs'),mod=new Module(name);mod.paths=Module._nodeModulePaths(base);const original=mod.require.bind(mod);mod.require=id=>id==='react'?react:original(id);mod._compile(built.outputFiles[0].text,name);
 return (...props)=>{globalThis.document={activeElement:null};index=0;refIndex=0;return mod.exports[exported](...props)};
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
 const data={id:'proposal',scope_type:'agent',target_name:'DeepSeek Harness',status:'pending',can_apply:true,created_at:'2026-10-11T01:00:00Z',documents:[{id:'d',name:'Protect secret',original_dsl:'source AGENT = exec "**/node"'}],previous_documents:[],records:[{id:'r',document_id:'d',statement:'Protect secret',clauses:[{effect:'block',operation:'open',target:'/w/0/.env'}]}],targets:[{id:'agent',name:'DeepSeek Harness',active:true}],total_affected_count:1};
 const props={data,onClose(){},onDecision:async(...args)=>decisions.push(args)};let tree=render(props);assert.equal(decisions.length,0);assert.match(renderToStaticMarkup(tree),/全部工作区与会话/);assert.match(renderToStaticMarkup(tree),/新增/);
 elements(tree).find(e=>e.type==='button'&&e.props.children==='完整 DSL').props.onClick();tree=render(props);assert.equal(decisions.length,0);assert.match(renderToStaticMarkup(tree),/node/);
 await elements(tree).find(e=>e.type==='button'&&e.props.children==='批准并应用').props.onClick();assert.equal(decisions[0][1],'confirm');
 tree=render({...props,data:{...data,status:'stale',can_apply:false}});assert.ok(!elements(tree).some(e=>e.props?.children==='批准并应用'));
});
test('approval deep links retain only the record identity',()=>{
 const url=navigationTarget('http://localhost/?view=workbench',{page:'approvals',approvalId:'approval-one'}),n=readNavigation('http://localhost'+url);assert.equal(n.page,'approvals');assert.equal(n.approvalId,'approval-one');assert.doesNotMatch(url,/proposal_hash|documents/);
});
test('runtime approval shows an exact task scope and readable before/after without applying on view',async()=>{
 const render=await harness('PolicyApprovals.jsx','ApprovalDetail');let decisions=[];
 const data={id:'runtime:job',kind:'runtime',scope_type:'session',target_name:'Task A',status:'pending',can_apply:true,can_reject:true,created_at:'2026-10-11T01:00:00Z',documents:[],records:[],change_items:[{label:'可写目录',before:'.',after:'src'}],targets:[{id:'task-a',name:'Task A',scope_label:'当前任务会话',application_label:'确认后重建当前任务执行域'}],total_affected_count:1};
 const tree=render({data,onClose(){},onDecision:async(...args)=>decisions.push(args)}),html=renderToStaticMarkup(tree);
 assert.match(html,/权限变更对照/);assert.match(html,/当前任务会话/);assert.match(html,/Task A/);assert.doesNotMatch(html,/全部工作区与会话|完整 DSL|PolicyIR|原始 JSON/);assert.equal(decisions.length,0);
 await elements(tree).find(e=>e.type==='button'&&e.props.children==='批准并应用').props.onClick();assert.equal(decisions[0][0].id,'runtime:job');assert.equal(decisions[0][1],'confirm');
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
 const proposal={id:'p',state:'pending',documents:[],result:{compilations:[]},targets:[],approval:{status:'stale',can_apply:false,reason:'Agent 环境已经变化，需要重新校验。'}};
 const tree=render({data:{scope_id:'agent',documents:[],records:[]},proposal,onReview:()=>handoffs++});
 assert.match(renderToStaticMarkup(tree),/需重新校验/);
 const button=elements(tree).find(e=>e.type==='button'&&e.props.children==='前往审批');assert.ok(button.props.disabled);
 await button.props.onClick();assert.equal(handoffs,0);
});
test('revalidating a stale draft uses the new proposal status and hands off only that proposal',async()=>{
 const render=await harness('ActPlanePolicies.jsx','DslEditor');let handedOff='';
 const old={id:'old',state:'pending',documents:[],base_hash:'old-base',base_revision:1,result:{},targets:[],approval:{status:'stale',can_apply:false}};
 const fresh={...old,id:'fresh',base_hash:'current',base_revision:2,approval:{status:'pending',can_apply:true}};
 const props={data:{scope_id:'agent',revision:2,document_hash:'current',documents:[],records:[]},proposal:old,approval:old.approval,onValidate:async()=>fresh,onReview:p=>{handedOff=p.id;},onClose:()=>{}};
 let tree=render(props);await elements(tree).find(e=>e.type==='button'&&e.props.children==='保存并校验').props.onClick();tree=render(props);
 const handoff=elements(tree).find(e=>e.type==='button'&&e.props.children==='前往审批');assert.equal(handoff.props.disabled,false);
 await handoff.props.onClick();assert.equal(handedOff,'fresh');
});
