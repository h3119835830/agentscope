import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
async function loadComponent(file,reactOverride) {
 const result=await build({entryPoints:[join(base,file)],bundle:true,platform:'node',format:'cjs',external:['react'],loader:{'.css':'empty'},write:false});
 const module=new Module(join(base,'.archive-domain-test.cjs'));module.paths=Module._nodeModulePaths(base);const originalRequire=module.require.bind(module);module.require=id=>id==='react'&&reactOverride?reactOverride:originalRequire(id);module._compile(result.outputFiles[0].text,join(base,'.archive-domain-test.cjs'));
 return module.exports;
}
const {default:DomainGraph}=await loadComponent('DomainGraph.jsx');
const {default:ArchiveDomains,archiveDomainPath}=await loadComponent('ArchiveDomains.jsx');
const graph={task_id:'t',version:4,versions:[{version:4}],live:false,nodes:[
 {key:'v4:task',kind:'domain',role:'task',domain_id:44,title:'任务域',labels:['source'],live:true},
 {key:'v4:runner:123',kind:'process',role:'runner',pid:123,title:'历史 runner 123',live:true},
 {key:'unrecorded',kind:'process',role:'watch',pid:null,title:'未记录进程'}
],edges:[{from:'v4:task',to:'v4:runner:123',kind:'binding',label:'绑定'}]};
const render=props=>renderToStaticMarkup(React.createElement(DomainGraph,{graph,files:{records:[]},fresh:true,...props}));
test('archive graph renders recorded historical PID without live verification or invented PID',()=>{
 const html=render({historical:true,graph:{...graph,live:true}});
 assert.match(html,/历史 PID/);assert.match(html,/123/);assert.doesNotMatch(html,/未记录进程|绑定已核验|class="live"|域已核验/);assert.match(html,/不代表当前在线/);
});
test('default live graph keeps excluding processes when graph is not live or observation is stale',()=>{
 assert.doesNotMatch(render({}),/历史 runner 123/);
 assert.doesNotMatch(render({graph:{...graph,live:true},fresh:false}),/历史 runner 123/);
 assert.match(render({graph:{...graph,live:true}}),/历史 runner 123/);
 assert.match(render({graph:{...graph,live:true}}),/绑定已核验/);
});
test('archive request paths remain task scoped and encoded',()=>{
 assert.equal(archiveDomainPath('task/1',null),'/api/tasks/task%2F1/archive/domains');
 assert.equal(archiveDomainPath('task/1',4),'/api/tasks/task%2F1/archive/domains?version=4');
 assert.equal(archiveDomainPath('task/1',null,'v4:task'),'/api/tasks/task%2F1/archive/domains/v4%3Atask');
});
test('archive graph starts folded with no rendered evidence or API call',()=>{
 let calls=0;const html=renderToStaticMarkup(React.createElement(ArchiveDomains,{task:'t',api:()=>{calls++;}}));
 assert.match(html,/历史域、进程与 DSL/);assert.doesNotMatch(html,/graph-canvas|record-code|<details[^>]*open/);assert.equal(calls,0);
});

test('replay domain tab starts expanded but its initial client effects only read the archived task graph',async()=>{
 const effects=[],calls=[];
 const hooks={...React,useLayoutEffect:()=>{},useState:initial=>[typeof initial==='function'?initial():initial,()=>{}],useRef:initial=>({current:initial}),useEffect:effect=>effects.push(effect)};
 const {default:ReplayDomains}=await loadComponent('ArchiveDomains.jsx',hooks);
 const html=renderToStaticMarkup(React.createElement(ReplayDomains,{task:'old/rq5',defaultOpen:true,api:async path=>{calls.push(path);return {nodes:[],edges:[],versions:[]};}}));
 assert.match(html,/<details[^>]*open/);for(const effect of effects)effect();await Promise.resolve();
 assert.deepEqual(calls,['/api/tasks/old%2Frq5/archive/domains']);assert.ok(calls.every(path=>!path.includes('/managed/')&&!path.includes('/workbench')));
});
test('history without a replay task keeps native history search and has no fixed research shortcut',async()=>{
 const {default:TaskArchive}=await loadComponent('TaskArchive.jsx');
 const navigation={page:'history',archiveTask:'',archivePane:'domains',query:'',filter:'history',listPage:0};
 const html=renderToStaticMarkup(React.createElement(TaskArchive,{navigation,navigate:()=>{},api:()=>{throw new Error('server render must not fetch live task');}}));
 assert.match(html,/任务回放/);assert.match(html,/搜索历史任务/);assert.doesNotMatch(html,/查看全部旧任务|OpenAgentSafety 场景/);assert.match(html,/运行前策略、运行时策略、执行审计和进程与域图/);assert.doesNotMatch(html,/<dialog|新建任务|当前工作台任务/);
 const all=renderToStaticMarkup(React.createElement(TaskArchive,{navigation:{...navigation,filter:'all'},navigate:()=>{},api:()=>{}}));assert.doesNotMatch(all,/查看全部旧任务/);
});

test('history filters reset pagination without injecting a research query',async()=>{
 const hooks={...React,useLayoutEffect:()=>{},useState:initial=>[typeof initial==='function'?initial():initial,()=>{}],useRef:initial=>({current:initial}),useEffect:()=>{}};
 const {default:TaskArchive}=await loadComponent('TaskArchive.jsx',hooks),patches=[];
 const tree=TaskArchive({navigation:{page:'history',archiveTask:'',query:'previous',filter:'history',listPage:3},navigate:patch=>patches.push(patch),api:()=>{throw new Error('not a live workflow');}});
 function find(node,type){if(!node||typeof node!=='object')return null;if(node.type===type)return node;for(const child of [node.props?.children].flat(Infinity)){const found=find(child,type);if(found)return found;}return null;}
 find(tree,'select').props.onChange({target:{value:'all'}});find(tree,'input').props.onChange({target:{value:'用户真实会话'}});
 assert.deepEqual(patches,[{filter:'all',listPage:0},{query:'用户真实会话',listPage:0}]);
 const html=renderToStaticMarkup(tree);assert.match(html,/>未结束</);assert.doesNotMatch(html,/OpenAgentSafety|RQ5|含失败|<thead/);
});

const {ArchiveReplay,PolicyDetailContent,ArchiveBody}=await loadComponent('TaskArchiveDetails.jsx');
test('replay is a full width task page with scoped page selector and no dialog or live workbench',()=>{
 const html=renderToStaticMarkup(React.createElement(ArchiveReplay,{task:'outside',tasks:[{id:'one',name:'本页一'}],api:()=>{},pane:'domains'}));
 assert.match(html,/任务回放页面/);assert.match(html,/本页历史任务/);assert.match(html,/outside · 创建时间未记录 · outside（当前任务不在本页）/);assert.match(html,/本页一/);assert.match(html,/执行监控/);assert.match(html,/>运行前<\/button>/);assert.equal((html.match(/role="tab"/g)||[]).length,4);assert.match(html,/任务概况/);assert.match(html,/结束结果/);assert.doesNotMatch(html,/<dialog|恢复任务|当前工作台任务/);
});
test('replay initial client read uses the explicit selected archive identity only',async()=>{
 const effects=[],calls=[],hooks={...React,useLayoutEffect:()=>{},useState:initial=>[typeof initial==='function'?initial():initial,()=>{}],useRef:initial=>({current:initial}),useEffect:effect=>effects.push(effect)};
 const {ArchiveReplay:Replay}=await loadComponent('TaskArchiveDetails.jsx',hooks);
 renderToStaticMarkup(React.createElement(Replay,{task:'old/rq5',tasks:[{id:'other'}],api:async (...args)=>{calls.push(args);return {};}}));
 const prior={window:globalThis.window,document:globalThis.document,requestAnimationFrame:globalThis.requestAnimationFrame,cancelAnimationFrame:globalThis.cancelAnimationFrame};Object.assign(globalThis,{window:{scrollTo:()=>{}},document:{getElementById:()=>null},requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{}});try{effects.forEach(e=>e());await Promise.resolve();assert.deepEqual(calls,[['/api/tasks/old%2Frq5/archive']]);}finally{Object.assign(globalThis,prior);}
});
test('policy detail restores four keyboard reachable subpages while DSL remains exact statement',()=>{
 const html=renderToStaticMarkup(React.createElement(PolicyDetailContent,{record:{statement:'保留保护',policy_type:'per_event',compilation:{scope:'statement',dsl:'exact-fragment'},bundle_compilation:{scope:'candidate_bundle',dsl:'inherited-bundle'}}}));
 for(const label of ['语句与类型','上下文','DSL','加载'])assert.ok(html.includes(label));assert.match(html,/role="tablist"/);assert.match(html,/exact-fragment/);assert.match(html,/<details[^>]*><summary>完整候选包/);
 const context=renderToStaticMarkup(React.createElement(PolicyDetailContent,{pane:'context',record:{evidence:[{role:'input',path:'/source/a',read_verified:true,content_hash:'hash123',id:'e1'}]}}));
 for(const text of ['/source/a','hash123','读取核验','e1'])assert.ok(context.includes(text));
});
test('startup retains lazy evidence behind one closed technical disclosure',()=>{
 const html=renderToStaticMarkup(React.createElement(ArchiveBody,{pane:'startup',task:'t',data:{stages:[]},api:()=>{throw Error('SSR should not fetch');}}));
 const technical=html.indexOf('<summary>技术详情</summary>');assert.ok(technical>0);for(const text of ['工作区文件证据','策略生成过程','生成工具结果','策略版本与加载记录'])assert.ok(html.indexOf(text)>technical);assert.equal((html.match(/<summary>技术详情<\/summary>/g)||[]).length,1);assert.doesNotMatch(html,/<details[^>]*open|载入更早记录/);
});

test('historical graph only associates loaded operation resources from the same task and version',()=>{
 const html=render({historical:true,files:{records:[{id:'own',task_id:'t',domain_id:44,version:4,target:'/same-version'},{id:'old',task_id:'t',domain_id:44,version:3,target:'/old-version'},{id:'foreign',task_id:'other',domain_id:44,version:4,target:'/other-task'}]}});
 assert.match(html,/same-version/);assert.doesNotMatch(html,/old-version|other-task/);
});

test('same-name replay selector labels include creation time and exact identity suffix',async()=>{
 const {replayTaskLabel,ArchiveReplaySource}=await loadComponent('TaskArchiveDetails.jsx');
 const a=replayTaskLabel({id:'12345678aaaa',name:'safety-delete-config',created_at:'2026-10-01T10:00:00Z'}),b=replayTaskLabel({id:'abcdef12bbbb',name:'safety-delete-config',created_at:'2026-10-02T10:00:00Z'});
 assert.notEqual(a,b);assert.match(a,/12345678/);assert.match(b,/abcdef12/);assert.match(a,/2026/);
 const html=renderToStaticMarkup(React.createElement(ArchiveReplaySource,{task:'t',header:{repository:{repo:'OpenAgentSafety',commit_sha:'abcdef123456'},source:{},workspace:'/snapshot'}}));
 assert.match(html,/<dt>场景来源<\/dt><dd>OpenAgentSafety<\/dd>/);assert.match(html,/<dt>来源提交<\/dt><dd>abcdef123456<\/dd>/);assert.match(html,/<dt>来源实例<\/dt><dd>未记录<\/dd>/);assert.match(html,/<dt>来源工作区<\/dt><dd>未记录<\/dd>/);assert.match(html,/<dt>执行快照<\/dt><dd>\/snapshot<\/dd>/);
});

test('historical monitor defaults to relationship graph with four distinct internal modes',async()=>{
 const {ArchiveMonitor}=await loadComponent('TaskArchiveDetails.jsx');
 const html=renderToStaticMarkup(React.createElement(ArchiveMonitor,{task:'old',api:()=>{throw Error('SSR must not request');}}));
 for(const text of ['关系图','OS 文件操作','关联进程','权限范围'])assert.ok(html.includes(text));
 assert.match(html,/id="archive-monitor-graph"[^>]*aria-selected="true"/);assert.doesNotMatch(html,/<th>历史 PID|完整结构化 Scope 未记录|<th>操作 \/ 来源/);
});

test('source directories and historical missing materials default to closed disclosures',async()=>{
 const {ArchiveReplaySource}=await loadComponent('TaskArchiveDetails.jsx'),{HistoricalGraphNotice}=await loadComponent('ArchiveDomains.jsx');
 const source=renderToStaticMarkup(React.createElement(ArchiveReplaySource,{task:'identity',header:{repository:{repo:'OpenAgentSafety'},source:{path:'/source'},workspace:'/execution'}}));
 for(const value of ['OpenAgentSafety','identity','/source','/execution'])assert.ok(source.indexOf(value)>source.indexOf('<summary>技术详情</summary>'));assert.match(source,/<details><summary>技术详情/);assert.doesNotMatch(source,/<details[^>]*open/);
 const notice=renderToStaticMarkup(React.createElement(HistoricalGraphNotice,{graph:{notice:'历史材料不完整',missing_sources:[{key:'v1:baseline',role:'baseline',reason:'missing_hash'}]}}));
 assert.match(notice,/<details[^>]*><summary>历史材料说明（1 项缺失或未核验）/);assert.match(notice,/missing_hash/);assert.match(notice,/历史材料不完整/);assert.doesNotMatch(notice,/<details[^>]*open/);
});

test('archive policy restores six-column statement records and audit retains workbench rows',async()=>{
 const {ArchivePolicyRows,ArchiveAuditRows}=await loadComponent('TaskArchiveDetails.jsx');
 const policy=renderToStaticMarkup(React.createElement(ArchivePolicyRows,{records:[{id:'runtime:j:statement:0',record_kind:'statement',statement:'保留测试文件保护',policy_type:'per_event',statement_effect:'retained',review_status:'approved',loading:{loaded:true},targets:['/tests']}],onOpen:()=>{}}));
 assert.match(policy,/class="archive-records-table archive-policy-table"/);for(const label of ["时间 / 作业","策略语句","生成 / 审核","编译 / 加载","版本","详情","语句 / DSL"])assert.ok(policy.includes(label));assert.match(policy,/保留测试文件保护/);assert.match(policy,/历史沿用规则/);assert.match(policy,/archive-policy-runtime:j:statement:0/);assert.doesNotMatch(policy,/本次未记录策略语句/);
 const missing=renderToStaticMarkup(React.createElement(ArchivePolicyRows,{records:[{id:'guide:0',statement:'只作指导',policy_type:'semantic_only',detail_available:false}],onOpen:()=>{}}));assert.match(missing,/不生成 OS 规则/);assert.match(missing,/<button[^>]*disabled[^>]*>材料未记录<\/button>/);
 const audit=renderToStaticMarkup(React.createElement(ArchiveAuditRows,{records:[{id:'a',operation:'unlink',target:'/tests/a.py',source:'independent_probe',result:'denied',pid:12,domain_id:33}],onOpen:()=>{}}));
 assert.match(audit,/class="audit-record compact-audit"/);assert.match(audit,/删除 · \/tests\/a.py/);assert.match(audit,/独立验收探针/);assert.match(audit,/历史 PID 12/);assert.doesNotMatch(audit,/<table/);
});
test('runtime default reads actual statements and saved Hook triggers; jobs only read in the separate generation collection',async()=>{
 const run=async(component,props)=>{const effects=[],calls=[],hooks={...React,useState:initial=>[typeof initial==='function'?initial():initial,()=>{}],useRef:initial=>({current:initial}),useEffect:effect=>effects.push(effect)};const exports=await loadComponent('TaskArchiveDetails.jsx',hooks);renderToStaticMarkup(React.createElement(exports[component],{...props,api:async path=>{calls.push(path);return {records:[]};}}));for(const effect of effects)effect();await Promise.resolve();return calls;};
 assert.deepEqual(await run('ArchiveBody',{pane:'runtime',data:{stages:[]},task:'old/rq5'}),['/api/tasks/old%2Frq5/archive/policies?stage=runtime&view=statements_only&limit=50','/api/tasks/old%2Frq5/archive/runtime-hooks?limit=50']);
 assert.deepEqual(await run('GenerationCollection',{stage:'runtime',task:'old/rq5'}),['/api/tasks/old%2Frq5/archive/policies?stage=runtime&view=jobs&limit=50']);
});
test('live and archived workbench share pure record drawer and monitor components without importing live workbench into replay',()=>{
 const require=createRequire(import.meta.url),fs=require('node:fs');
 const live=fs.readFileSync(join(base,'ManagedWorkbench.jsx'),'utf8'),monitor=fs.readFileSync(join(base,'RuntimeOverview.jsx'),'utf8'),archive=fs.readFileSync(join(base,'TaskArchiveDetails.jsx'),'utf8'),views=fs.readFileSync(join(base,'WorkbenchRecordViews.jsx'),'utf8');
 for(const component of ['PolicyRecordRow','AuditRecordRow','RecordDrawerFrame']){assert.ok(live.includes('<'+component));assert.ok(archive.includes('<'+component));}
 assert.ok(monitor.includes('<RuntimeModeTabs'));assert.ok(archive.includes('<RuntimeModeTabs'));assert.doesNotMatch(archive,/import .*ManagedWorkbench|import .*RuntimeOverview/);assert.doesNotMatch(views,/fetch\(|api\(|post\(|setInterval\(/);
});

test('bootstrap failure is a pure compact notice with factual diagnosis and independently authorized recovery actions',async()=>{
 const {default:Notice,bootstrapFailureSummary,bootstrapDiagnosticText}=await loadComponent('BootstrapFailureNotice.jsx');
 assert.equal(bootstrapDiagnosticText({code:'engine_pattern_limit_exceeded',max_utf8_bytes:64}), '执行引擎单个路径模式最多 64 UTF-8 字节。');
 assert.equal(bootstrapDiagnosticText({raw_provider_text:'must-not-export'}),'');
 assert.match(bootstrapFailureSummary({code:'engine_pattern_limit_exceeded'}),/路径超过执行引擎长度上限/);
 const noActions=renderToStaticMarkup(React.createElement(Notice,{failure:{error:'Pi settled without a server-validated submission'},candidateId:'unapproved',onViewCandidate:()=>{throw Error('never automatic');},onRegenerate:()=>{throw Error('never automatic');}}));
 assert.match(noActions,/尚未通过服务端校验/);assert.match(noActions,/Pi settled/);assert.match(noActions,/<details><summary>失败详情/);assert.doesNotMatch(noActions,/查看恢复候选|重新生成<\/button>|<details[^>]*open/);
 const calls=[];const element=Notice({failure:{code:'engine_pattern_limit_exceeded',targets:[{path:'/exact-target',utf8_bytes:85}],max_utf8_bytes:63},candidateId:'exact-candidate',canViewCandidate:true,canRegenerate:true,onViewCandidate:id=>calls.push(['view',id]),onRegenerate:()=>calls.push(['regenerate'])});
 const visit=node=>!node||typeof node!=='object'?[]:[node,...(Array.isArray(node.props?.children)?node.props.children:[node.props?.children]).flatMap(visit)];
 const buttons=visit(element).filter(n=>n.type==='button');assert.equal(calls.length,0);assert.equal(buttons.length,2);buttons[0].props.onClick();assert.deepEqual(calls,[['view','exact-candidate']]);
 const html=renderToStaticMarkup(element);assert.match(html,/85 字节（上限 63）/);assert.match(html,/原失败记录保留/);
});

test('embedded preparation keeps confirmation and evidence folds without a second strategy table or task summary',async()=>{
 const bootstrap={context:{context_hash:'context',assets:[]},proposals:[{state:'validated',content_hash:'proposal',proposal:{draft:{atoms:[],guidance:[]}}}],jobs:[],tool_events:[]};
 let nulls=0;const hooks={...React,useState:initial=>[initial===null?(++nulls===1?bootstrap:{state:{phase:'policy_review',version:0}}):initial===true?false:initial,()=>{}],useEffect:()=>{}};
 const {TaskRecord}=await loadComponent('TaskHub.jsx',hooks);
 const html=renderToStaticMarkup(React.createElement(TaskRecord,{task:{id:'candidate'},embedded:true,api:()=>{},post:()=>{throw Error('no automatic confirmation');}}));
 assert.match(html,/确认策略并启动 Agent/);for(const text of ['工作区文件证据','生成过程与工具结果','策略版本'])assert.ok(html.includes(text));assert.doesNotMatch(html,/task-record-summary|启动前策略记录|task-policy-table|返回任务记录/);
});

test('startup recovery only reads on mount and explicit candidate action navigates to returned target without confirming',async()=>{
 const recovery={eligible:true,origin:{context_hash:'origin-context',manifest_hash:'origin-manifest'},failure:{summary:'目标路径过长'},candidate:{task_id:'new-task',proposal_hash:'proposal-hash',status:'awaiting_review'}};
 const effects=[],calls=[],opened=[],hooks={...React,useState:initial=>[initial===null?recovery:initial,()=>{}],useRef:initial=>({current:initial}),useEffect:effect=>effects.push(effect)};
 const {default:Recovery}=await loadComponent('StartupRecovery.jsx',hooks);
 const node=Recovery({task:'old/task',api:async path=>{calls.push(['GET',path]);return recovery;},post:async(path,body)=>{calls.push(['POST',path,body]);return {target:{task_id:'new-task',phase:'policy_review',gate:'waiting_confirmation'}};},onOpenTask:id=>opened.push(id)});
 assert.deepEqual(calls,[]);assert.deepEqual(opened,[]);const cleanups=effects.map(effect=>effect());await Promise.resolve();assert.deepEqual(calls,[['GET','/api/managed/tasks/old%2Ftask/startup/recovery']]);
 const notice=node.props.children.find(child=>child?.props?.onViewCandidate);await notice.props.onViewCandidate();
 assert.deepEqual(calls[1],['POST','/api/managed/tasks/old%2Ftask/startup/recovery',{action:'reuse',expected_context_hash:'origin-context',expected_manifest_hash:'origin-manifest',expected_candidate_task_id:'new-task',expected_candidate_proposal_hash:'proposal-hash'}]);assert.deepEqual(opened,['new-task']);assert.equal(calls.length,2);cleanups.forEach(cleanup=>cleanup?.());
});

test('verified recovery readiness is distinct from original failure, while generating link offers navigation only',async()=>{
 const {default:Notice}=await loadComponent('BootstrapFailureNotice.jsx');
 const ready=renderToStaticMarkup(React.createElement(Notice,{failure:{summary:'原路径超过上限'},candidateId:'recovered-task',recoveryReady:true,canViewCandidate:true,onViewCandidate:()=>{}}));
 assert.match(ready,/原生成失败/);assert.match(ready,/恢复候选待确认/);assert.match(ready,/恢复任务：recovered-task/);assert.match(ready,/候选待人工确认/);
 const generating=renderToStaticMarkup(React.createElement(Notice,{progressTaskId:'pending-task',progressStatus:'generating',onViewProgress:()=>{}}));assert.match(generating,/恢复候选生成中/);assert.match(generating,/查看恢复进度/);assert.doesNotMatch(generating,/record-tag[^>]*>恢复候选待确认|record-tag[^>]*>已加载|record-tag[^>]*>已生效/);
 const recovery={eligible:true,origin:{context_hash:'ctx',manifest_hash:'manifest'},link:{task_id:'pending-task',status:'generating',phase:'generating',gate:'waiting_policy'}},opened=[],calls=[];
 const hooks={...React,useState:initial=>[initial===null?recovery:initial,()=>{}],useRef:initial=>({current:initial}),useEffect:()=>{}};
 const {default:Recovery}=await loadComponent('StartupRecovery.jsx',hooks);const node=Recovery({task:'old',api:()=>{},post:()=>calls.push('POST'),onOpenTask:id=>opened.push(id)}),notice=node.props.children.find(child=>child?.props?.onViewProgress);
 assert.equal(notice.props.canRegenerate,false);assert.equal(notice.props.canViewCandidate,false);notice.props.onViewProgress(notice.props.progressTaskId);assert.deepEqual(opened,['pending-task']);assert.deepEqual(calls,[]);
});

test('targetless guidance rows show distinct compact real statements while execution rows keep path titles',async()=>{
 const {workbenchPolicyTitle,PolicyRecordRow}=await loadComponent('WorkbenchRecordViews.jsx');
 const guidance=[{statement:'先检查当前结果，再说明本次修改。',policy_type:'semantic_only'},{statement:'保留用户提供的配置，说明需要人工确认的内容。',policy_type:'semantic_only'}];
 const titles=guidance.map(r=>workbenchPolicyTitle(r,'/snapshot','任务指导'));assert.notEqual(titles[0],titles[1]);assert.equal(titles[0],guidance[0].statement);
 assert.equal(workbenchPolicyTitle({targets:['/snapshot/tests/a.py'],statement:'实际执行语句'},'/snapshot','任务指导'),'tests/a.py');
 const long='指导'.repeat(80),summary=workbenchPolicyTitle({statement:long},'/snapshot','任务指导');assert.equal(Array.from(summary).length,101);assert.ok(summary.endsWith('…'));
 const html=renderToStaticMarkup(React.createElement(PolicyRecordRow,{title:titles[0],statementSummary:true,status:'任务指导',onOpen:()=>{}}));assert.match(html,/record-statement-summary/);assert.match(html,/先检查当前结果，再说明本次修改。/);
});
