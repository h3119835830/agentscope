// UI sample data only. No API, process discovery, policy load, or authorization.
const taskDrafts={coding:taskDraft,research:clone(taskDraft)};
let overviewView='tasks',connectionScope='all',sessionOpen=false,relationView='processes',systemView='baseline';
let approvalScope='all',librarySearch='',libraryCategory='all',graphNodes=new Map();
const taskInfo={coding:{name:'登录表单修复',id:'S-DEMO',agent:'编码 DSH',workspace:'/workspace',root:'D-A'},research:{name:'研究任务 B',id:'S-RESEARCH',agent:'研究 DSH',workspace:'/workspace/research',root:'D-B'}};
const currentTask=()=>taskInfo[domain==='D-B'?'research':'coding'];
function setDomain(value){domain=value;taskDraft=taskDrafts[value==='D-B'?'research':'coding'];sessionFilter='all';sessionSearch='';}
function openSession(value,view='permissions'){setDomain(value);page='sessions';sessionOpen=true;tab=view;}
function tabBar(group,items,value){return `<div class="tabs section-tabs" role="tablist" aria-label="${({overview:'总览视图',session:'会话视图',system:'系统设置'})[group]}">${items.map(([key,name])=>`<button role="tab" id="${group}-${key}" aria-controls="${group}-panel" aria-selected="${value===key}" tabindex="${value===key?'0':'-1'}" data-view="${group}" data-value="${key}" class="${value===key?'on':''}">${name}</button>`).join('')}</div>`;}
function setView(group,value){if(group==='overview')overviewView=value;else if(group==='session')tab=value;else systemView=value;render();}
function domainOptions(){return `<label class="sr" for="domain">查看策略域</label><select id="domain" aria-label="查看策略域"><option value="D-A" ${domain==='D-A'?'selected':''}>主 Agent / D-A</option><option value="D-A1" ${domain==='D-A1'?'selected':''}>测试子 Agent / D-A1</option><option value="D-B" ${domain==='D-B'?'selected':''}>研究 Agent / D-B</option></select>`;}
function diagram(nodes,edges,{kind='tasks',toolbar='',footer='关系为样例，未取得当前连接或策略绑定证据。'}={}){
  graphNodes=new Map(nodes.map(n=>[n.id,n]));
  return `<section class="diagram-panel" aria-label="${({tasks:'全局任务连接图',services:'系统服务链路图',processes:'会话执行进程树',domains:'策略域继承图'})[kind]}"><div class="diagram-toolbar">${toolbar}<span class="muted">点击节点查看详情</span></div><div class="diagram-scroll" tabindex="0" aria-label="可滚动关系图"><div class="diagram-canvas ${kind==='services'?'services':''}"><svg class="diagram-lines" aria-hidden="true"><defs><marker id="link-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="#9aaec3"/></marker></defs>${edges.map(e=>`<g data-edge-from="${e[0]}" data-edge-to="${e[1]}" data-edge-label="${esc(e[2])}" data-edge-kind="${e[3]||'connection'}"><path fill="none" stroke="#9aaec3" stroke-width="1.3" marker-end="url(#link-arrow)"/><text text-anchor="middle"></text></g>`).join('')}</svg>${nodes.map(n=>`<button class="graph-node ${n.kind} ${n.selected?'selected':''}" data-node="${n.id}" style="left:${n.x}%;top:${n.y}px" aria-label="查看 ${esc(n.name)}"><span class="node-kind">${esc(n.type)}<span aria-hidden="true">↗</span></span><strong>${esc(n.name)}</strong><span class="node-meta">${esc(n.meta)}</span></button>`).join('')}</div></div><div class="diagram-footer"><span>${footer}</span><span class="legend-item"><i></i>${kind==='processes'?'父子进程':kind==='domains'?'约束继承':'连接 / 关联'}</span></div></section>`;
}
function drawEdges(){
  const canvas=document.querySelector('.diagram-canvas');if(!canvas)return;
  const origin=canvas.getBoundingClientRect(),svg=canvas.querySelector('svg');svg.setAttribute('viewBox',`0 0 ${origin.width} ${origin.height}`);
  for(const edge of canvas.querySelectorAll('[data-edge-from]')){
    const from=canvas.querySelector(`[data-node="${edge.dataset.edgeFrom}"]`),to=canvas.querySelector(`[data-node="${edge.dataset.edgeTo}"]`);if(!from||!to)continue;
    const a=from.getBoundingClientRect(),b=to.getBoundingClientRect(),x=a.left-origin.left+a.width/2,y=a.bottom-origin.top,tx=b.left-origin.left+b.width/2,ty=b.top-origin.top,mid=(y+ty)/2;
    edge.querySelector('path').setAttribute('d',`M${x},${y} C${x},${mid} ${tx},${mid} ${tx},${ty-7}`);
    const label=edge.querySelector('text');label.setAttribute('x',(x+tx)/2);label.setAttribute('y',mid-7);label.textContent=edge.dataset.edgeLabel;
  }
}
const graphResize=new ResizeObserver(()=>drawEdges());
function renderOverview(){
  const tabs=tabBar('overview',[['tasks','当前连接'],['services','服务链路']],overviewView);
  if(overviewView==='services'){
    const nodes=[{id:'api',kind:'service',type:'控制服务',name:'AgentScope API',meta:'状态未观测',x:50,y:18},{id:'pi',kind:'service',type:'策略分析',name:'Pi',meta:'生成候选 · 无执行授权',x:19,y:148},{id:'broker',kind:'service',type:'可信执行',name:'Broker',meta:'批准 / 加载边界',x:50,y:148},{id:'dsh-service',kind:'agent',type:'任务执行',name:'DSH',meta:'原生 / 受管实例',x:81,y:148},{id:'actplane',kind:'service',type:'规则执行',name:'ActPlane',meta:'支持检查与规则加载',x:50,y:278},{id:'kernel',kind:'service',type:'OS 拦截层',name:'Linux / BPF-LSM',meta:'实际拦截需独立验收',x:50,y:386}];
    const edges=[['api','pi','候选分析'],['api','broker','可信控制'],['api','dsh-service','执行协调'],['broker','actplane','编译 / 加载'],['actplane','kernel','规则实施']];
    return tabs+`<div id="overview-panel" role="tabpanel" aria-labelledby="overview-services">${diagram(nodes,edges,{kind:'services',toolbar:'<span>控制与执行链路</span>',footer:'架构示意；服务连接、规则加载与真实拦截分别核验。'})}</div>`;
  }
  const nodes=[{id:'platform',kind:'service',type:'控制台',name:'AgentScope',meta:'2 个示例会话',x:50,y:18}];
  const edges=[];
  for(const [key,x] of [['coding',25],['research',75]]){
    if(connectionScope!=='all'&&connectionScope!==key)continue;
    const t=taskInfo[key];nodes.push({id:key+'-agent',kind:'agent',type:'Agent 实例',name:t.agent,meta:'示例连接 · 未核验',x,y:125,task:t.root},{id:key+'-session',kind:'session',type:'会话',name:t.name,meta:t.id+' · 策略未加载',x,y:234,task:t.root,open:true},{id:key+'-workspace',kind:'workspace',type:'工作区',name:key==='coding'?'项目工作区':'研究工作区',meta:t.workspace,x,y:343,task:t.root});
    edges.push(['platform',key+'-agent','观测连接'],[key+'-agent',key+'-session','关联会话'],[key+'-session',key+'-workspace','使用工作区']);
  }
  const toolbar=`<div class="row"><label class="sr" for="connection-scope">连接范围</label><select id="connection-scope"><option value="all" ${connectionScope==='all'?'selected':''}>全部连接</option><option value="coding" ${connectionScope==='coding'?'selected':''}>编码任务</option><option value="research" ${connectionScope==='research'?'selected':''}>研究任务</option></select><span class="muted">${connectionScope==='all'?'2 个会话':'1 个会话'}</span></div>`;
  return tabs+`<div id="overview-panel" role="tabpanel" aria-labelledby="overview-tasks">${diagram(nodes,edges,{toolbar,footer:'示例连接 · 选择会话进入进程树；连接状态与安全生效分别显示。'})}</div>`;
}
function renderSessionList(){
  return `<div class="panel"><div class="table-wrap"><table class="records task-table" aria-label="会话列表"><thead><tr><th>会话</th><th>Agent</th><th>工作区</th><th>安全状态</th><th></th></tr></thead><tbody>${Object.values(taskInfo).map(t=>`<tr><td data-label="会话"><strong>${t.name}</strong><small>${t.id}</small></td><td data-label="Agent">${t.agent}</td><td data-label="工作区"><code>${t.workspace}</code></td><td data-label="安全状态"><span class="badge">样例 · 未加载</span></td><td><button class="text-action" data-session="${t.root}">打开</button></td></tr>`).join('')}</tbody></table></div></div>`;
}
function renderRules(){
  const rules=selectedRules().filter(r=>(sessionFilter==='all'||(sessionFilter==='inherited')===r.inherited)&&`${r.name} ${r.target}`.toLowerCase().includes(sessionSearch.toLowerCase()));
  return `<div class="toolbar"><label class="sr" for="session-search">搜索会话规则</label><input id="session-search" type="search" placeholder="搜索规则或文件路径" value="${esc(sessionSearch)}"><label class="sr" for="session-source">规则来源</label><select id="session-source"><option value="all" ${sessionFilter==='all'?'selected':''}>全部来源</option><option value="inherited" ${sessionFilter==='inherited'?'selected':''}>继承规则</option><option value="local" ${sessionFilter==='local'?'selected':''}>本会话规则</option></select><span class="record-count">${rules.length} 条记录</span></div>`+ruleTable(rules);
}
function renderRelations(){
  const task=currentTask(),coding=domain!=='D-B';let nodes,edges;
  if(relationView==='processes'){
    nodes=coding?[{id:'p210',kind:'process',type:'主 Agent · DSH',name:'编码 Agent',meta:'PID 210 · D-A',x:50,y:25,pid:210,ppid:'未记录',scope:'D-A'},{id:'p211',kind:'process',type:'子进程',name:'shell',meta:'PID 211 · D-A',x:25,y:167,pid:211,ppid:210,scope:'D-A'},{id:'p220',kind:'agent',type:'子 Agent',name:'测试 Agent',meta:'PID 220 · D-A1',x:75,y:167,pid:220,ppid:210,scope:'D-A1'},{id:'p212',kind:'process',type:'子进程',name:'pytest',meta:'PID 212 · D-A',x:25,y:310,pid:212,ppid:211,scope:'D-A'}]:[{id:'p310',kind:'agent',type:'研究 Agent · DSH',name:'研究 Agent',meta:'PID 310 · D-B',x:50,y:25,pid:310,ppid:'未记录',scope:'D-B'}];
    edges=coding?[['p210','p211','启动'],['p210','p220','委派 / 启动'],['p211','p212','启动']]:[];
  }else{
    nodes=[{id:'d0',kind:'domain',type:'平台规则来源',name:'平台底线 D0',meta:'v0.1 · 3 条继承规则',x:50,y:25,scope:'D0',count:3},{id:'task-domain',kind:'domain',type:'任务域',name:coding?'编码任务 D-A':'研究任务 D-B',meta:coding?'新增 3 条 · 继承 3 条':'新增 2 条 · 继承 3 条',x:50,y:167,scope:task.root,count:coding?6:5}];
    edges=[['d0','task-domain','继承平台底线']];
    if(coding){nodes.push({id:'child-domain',kind:'domain',type:'子 Agent 域',name:'测试子域 D-A1',meta:'新增 1 条 · 继承 6 条',x:50,y:310,scope:'D-A1',count:7});edges.push(['task-domain','child-domain','继承任务约束']);}
  }
  nodes.forEach(n=>n.selected=n.scope===domain);
  const toolbar=`<div class="seg" role="group" aria-label="运行关系类型"><button data-relation="processes" aria-pressed="${relationView==='processes'}" class="${relationView==='processes'?'on':''}">执行进程</button><button data-relation="domains" aria-pressed="${relationView==='domains'}" class="${relationView==='domains'?'on':''}">策略域</button></div><span class="muted">${task.id} · 当前查看 ${domain}</span>`;
  return diagram(nodes,edges,{kind:relationView,toolbar,footer:relationView==='processes'?'PID 与父子关系均为样例；普通子进程延续所属域。':'继承模型示意，未证明运行时已创建或加载这些域。'});
}
function renderFiles(){
  const rows=domain==='D-B'?[['研究工作区','/workspace/research','待场景确认','P13']]:[['秘密配置','/workspace/.env','平台继承规则','P01'],['任务工作区','/workspace/**','任务写入范围','P06'],['测试目录','/workspace/tests/**','子域进一步收紧','C01']];
  return `<div class="panel"><div class="table-wrap"><table class="records" aria-label="工作区与约束"><thead><tr><th>资源</th><th>路径</th><th>配置来源</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td data-label="资源"><strong>${r[0]}</strong></td><td data-label="路径"><code>${r[1]}</code></td><td data-label="配置来源">${r[2]}</td><td><button class="text-action" data-file-rule="${r[3]}">${r[3]==='P13'?'查看网络规则':'查看规则'}</button></td></tr>`).join('')}</tbody></table></div></div><p class="list-subtle" style="margin-top:12px">仅展示示例资源与规则关联，未读取真实文件或核验访问权限。</p>`;
}
function renderVersions(){
  const rows=[['baseline','平台底线','v0.1','会话创建时的继承快照',3],['task','任务规则','任务草案',domain==='D-B'?'研究任务':'编码任务',domain==='D-B'?2:3],...(domain==='D-A1'?[['child','子域规则','子域草案','测试子 Agent',1]]:[])];
  return `<div class="panel"><div class="table-wrap"><table class="records" aria-label="策略版本与来源"><thead><tr><th>来源</th><th>版本</th><th>适用范围</th><th>状态</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td data-label="来源"><strong>${r[1]}</strong><small>${r[4]} 条规则</small></td><td data-label="版本">${r[2]}</td><td data-label="范围">${r[3]}</td><td data-label="状态"><span class="badge">未加载</span></td><td><button class="text-action" data-version="${r[0]}">查看</button></td></tr>`).join('')}</tbody></table></div></div>`;
}
function renderSessions(){
  if(!sessionOpen)return renderSessionList();
  const tabs=tabBar('session',[['permissions','安全规则'],['relations','运行关系'],['files','工作区'],['events','执行记录'],['versions','策略版本']],tab);
  const body=tab==='permissions'?renderRules():tab==='relations'?renderRelations():tab==='files'?renderFiles():tab==='versions'?renderVersions():`<div class="empty-state"><strong>尚无实测执行记录</strong><p>原型未连接 Agent 或内核观测。实际接入后，在这里关联工具调用、OS 拦截与反馈送达。</p><button data-view="session" data-value="relations">查看运行关系</button></div>`;
  return tabs+`<div id="session-panel" role="tabpanel" aria-labelledby="session-${tab}">${body}</div>`;
}
function renderApprovals(){
  const show=approvalScope!=='S-RESEARCH';
  return `<div class="toolbar"><label class="sr" for="approval-scope">审批会话范围</label><select id="approval-scope"><option value="all" ${approvalScope==='all'?'selected':''}>全部会话</option><option value="S-DEMO" ${approvalScope==='S-DEMO'?'selected':''}>登录表单修复</option><option value="S-RESEARCH" ${approvalScope==='S-RESEARCH'?'selected':''}>研究任务 B</option></select><span class="record-count">${show?1:0} 条记录</span></div>${show?`<div class="panel"><div class="table-wrap"><table class="records approval-table" aria-label="变更审批"><thead><tr><th>变更</th><th>会话 / 目标域</th><th>范围变化</th><th>状态</th><th></th></tr></thead><tbody><tr><td data-label="变更"><strong>测试子 Agent 写入范围</strong><small>场景 Agent 提议</small></td><td data-label="会话">登录表单修复<small>S-DEMO · D-A1</small></td><td data-label="范围"><code>/workspace/**</code><code>→ /workspace/tests/**</code></td><td data-label="状态"><span class="badge ${changeState==='pending'?'amber':''}">${changeState==='pending'?'待处理':changeState==='draft'?'草案 · 未加载':'已拒绝'}</span></td><td><button class="text-action" data-inspect="change">查看</button></td></tr></tbody></table></div></div>`:'<div class="empty-state"><strong>这个会话没有变更申请</strong></div>'}`;
}
function renderLibrary(){
  const rows=templates.filter(r=>(libraryCategory==='all'||r.category===libraryCategory)&&`${r.name} ${r.origin}`.toLowerCase().includes(librarySearch.toLowerCase()));
  return `<div class="toolbar"><label class="sr" for="library-search">搜索策略模板</label><input id="library-search" type="search" placeholder="搜索策略模板或研究来源" value="${esc(librarySearch)}"><label class="sr" for="library-category">模板类别</label><select id="library-category"><option value="all">全部类别</option>${[...new Set(templates.map(t=>t.category))].map(c=>`<option ${libraryCategory===c?'selected':''}>${esc(c)}</option>`).join('')}</select><span class="record-count">${rows.length} 个模板</span></div><div class="panel"><div class="table-wrap"><table class="records template-list" aria-label="策略模板库"><thead><tr><th>模板</th><th>类别</th><th>来源</th><th>底线选用</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td data-label="模板"><strong>${r.id} · ${esc(r.name)}</strong></td><td data-label="类别">${esc(r.category)}</td><td data-label="来源">${esc(r.origin)}</td><td data-label="底线选用"><span class="badge ${baselineDraft[r.id].enabled?'blue':''}">${baselineDraft[r.id].enabled?'已选用':'未选用'}</span></td><td><button class="text-action" data-template="${r.id}">查看模板</button></td></tr>`).join('')}</tbody></table></div>${rows.length?'':'<div class="empty">没有匹配的模板</div>'}</div>`;
}
function renderSystem(){
  const tabs=tabBar('system',[['baseline','安全底线'],['capabilities','服务与能力']],systemView);
  const rows=[['控制 API','页面 / 接口连接','未连接'],['DSH','当前实例与会话绑定','未观测'],['Broker','可信控制通道','未观测'],['ActPlane','编译与能力报告','未检查当前会话'],['BPF-LSM','真实加载与拦截','未验证']];
  const body=systemView==='baseline'?renderPlatform():`<div class="panel"><div class="table-wrap"><table class="records service-table" aria-label="服务与能力状态"><thead><tr><th>组件</th><th>核验内容</th><th>当前状态</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td data-label="组件"><strong>${r[0]}</strong></td><td data-label="核验内容">${r[1]}</td><td data-label="状态"><span class="badge">${r[2]}</span></td><td><button class="text-action" data-service-map>查看链路</button></td></tr>`).join('')}</tbody></table></div></div>`;
  return tabs+`<div id="system-panel" role="tabpanel" aria-labelledby="system-${systemView}">${body}</div>`;
}
function render(){
  graphResize.disconnect();graphNodes=new Map();let context='',actions='';
  if(page==='overview')context='<strong>演示工作区</strong><small>连接关系预览</small>';
  if(page==='sessions'){
    if(sessionOpen){context=`<button class="back-button" data-all-sessions aria-label="返回会话列表">←</button><strong>${currentTask().name}</strong><small>${currentTask().id}</small>${domainOptions()}`;actions=`${domain!=='D-B'?`<button data-session-approvals>${changeState==='pending'?'待处理 · 1':'变更记录'}</button>`:''}<button data-inspect="check">检查安全配置</button>`;}
    else context='<strong>2 个会话</strong><small>示例任务</small>';
  }
  if(page==='approvals')context=`<strong>${changeState==='pending'?'1 项待处理':'暂无待处理项'}</strong><small>统一变更记录</small>`;
  if(page==='library')context='<strong>15 个策略模板</strong><small>研究来源与复用</small>';
  if(page==='system'){context=systemView==='baseline'?`<strong>基线 v0.${baselineRevision}</strong><span class="muted">草案 · 新建会话</span>`:'<strong>执行环境</strong><small>证据与能力</small>';if(systemView==='baseline')actions='<button class="primary" data-inspect="draft">查看基线草案</button>';}
  document.getElementById('context').innerHTML=context;document.getElementById('page-actions').innerHTML=actions;
  document.getElementById('content').innerHTML=({overview:renderOverview,sessions:renderSessions,approvals:renderApprovals,library:renderLibrary,system:renderSystem})[page]();
  document.querySelectorAll('[data-page]').forEach(n=>{n.classList.toggle('on',n.dataset.page===page);n.setAttribute('aria-current',n.dataset.page===page?'page':'false');});
  document.querySelector('[data-count="approvals"]').textContent=changeState==='pending'?'1':'';
  const canvas=document.querySelector('.diagram-canvas');if(canvas){graphResize.observe(canvas);requestAnimationFrame(drawEdges);}
}
function showDetails(title,body,footer,opener,drawer=false){lastOpener=opener;const d=document.getElementById('inspector');d.className=drawer?'side-drawer':'';d.innerHTML=`<div class="dialog-head"><h2 id="inspector-title">${esc(title)}</h2><button data-close="inspector" aria-label="关闭详情">×</button></div><div class="dialog-body">${body}<div class="dialog-footer">${footer||'<button data-close="inspector">关闭</button>'}</div></div>`;d.showModal();}
function inspectNode(id,opener){
  const n=graphNodes.get(id);if(!n)return;if(n.open){openSession(n.task,'relations');render();return;}
  const ruleScope=n.scope==='D0'?currentTask().root:n.scope;
  const body=`<dl class="kv"><dt>类型</dt><dd>${esc(n.type)}</dd>${n.pid?`<dt>PID / 父 PID</dt><dd>${n.pid} / ${n.ppid}</dd>`:''}${n.scope?`<dt>策略域</dt><dd>${n.scope}</dd>`:''}<dt>关联信息</dt><dd>${esc(n.meta)}</dd><dt>连接观测</dt><dd>样例 · 未核验</dd><dt>策略生效</dt><dd>未加载 · 未验证</dd></dl>`;
  showDetails(n.name,body,n.scope?`<button class="primary" data-node-rules="${ruleScope}" ${n.scope==='D0'?'data-only-inherited':''}>查看约束</button>`:n.task?`<button class="primary" data-node-session="${n.task}">打开会话</button>`:'<button data-close="inspector">关闭</button>',opener,true);
}
function inspectTemplate(id,opener){const r=byId[id];showDetails(r.name,`<dl class="kv"><dt>来源</dt><dd>${esc(r.origin)}</dd><dt>保护对象</dt><dd><code>${esc(r.target)}</code></dd><dt>默认处置</dt><dd>${esc(actionName[r.effect])}</dd><dt>反馈原因</dt><dd>${esc(r.reason)}</dd></dl><details><summary>能力与研究依据</summary><p style="margin-top:12px">${esc(capability(r))}。${esc(r.limitations)}</p>${evidenceHtml(r)}</details>`,`<button class="primary" data-use-template="${id}">到平台底线配置</button>`,opener);}
function inspectVersion(id,opener){const rules=selectedRules().filter(r=>id==='baseline'?r.sourceLabel==='平台底线':id==='child'?r.id==='C01':r.sourceLabel!=='平台底线'&&r.id!=='C01');showDetails(id==='baseline'?'平台继承快照':id==='child'?'子域规则草案':'任务规则草案',`<dl class="kv"><dt>会话</dt><dd>${currentTask().id}</dd><dt>来源</dt><dd>${id==='baseline'?'基线 v0.1 · 创建时冻结':'当前任务草案'}</dd><dt>规则数</dt><dd>${rules.length}</dd><dt>加载状态</dt><dd>未加载</dd></dl><details><summary>规则记录</summary><ul>${rules.map(r=>`<li>${esc(r.name)}</li>`).join('')}</ul></details>`,null,opener);}
document.addEventListener('click',e=>{
  const n=e.target.closest('button');if(!n)return;
  if(n.dataset.page){page=n.dataset.page;render();}
  else if(n.dataset.view)setView(n.dataset.view,n.dataset.value);
  else if(n.dataset.session){openSession(n.dataset.session);render();}
  else if(n.hasAttribute('data-all-sessions')){sessionOpen=false;render();}
  else if(n.dataset.relation){relationView=n.dataset.relation;render();}
  else if(n.hasAttribute('data-session-approvals')){approvalScope=currentTask().id;page='approvals';render();}
  else if(n.dataset.node)inspectNode(n.dataset.node,n);
  else if(n.dataset.nodeRules){closeDialog('inspector');setDomain(n.dataset.nodeRules);tab='permissions';if(n.hasAttribute('data-only-inherited'))sessionFilter='inherited';render();}
  else if(n.dataset.nodeSession){closeDialog('inspector');openSession(n.dataset.nodeSession,'relations');render();}
  else if(n.dataset.template)inspectTemplate(n.dataset.template,n);
  else if(n.dataset.useTemplate){closeDialog('inspector');page='system';systemView='baseline';category='all';search='';render();openEditor(n.dataset.useTemplate,'platform',document.querySelector(`[data-edit="${n.dataset.useTemplate}"]`));}
  else if(n.dataset.version)inspectVersion(n.dataset.version,n);
  else if(n.hasAttribute('data-service-map')){page='overview';overviewView='services';render();}
  else if(n.dataset.fileRule){if(n.dataset.fileRule==='C01')setDomain('D-A1');tab='permissions';sessionSearch=(byId[n.dataset.fileRule]||{}).name||'';render();}
  else if(n.dataset.edit){document.getElementById('inspector').className='';openEditor(n.dataset.edit,n.dataset.context,n);}
  else if(n.dataset.close)closeDialog(n.dataset.close);
  else if(n.dataset.inspect){document.getElementById('inspector').className='';inspect(n.dataset.inspect,n);}
  else if(n.hasAttribute('data-default-reason')){document.getElementById('reason').value=byId[editContext.id].reason;document.getElementById('dsl-preview').textContent=preview(editorValue());}
  else if(n.dataset.change){changeState=n.dataset.change;document.getElementById('inspector').close();render();toast(changeState==='draft'?'建议已存为待审草案；尚未加载。':'已拒绝这条示例建议。');}
});
document.addEventListener('change',e=>{
  if(e.target.id==='domain'){setDomain(e.target.value);render();}
  else if(e.target.id==='category'){category=e.target.value;render();}
  else if(e.target.id==='session-source'){sessionFilter=e.target.value;render();}
  else if(e.target.id==='connection-scope'){connectionScope=e.target.value;render();}
  else if(e.target.id==='approval-scope'){approvalScope=e.target.value;render();}
  else if(e.target.id==='library-category'){libraryCategory=e.target.value;render();}
});
document.addEventListener('input',e=>{
  if(['search','session-search','library-search'].includes(e.target.id)){const id=e.target.id,value=e.target.value;if(id==='search')search=value;else if(id==='session-search')sessionSearch=value;else librarySearch=value;render();document.getElementById(id).focus();}
  else if(e.target.closest('#rule-form')&&!editContext.locked)document.getElementById('dsl-preview').textContent=preview(editorValue());
});
document.addEventListener('keydown',e=>{
  if(e.target.getAttribute('role')!=='tab'||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();
  const tabs=[...e.target.closest('[role="tablist"]').querySelectorAll('[role="tab"]')],index=tabs.indexOf(e.target),next=e.key==='Home'?tabs[0]:e.key==='End'?tabs.at(-1):tabs[(index+(e.key==='ArrowRight'?1:tabs.length-1))%tabs.length];
  setView(next.dataset.view,next.dataset.value);document.getElementById(next.id).focus();
});
