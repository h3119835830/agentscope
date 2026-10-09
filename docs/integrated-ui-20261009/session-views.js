// Opens native Agent pages only. Homepage bindings belong to instances, not logical sessions.
let relationFormat='graph',sessionScope='all',inspectedNode=null;
const pendingHomeOpens=new Set();
let agentHomeAdapter=null;
function agentHomeButton(id,{primary=false}={}){
  const bound=!!agentHomeRecords[sessionsById[id].instanceId].homeRef&&!!agentHomeAdapter;
  return `<button ${primary?'class="primary"':''} data-open-native="${id}" ${!bound||pendingHomeOpens.has(sessionsById[id].instanceId)?'disabled':''} title="${bound?'在新标签中打开对应 Agent 实例首页':'样例实例尚未绑定真实 Agent 首页'}">打开 Agent 首页 ↗</button>`;
}
async function openAgentHome(id){
  const session=sessionsById[id],ref=session&&agentHomeRecords[session.instanceId].homeRef;
  if(!ref||!agentHomeAdapter){toast('尚未绑定真实 Agent 实例首页；没有打开或启动执行端。');return;}
  const launcher=agentHomeAdapter.launcher;
  if(pendingHomeOpens.has(sessionsById[id].instanceId))return;
  pendingHomeOpens.add(session.instanceId);
  try{await launcher.open(ref);}catch(error){toast(error.message);}
  finally{pendingHomeOpens.delete(session.instanceId);}
}
function relationRecords(nodes,edges){
  return `<div class="table-wrap"><table class="records relation-table" aria-label="运行关系记录"><thead><tr><th>对象 / 身份</th><th>关联会话</th><th>关系</th><th>策略</th><th></th></tr></thead><tbody>${nodes.map(n=>{
    const parent=edges.find(e=>e[1]===n.id),parentNode=parent&&nodes.find(p=>p.id===parent[0]);
    const owner=n.sessionIds.length===1?sessionsById[n.sessionIds[0]]:null;
    const count=n.scope==='D0'?3:owner?policyRulesForScope(owner.scope).length:null;
    return `<tr data-record-node="${n.id}"><td data-label="对象"><strong>${esc(n.name)}</strong><small>${esc(n.identity)}</small></td><td data-label="关联会话">${n.sessionIds.length?n.sessionIds.map(id=>`<span>${esc(sessionsById[id].name)}</span><code>${id}</code>`).join(''):'平台规则来源'}</td><td data-label="关系">${parent?esc(parentNode.name)+'<small>'+esc(parent[2])+'</small>':'—'}</td><td data-label="策略">${count===null?'按关联会话查看':count+' 条'}<small>绑定未验证</small></td><td><button class="text-action" data-node="${n.id}">查看</button></td></tr>`;
  }).join('')}</tbody></table></div>`;
}
function nodePolicies(n,owner){
  const rules=n.scope==='D0'?policyRulesForScope(currentTask().scope).filter(r=>r.sourceLabel==='平台底线'):owner?policyRulesForScope(owner.scope):[];
  return `<p class="node-policy-summary">${rules.length} 条${n.kind==='process'?'关联会话策略':'配置策略'}<span class="badge">未加载 · 绑定未验证</span></p><div class="node-policies" aria-label="节点关联策略">${rules.map(r=>`<div class="node-policy" data-node-policy="${r.id}"><div><strong>${esc(r.name)}</strong><code>${esc(r.target)}</code></div><div><span>${r.kind==='semantic'?'内容检查 / 提醒':esc(actionName[r.effect])}</span><small>${['P06','C01'].includes(r.id)?'范围外写入':opName[r.operation]} · ${esc(r.sourceLabel)}${r.inherited?' · 继承只读':''}</small></div></div>`).join('')}</div>`;
}
function nodeMetadata(n,owner){
  if(!owner)return '<dl class="kv"><dt>配置来源</dt><dd>平台安全底线 D0</dd><dt>版本</dt><dd>v0.1 · 会话继承快照</dd><dt>执行状态</dt><dd>未加载 · 未验证</dd></dl>';
  const runtime=sessionRuntime[owner.id];
  return `<dl class="kv" aria-label="会话元数据"><dt>Agent 名称</dt><dd>${esc(owner.agent)}</dd><dt>会话 ID</dt><dd><code>${owner.id}</code></dd><dt>会话名称</dt><dd>${esc(owner.name)}</dd><dt>Agent 实例</dt><dd>${owner.instanceId}</dd><dt>Agent 首页</dt><dd>${agentHomeRecords[owner.instanceId].homeRef?'已绑定实例入口':'样例 · 尚未绑定真实实例'}</dd><dt>父会话</dt><dd>${owner.parentId||'—'}</dd><dt>工作区</dt><dd><code>${esc(owner.workspace)}</code></dd><dt>最近活动</dt><dd>${owner.lastActivity}</dd><dt>会话活动</dt><dd>${sessionStateText(owner.id)}</dd><dt>连接状态</dt><dd>${runtime.connection==='connected'?'已连接（样例）':'已断开（样例）'}</dd><dt>配置目标域</dt><dd>${owner.scope}</dd></dl>`;
}
function renderNodeInspector(opener){
  const {node:n,ownerId,pane}=inspectedNode,owner=sessionsById[ownerId];
  if(!inspectedNode.opener)inspectedNode.opener=opener||lastOpener;
  const chooser=n.sessionIds.length>1?`<label class="node-owner">关联会话<select id="node-owner" aria-label="节点关联会话">${n.sessionIds.map(id=>`<option value="${id}" ${ownerId===id?'selected':''}>${esc(sessionsById[id].name)} · ${id}</option>`).join('')}</select></label>`:'';
  const tabs=`<div class="tabs node-tabs" role="tablist" aria-label="节点详情"><button role="tab" id="node-policies" aria-controls="node-panel" aria-selected="${pane==='policies'}" tabindex="${pane==='policies'?0:-1}" class="${pane==='policies'?'on':''}" data-inspector-pane="policies">关联策略</button><button role="tab" id="node-metadata" aria-controls="node-panel" aria-selected="${pane==='metadata'}" tabindex="${pane==='metadata'?0:-1}" class="${pane==='metadata'?'on':''}" data-inspector-pane="metadata">会话信息</button></div>`;
  const technical=`<details><summary>运行与绑定说明</summary><dl class="kv"><dt>对象类型</dt><dd>${esc(n.type)}</dd>${n.pid?`<dt>PID / 父 PID</dt><dd>${n.pid} / ${n.ppid}（样例）</dd>`:''}<dt>OS 绑定</dt><dd>未核验</dd></dl>${n.note?`<p class="list-subtle">${esc(n.note)}</p>`:''}</details>`;
  const footer=`${owner?`<button data-node-rules="${owner.scope}">查看全部策略</button>${agentHomeButton(owner.id,{primary:true})}`:'<button data-node-baseline>查看平台底线</button>'}`;
  showDetails(n.name,chooser+tabs+`<div id="node-panel" role="tabpanel" aria-labelledby="node-${pane}">${pane==='policies'?nodePolicies(n,owner):nodeMetadata(n,owner)}</div>`+technical,footer,inspectedNode.opener,true);
  document.getElementById('inspector').classList.add('node-drawer');
}
