// UI sample data only. No API, process discovery, policy load, or authorization.
let overviewView='tasks',connectionScope='all',sessionOpen=false,relationView='agents',systemView='baseline';
let approvalScope='all',librarySearch='',libraryCategory='all',graphNodes=new Map();
const currentTask=()=>taskInfo[domain==='D-B'?'research':'coding'];
function setDomain(value){domain=value;taskDraft=taskDrafts[value==='D-B'?'research':'coding'];sessionFilter='all';sessionSearch='';}
function openSession(value,view='permissions'){setDomain(value);page='sessions';sessionOpen=true;tab=view;}
function tabBar(group,items,value){return `<div class="tabs section-tabs" role="tablist" aria-label="${({overview:'总览视图',session:'会话视图',system:'系统设置'})[group]}">${items.map(([key,name])=>`<button role="tab" id="${group}-${key}" aria-controls="${group}-panel" aria-selected="${value===key}" tabindex="${value===key?'0':'-1'}" data-view="${group}" data-value="${key}" class="${value===key?'on':''}">${name}</button>`).join('')}</div>`;}
function setView(group,value){if(group==='overview')overviewView=value;else if(group==='session')tab=value;else systemView=value;render();}
function domainOptions(){return `<label class="sr" for="domain">查看策略域</label><select id="domain" aria-label="查看策略域"><option value="D-A" ${domain==='D-A'?'selected':''}>主 Agent / D-A</option><option value="D-A1" ${domain==='D-A1'?'selected':''}>测试子 Agent / D-A1</option><option value="D-B" ${domain==='D-B'?'selected':''}>研究 Agent / D-B</option></select>`;}
function diagram(nodes,edges){
  return `<div class="diagram-scroll" tabindex="0" aria-label="可滚动关系图"><div class="diagram-canvas"><svg class="diagram-lines" aria-hidden="true"><defs><marker id="link-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="#9aaec3"/></marker></defs>${edges.map(e=>`<g data-edge-from="${e[0]}" data-edge-to="${e[1]}" data-edge-label="${esc(e[2])}"><path fill="none" stroke="#9aaec3" stroke-width="1.3" marker-end="url(#link-arrow)"/><text text-anchor="middle"></text></g>`).join('')}</svg>${nodes.map(n=>`<button class="graph-node ${n.kind} ${n.selected?'selected':''}" data-node="${n.id}" style="left:${n.x}%;top:${n.y}px" aria-label="查看 ${esc(n.name)}"><span class="node-kind">${esc(n.type)}<span aria-hidden="true">↗</span></span><strong>${esc(n.name)}</strong><span class="node-meta">${esc(n.meta)}</span></button>`).join('')}</div></div>`;
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
  const tabs=tabBar('overview',[['tasks','当前连接'],['services','服务职责']],overviewView);
  if(overviewView==='services'){
    const rows=[['AgentScope API','控制入口','协调会话与安全配置'],['Pi','策略分析','生成候选，交给可信控制面审核'],['Broker','可信控制','处理受信的批准、加载与执行协调'],['DSH','Agent 宿主','管理会话、Agent 对象与工具调用'],['ActPlane','策略实施','编译、加载与能力检查'],['Linux / BPF-LSM','OS 拦截','真实拦截效果需独立验收']];
    return tabs+`<div id="overview-panel" role="tabpanel" aria-labelledby="overview-services"><div class="panel"><div class="table-wrap"><table class="records" aria-label="服务职责列表"><thead><tr><th>组件</th><th>职责</th><th>说明</th><th>观测状态</th></tr></thead><tbody>${rows.map(r=>`<tr><td data-label="组件"><strong>${r[0]}</strong></td><td data-label="职责">${r[1]}</td><td data-label="说明">${r[2]}</td><td data-label="观测状态"><span class="badge">未观测</span></td></tr>`).join('')}</tbody></table></div></div></div>`;
  }

  const rows=Object.entries(taskInfo).filter(([key])=>connectionScope==='all'||connectionScope===key);
  const toolbar=`<div class="toolbar"><label class="sr" for="connection-scope">连接范围</label><select id="connection-scope"><option value="all" ${connectionScope==='all'?'selected':''}>全部连接</option><option value="coding" ${connectionScope==='coding'?'selected':''}>编码任务</option><option value="research" ${connectionScope==='research'?'selected':''}>研究任务</option></select><span class="record-count">${rows.length} 条记录</span></div>`;
  return tabs+`<div id="overview-panel" role="tabpanel" aria-labelledby="overview-tasks">${toolbar}<div class="panel"><div class="table-wrap"><table class="records connection-table" aria-label="当前连接列表"><thead><tr><th>执行端实例</th><th>类型</th><th>关联会话</th><th>连接观测</th><th></th></tr></thead><tbody>${rows.map(([key,t])=>`<tr><td data-label="执行端实例"><strong>${t.instanceId}</strong></td><td data-label="类型">DSH Web</td><td data-label="关联会话">${sessionRecords.filter(s=>s.instanceId===t.instanceId).length} 个</td><td data-label="连接观测"><span class="badge">样例 · 未核验</span></td><td><button class="text-action" data-session-filter="${key}">查看会话</button></td></tr>`).join('')}</tbody></table></div></div></div>`;
}
function renderSessionList(){
  const rows=sessionRecords.filter(s=>sessionScope==='all'||s.taskKey===sessionScope);
  return `<div class="toolbar"><label class="sr" for="session-scope">会话范围</label><select id="session-scope"><option value="all" ${sessionScope==='all'?'selected':''}>全部会话</option><option value="coding" ${sessionScope==='coding'?'selected':''}>编码任务</option><option value="research" ${sessionScope==='research'?'selected':''}>研究任务</option></select><span class="record-count">${rows.length} 条记录</span></div><div class="panel"><div class="table-wrap"><table class="records task-table" aria-label="会话列表"><thead><tr><th>会话名称 / ID</th><th>Agent</th><th>会话活动</th><th>安全状态</th><th></th></tr></thead><tbody>${rows.map(t=>`<tr data-session-record="${t.id}"><td data-label="会话"><strong>${esc(t.name)}</strong><code>${t.id}</code>${t.parentId?'<small>子会话</small>':''}</td><td data-label="Agent">${esc(t.agent)}<small>${t.instanceId}</small></td><td data-label="会话活动"><span class="badge">${sessionStateText(t.id)}</span></td><td data-label="安全状态"><span class="badge">未加载</span></td><td><div class="record-actions"><button class="text-action" data-session="${t.scope}">查看安全</button>${sessionOpenButton(t.id)}</div></td></tr>`).join('')}</tbody></table></div></div>`;
}
function renderRules(){
  const rules=selectedRules().filter(r=>(sessionFilter==='all'||(sessionFilter==='inherited')===r.inherited)&&`${r.name} ${r.target}`.toLowerCase().includes(sessionSearch.toLowerCase()));
  return `<div class="toolbar"><label class="sr" for="session-search">搜索会话规则</label><input id="session-search" type="search" placeholder="搜索规则或文件路径" value="${esc(sessionSearch)}"><label class="sr" for="session-source">规则来源</label><select id="session-source"><option value="all" ${sessionFilter==='all'?'selected':''}>全部来源</option><option value="inherited" ${sessionFilter==='inherited'?'selected':''}>继承规则</option><option value="local" ${sessionFilter==='local'?'selected':''}>本会话规则</option></select><span class="record-count">${rules.length} 条记录</span></div>`+ruleTable(rules);
}
function renderRelations(){
  const {nodes,edges}=relationModel(relationView,currentTask().taskKey);
  graphNodes=new Map(nodes.map(n=>[n.id,n]));
  const types=`<div class="seg" role="group" aria-label="运行关系类型">${[['agents','Agent 关系'],['processes','OS 进程'],['domains','策略域']].map(([key,label])=>`<button data-relation="${key}" aria-pressed="${relationView===key}" class="${relationView===key?'on':''}">${label}</button>`).join('')}</div>`;
  const format=`<div class="seg" role="group" aria-label="展示形式"><button data-relation-format="graph" aria-pressed="${relationFormat==='graph'}" class="${relationFormat==='graph'?'on':''}">关系图</button><button data-relation-format="records" aria-pressed="${relationFormat==='records'}" class="${relationFormat==='records'?'on':''}">记录表</button></div>`;
  const hint=relationView==='agents'?'Agent 委派与工具调用；点击对象查看策略和会话信息。':relationView==='processes'?'PID 与关联均为样例；共享宿主按关联会话查看配置。':'配置目标与继承模型；实际 OS 绑定未核验。';
  return `<section class="diagram-panel" aria-label="会话运行关系"><div class="diagram-toolbar">${types}${format}</div>${relationFormat==='graph'?diagram(nodes,edges):relationRecords(nodes,edges)}<div class="diagram-footer"><span>${hint}</span><button class="text-action" data-lifecycle>会话如何运行 ↗</button></div></section>`;
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
  const body=systemView==='baseline'?renderPlatform():`<div class="panel"><div class="table-wrap"><table class="records service-table" aria-label="服务与能力状态"><thead><tr><th>组件</th><th>核验内容</th><th>当前状态</th><th></th></tr></thead><tbody>${rows.map(r=>`<tr><td data-label="组件"><strong>${r[0]}</strong></td><td data-label="核验内容">${r[1]}</td><td data-label="状态"><span class="badge">${r[2]}</span></td><td><button class="text-action" data-service-map>查看职责</button></td></tr>`).join('')}</tbody></table></div></div>`;
  return tabs+`<div id="system-panel" role="tabpanel" aria-labelledby="system-${systemView}">${body}</div>`;
}
function render(){
  graphResize.disconnect();graphNodes=new Map();let context='',actions='';
  if(page==='overview')context='<strong>演示工作区</strong><small>2 个执行端实例</small>';
  if(page==='sessions'){

    if(sessionOpen){const session=currentSession();context=`<button class="back-button" data-all-sessions aria-label="返回会话列表">←</button><strong>${esc(session.name)}</strong><small>${session.id} · ${esc(session.agent)}</small>${domainOptions()}`;actions=`${domain!=='D-B'?`<button data-session-approvals>${changeState==='pending'?'待处理 · 1':'变更记录'}</button>`:''}${sessionOpenButton(session.id)}<button data-inspect="check">检查安全配置</button>`;}
    else context='<strong>会话目录</strong><small>3 个样例会话</small>';
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
function showDetails(title,body,footer,opener,drawer=false){lastOpener=opener;const d=document.getElementById('inspector');d.className=drawer?'side-drawer':'';d.innerHTML=`<div class="dialog-head"><h2 id="inspector-title">${esc(title)}</h2><button data-close="inspector" aria-label="关闭详情">×</button></div><div class="dialog-body">${body}<div class="dialog-footer">${footer||'<button data-close="inspector">关闭</button>'}</div></div>`;if(!d.open)d.showModal();}
function inspectNode(id,opener){
  const n=graphNodes.get(id);if(!n)return;
  const selected=n.sessionIds.includes(currentSession().id)?currentSession().id:n.sessionIds[0];
  inspectedNode={node:n,ownerId:selected,pane:'policies'};renderNodeInspector(opener);
}
function inspectLifecycle(opener){
  showDetails('聊天会话与进程',`<ol class="lifecycle-steps"><li><strong>打开或新建会话</strong><p>DSH Web 宿主创建或恢复 Session，按需取得进程内 Agent 对象。打开页面本身不等于新建一个 OS 进程。</p></li><li><strong>发送消息</strong><p>Agent 开始一轮运行；调用 shell 等工具时，才可能启动工具子进程。</p></li><li><strong>回复完成</strong><p>Agent 回到空闲，宿主服务通常继续运行。下条消息可复用会话；历史仍存在不代表 Agent 对象或工具进程一直存活。</p></li><li><strong>停止或重新打开</strong><p>取消一轮回复、关闭页面、停止宿主是不同动作。宿主退出后，历史会话可以恢复，PID 可能变化。一次性 headless 命令则在本轮完成并保存后退出。</p></li></ol><details><summary>实现依据与安全含义</summary><p>本机 DSH 0.2.0-rc.2：SessionController 查找或恢复 Agent；Agent loop 有 idle 状态；headless 等待 whenIdle 后调用 exit。进程内子 Agent 可以共享宿主 PID。会话隔离需可信的执行身份与工具/进程绑定，不能只靠会话名称或共享 PID。</p><p>以上为代码核对；当前原型未观测真实进程，也未执行聊天生命周期实验。</p></details>`,null,opener);
}
function inspectTemplate(id,opener){const r=byId[id];showDetails(r.name,`<dl class="kv"><dt>来源</dt><dd>${esc(r.origin)}</dd><dt>保护对象</dt><dd><code>${esc(r.target)}</code></dd><dt>默认处置</dt><dd>${esc(actionName[r.effect])}</dd><dt>反馈原因</dt><dd>${esc(r.reason)}</dd></dl><details><summary>能力与研究依据</summary><p style="margin-top:12px">${esc(capability(r))}。${esc(r.limitations)}</p>${evidenceHtml(r)}</details>`,`<button class="primary" data-use-template="${id}">到平台底线配置</button>`,opener);}
function inspectVersion(id,opener){const rules=selectedRules().filter(r=>id==='baseline'?r.sourceLabel==='平台底线':id==='child'?r.id==='C01':r.sourceLabel!=='平台底线'&&r.id!=='C01');showDetails(id==='baseline'?'平台继承快照':id==='child'?'子域规则草案':'任务规则草案',`<dl class="kv"><dt>会话</dt><dd>${currentSession().id}</dd><dt>来源</dt><dd>${id==='baseline'?'基线 v0.1 · 创建时冻结':'当前任务草案'}</dd><dt>规则数</dt><dd>${rules.length}</dd><dt>加载状态</dt><dd>未加载</dd></dl><details><summary>规则记录</summary><ul>${rules.map(r=>`<li>${esc(r.name)}</li>`).join('')}</ul></details>`,null,opener);}
document.addEventListener('click',e=>{
  const n=e.target.closest('button');if(!n)return;
  if(n.dataset.page){page=n.dataset.page;render();}
  else if(n.dataset.view)setView(n.dataset.view,n.dataset.value);
  else if(n.dataset.sessionFilter){sessionScope=n.dataset.sessionFilter;page='sessions';sessionOpen=false;render();}
  else if(n.dataset.openNative)openNativeSession(n.dataset.openNative);
  else if(n.dataset.session){openSession(n.dataset.session,n.dataset.openView||'permissions');render();}
  else if(n.hasAttribute('data-all-sessions')){sessionOpen=false;render();}
  else if(n.dataset.relation){relationView=n.dataset.relation;render();}
  else if(n.dataset.relationFormat){relationFormat=n.dataset.relationFormat;render();}
  else if(n.dataset.inspectorPane){inspectedNode.pane=n.dataset.inspectorPane;renderNodeInspector(n);document.getElementById('node-'+inspectedNode.pane).focus();}
  else if(n.hasAttribute('data-node-baseline')){closeDialog('inspector');page='system';systemView='baseline';render();}
  else if(n.hasAttribute('data-session-approvals')){approvalScope=currentTask().id;page='approvals';render();}
  else if(n.dataset.node)inspectNode(n.dataset.node,n);
  else if(n.hasAttribute('data-lifecycle'))inspectLifecycle(n);
  else if(n.dataset.nodeRules){closeDialog('inspector');openSession(n.dataset.nodeRules);render();}
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
  else if(e.target.id==='node-owner'){inspectedNode.ownerId=e.target.value;renderNodeInspector();}
  else if(e.target.id==='session-scope'){sessionScope=e.target.value;render();}
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
  if(next.dataset.inspectorPane){inspectedNode.pane=next.dataset.inspectorPane;renderNodeInspector();}else setView(next.dataset.view,next.dataset.value);document.getElementById(next.id).focus();
});
