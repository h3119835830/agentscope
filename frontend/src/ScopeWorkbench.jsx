import React, {useEffect, useRef, useState} from 'react';
import {candidateState, connectionEvidence, executionState, kinds, proposalSummary, recordsFor, resources, scopeDiff, stageEvidence, statusNames, writable} from './scopeView.mjs';
import './scope.css';

const initialText={task_grant:'授权修改 backend 和 frontend，保护 tests/config；output 需要单独审批。',
  restrict:'暂时只修改 backend，停止修改 frontend，继续保护 tests/config。',
  expand:'申请 output 写入任务报告，保留已生效的所有仓库限制。',guidance:'请用简洁清楚的文字解释修复结果。'};
const when=t=>t?new Date(t).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}):'—';
const tabsList=[['current','当前权限'],['review','变更审核'],['records','执行记录']];
function Badge({tone='neutral',children}) {return <span className={'scope-badge '+tone}>{children}</span>;}
function Evidence({value}) {return <details className="scope-technical"><summary>技术证据</summary><pre>{JSON.stringify(value,null,2)}</pre></details>;}
function PermissionTable({scope}) {
  return <div className="scope-table-wrap"><table className="scope-permissions"><thead><tr><th>资源</th><th>用途</th><th>权限</th></tr></thead>
    <tbody>{resources.map(([resource,label])=><tr key={resource}><td><svg className="scope-folder" aria-hidden="true" viewBox="0 0 20 20" fill="none"><path d="M2 5h6l2 2h8v9H2V5Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/></svg>{resource}</td><td>{label}</td>
      <td><Badge tone={writable(scope,resource)?'good':'neutral'}>{writable(scope,resource)?resource==='runtime / tmp'?'指定目录可写':'可读写':resource==='tests'||resource==='config'?'只读 · 保护':'只读'}</Badge></td></tr>)}</tbody></table></div>;
}
function Diff({base,next}) {
  if(!next)return <p className="scope-muted">候选分析尚未完成。</p>;
  const diff=scopeDiff(base,next);
  return diff.length?<div className="scope-diff-list">{diff.map(row=><div key={row.resource}><b>{row.resource}</b><span>{row.before}</span><span aria-hidden="true">→</span>
    <Badge tone={row.after==='可读写'?'good':'neutral'}>{row.after}</Badge></div>)}</div>:<p className="scope-muted">文件权限不变。</p>;
}
export default function ScopeWorkbench({api,post,notify}) {
  const [task,setTask]=useState(()=>{const selected=new URLSearchParams(window.location.search).get('task')||'';
    return /^[a-f0-9]{16}$/.test(selected)?selected:localStorage.getItem('scopeDemoTask')||'';});
  const [tasks,setTasks]=useState([]),[data,setData]=useState(null),[tab,setTab]=useState('current');
  const [kind,setKind]=useState('task_grant'),[text,setText]=useState(initialText.task_grant),[busy,setBusy]=useState(false);
  const [reviewed,setReviewed]=useState(false),[category,setCategory]=useState('scope'),[page,setPage]=useState(0);
  const [error,setError]=useState(''),[detail,setDetail]=useState(null);
  const dialog=useRef(null),opener=useRef(null),tabs=useRef([]),idempotence=useRef(null);
  const reload=async(id=task)=>{const list=await api('/api/tasks');setTasks(list.filter(t=>t.repo==='AgentScope/custom-scope-demo'));
    if(id)setData(await api('/api/tasks/'+id+'/scope-manager'));};
  useEffect(()=>{
    let live=true,inFlight=false;setData(null);setError('');setPage(0);
    const fetchData=async()=>{if(inFlight)return;inFlight=true;try{
      const list=await api('/api/tasks');if(live)setTasks(list.filter(t=>t.repo==='AgentScope/custom-scope-demo'));
      if(task){const value=await api('/api/tasks/'+task+'/scope-manager');if(live){setData(value);setError('');}}
    }catch(e){if(live)setError(e.message);}finally{inFlight=false;}};
    fetchData();const timer=setInterval(fetchData,3000);return()=>{live=false;clearInterval(timer);};
  },[task,api]);
  useEffect(()=>{if(detail){if(!dialog.current.open)dialog.current.showModal();dialog.current.querySelector('button')?.focus();}},[detail?.type,!!detail]);
  const choose=id=>{setData(null);setTask(id);setTab('current');setReviewed(false);idempotence.current=null;localStorage.setItem('scopeDemoTask',id);
    const url=new URL(window.location.href);if(id)url.searchParams.set('task',id);else url.searchParams.delete('task');window.history.replaceState(null,'',url.pathname+url.search);};
  const perform=async fn=>{setBusy(true);setError('');try{const result=await fn();await reload(typeof result==='string'?result:task);return true;}
    catch(e){setError(e.message);notify('操作未完成，请查看错误详情。');return false;}finally{setBusy(false);}};
  const open=(value,event)=>{opener.current=event.currentTarget;setDetail(value);};
  const close=()=>{dialog.current.close();setDetail(null);if(opener.current?.isConnected)opener.current.focus();else tabs.current[0]?.focus();};
  const create=()=>perform(async()=>{const value=await post('/api/scope-demo/tasks');choose(value.task_id);return value.task_id;});
  const changeKind=k=>{setKind(k);setText(initialText[k]);idempotence.current=null;};
  const request=(k,event,original)=>{changeKind(k);if(original)setText(original);open({type:'request',title:kinds[k]},event);};
  const assess=async()=>{const ok=await perform(async()=>{if(!idempotence.current)idempotence.current=crypto.randomUUID();
    await post('/api/tasks/'+task+'/scope-manager/changes',{kind,text,request_key:idempotence.current,expected_snapshot:data.session.active_snapshot_id});
    idempotence.current=null;setTab('review');setReviewed(false);});if(ok)close();};
  const review=async(d,decision)=>{const ok=await perform(()=>post('/api/tasks/'+task+'/scope-manager/changes/'+d.id+'/review',
    {decision,expected_proposal_hash:d.proposal_hash,reviewed_by:'工作台研究者'}));
    if(ok){close();notify(decision==='approve'?'应用结果已回查。':'候选已拒绝，用户要求仍然保留。');}};
  const snapshot=data?.current,scope=snapshot?.payload||data?.default_scope;
  const ended=data?.session.phase==='ended',effective=!!data?.effective&&!error,state=data?executionState(data,!!error):null;
  const connection=data?connectionEvidence(data,!!error):null;
  const pending=data?.deltas.filter(d=>d.review_status==='pending')||[],history=data?stageEvidence(data):[];
  const visibleDeltas=data?.deltas.filter(d=>reviewed?d.review_status!=='pending':d.review_status==='pending')||[];
  const records=data?recordsFor(data,category):[],pageCount=Math.max(1,Math.ceil(records.length/8)),safePage=Math.min(page,pageCount-1);
  const detailDelta=detail?.type==='delta'?data?.deltas.find(d=>d.id===detail.id):null,detailState=detailDelta?candidateState(detailDelta,data):null;
  const detailBase=detailDelta?data.snapshots.find(s=>s.id===detailDelta.base_snapshot_id):null,historical=detail?.type==='snapshot'?detail.snapshot:null;
  return <div className="scope-workbench">
    <header className="scope-heading"><div><h1>Agent 动态权限演示</h1><p>从默认只读开始，按任务需要逐步授权。示例：修复文本统计并生成报告。</p>
      {state&&<div className="scope-heading-state" aria-live="polite"><Badge tone={state.tone}>{state.label}</Badge>
        <span>{ended?'临时授权已撤销':effective?'当前有效 v'+snapshot.revision:snapshot?'最近核验 v'+snapshot.revision:'尚未核验'}</span>
        <button className="scope-link" onClick={e=>open({type:'task',title:'任务详情'},e)}>任务详情</button>
        <button className="scope-link" onClick={e=>open({type:'connection',title:'DSH 连接详情'},e)}>DSH 连接详情</button></div>}</div>
      <div className="scope-heading-actions"><select aria-label="选择 Demo 任务" value={task} disabled={busy} onChange={e=>choose(e.target.value)}>
        <option value="">选择任务</option>{tasks.map(t=><option key={t.id} value={t.id}>{when(t.created_at).slice(0,11)} {t.status==='completed'?'已结束':t.status==='prepared'?'待开始':'进行中'} · {t.id.slice(-4)}</option>)}</select>
        <button className="scope-button" disabled={busy} onClick={create}>新建任务</button><button className="scope-icon-button" aria-label="Agent 设置" title="Agent 设置" onClick={e=>open({type:'settings',title:'Agent 设置'},e)}>⚙</button></div>
    </header>
    {error&&<div role="alert" className="scope-notice warn"><span>操作或连接未完成，权限状态需回查。</span><button className="scope-link" onClick={e=>open({type:'error',title:'错误详情',value:error},e)}>查看错误</button></div>}
    {data&&<>
      <nav className="scope-stages" aria-label="权限生命周期">{history.map((s,i)=><button key={s.key} className={s.evidence?'done':'future'} disabled={!s.evidence}
        aria-label={s.title+(s.optional?'，可选分支':'')+(s.evidence?'，查看记录':'，尚未进行')} onClick={e=>open(s.key==='close'?{type:'closure',title:'结束撤销'}:{type:'snapshot',title:s.title,snapshot:s.evidence},e)}>
        <span className="scope-step-number" aria-hidden="true">{s.evidence?'✓':s.optional?'↳':i+1}</span><span><b>{s.title}</b><small>{s.evidence?s.evidence.closed?'已撤销':'v'+s.evidence.revision+' 已核验'+(s.optional?' · 可选':''):s.note}</small></span></button>)}</nav>
      <div role="tablist" aria-label="任务工作台" className="scope-tabs">{tabsList.map(([key,label],i)=><button key={key} ref={el=>tabs.current[i]=el} role="tab" id={'scope-tab-'+key}
        aria-controls={'scope-panel-'+key} aria-selected={tab===key} tabIndex={tab===key?0:-1} onClick={()=>setTab(key)} onKeyDown={e=>{
          if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;setTab(tabsList[n][0]);tabs.current[n].focus();}}}>
        {label}{key==='review'&&pending.length>0&&<span className="scope-count">{pending.length}</span>}</button>)}</div>
      {tab==='current'&&<section role="tabpanel" id="scope-panel-current" aria-labelledby="scope-tab-current" className="scope-pane">
        {!ended&&<div className={'scope-notice '+(state.tone==='warn'?'warn':'')}><div><b>{state.label}</b><p>{state.hint}</p></div>
          {!snapshot?<button className="scope-button primary" disabled={busy||!!error} onClick={()=>perform(()=>post('/api/tasks/'+task+'/scope-manager/cold'))}>{busy?'核验中…':'验证冷启动'}</button>:
          !ended&&data.session.phase==='cold'?<button className="scope-button primary" disabled={busy||!!error} onClick={e=>request('task_grant',e)}>提出任务授权</button>:
          !ended&&<button className="scope-button primary" disabled={busy||!!error} onClick={e=>request('restrict',e)}>调整任务权限</button>}</div>}
        <div className="scope-section-head"><div><h2>{ended?'结束前的权限':effective?'当前有效权限':snapshot?'最近核验的权限':'默认文件权限'}</h2>
          <p>{ended?'历史快照，授权已失效。':effective?'读取、写入与删除的实际允许范围。':snapshot?'执行域尚未确认，以下为历史核验记录。':'仓库只读，运行与临时文件可在指定目录写入。'}</p></div>
          <button className="scope-link" onClick={e=>open({type:'snapshot',title:ended?'结束前的权限':snapshot?'权限详情':'默认权限',snapshot:snapshot||{payload:scope}},e)}>{snapshot?'v'+snapshot.revision+' · 权限详情':'权限详情'}</button></div>
        <PermissionTable scope={scope}/><footer className="scope-pane-footer"><span>写入授权仅限本任务；测试与配置持续保护。</span>
          {!ended&&snapshot&&<button className="scope-link danger" disabled={busy} onClick={e=>open({type:'close',title:'结束任务'},e)}>结束并撤销</button>}</footer>
      </section>}
      {tab==='review'&&<section role="tabpanel" id="scope-panel-review" aria-labelledby="scope-tab-review" className="scope-pane">
        <div className="scope-section-head"><div><h2>{reviewed?'已处理申请':'待处理申请'}</h2><p>审批并核验后，才更新当前权限。</p></div>
          {!ended&&snapshot&&<button className="scope-button primary" disabled={busy||!!error||!!data.session.apply_id} onClick={e=>request(data.session.phase==='cold'?'task_grant':'restrict',e)}>提出新要求</button>}</div>
        <div className="scope-filter" aria-label="申请筛选"><button aria-pressed={!reviewed} onClick={()=>setReviewed(false)}>待处理{pending.length?' '+pending.length:''}</button><button aria-pressed={reviewed} onClick={()=>setReviewed(true)}>已处理</button></div>
        {!visibleDeltas.length&&<div className="scope-empty"><span aria-hidden="true">✓</span><h3>{reviewed?'暂无已处理申请':'没有待处理申请'}</h3><p>{ended?'本次任务的权限申请均已处理。':snapshot?'需要调整权限时，提出新要求。':'先在当前权限页验证冷启动。'}</p>
          {ended&&!reviewed&&data.deltas.length>0&&<button className="scope-link" onClick={()=>setReviewed(true)}>查看已处理申请</button>}</div>}
        <div className="scope-requests">{visibleDeltas.map(d=>{const c=candidateState(d,data),proposal=d.proposal?.proposal,base=data.snapshots.find(s=>s.id===d.base_snapshot_id),diff=scopeDiff(base?.payload,proposal);
          return <article className="scope-request-row" data-delta-id={d.id} key={d.id}><div><h3>{kinds[d.kind]}</h3><p>{proposal?diff.length?diff.map(r=>r.resource+' '+r.before+' → '+r.after).join('；'):'文件权限不变':'正在准备权限候选'}</p></div>
            <Badge tone={c.label==='已核验生效'?'good':c.stale&&d.review_status==='pending'||c.label==='分析失败'?'warn':'neutral'}>{c.label}</Badge>
            <button className="scope-button" aria-label={kinds[d.kind]+'，查看申请'} onClick={e=>open({type:'delta',title:kinds[d.kind],id:d.id},e)}>{c.ready?'审核申请':'查看申请'}</button></article>;})}</div>
      </section>}
      {tab==='records'&&<section role="tabpanel" id="scope-panel-records" aria-labelledby="scope-tab-records" className="scope-pane">
        <div className="scope-section-head"><div><h2>执行记录</h2><p>先看关键变化，点击记录查看证据。</p></div><span className="scope-muted">{records.length} 条{category!=='scope'?' · 最近事件':''}</span></div>
        <div className="scope-filter" aria-label="记录筛选">{[['scope','权限变化'],['agent','Agent 执行'],['kernel','拦截记录']].map(([key,label])=><button key={key} aria-pressed={category===key} onClick={()=>{setCategory(key);setPage(0);}}>{label}</button>)}</div>
        {records.length?<ol className="scope-records">{records.slice(safePage*8,safePage*8+8).map(r=><li key={r.id}><time>{when(r.time)}</time><b>{r.title}</b><Badge tone={r.tone}>{r.result}</Badge>
          <button className="scope-record-open" aria-label={r.title+'，查看详情'} onClick={e=>open(r.snapshot?{type:'snapshot',title:r.title,snapshot:r.snapshot}:{type:'event',title:r.title,value:r.value},e)}>详情<span aria-hidden="true"> ›</span></button></li>)}</ol>:
          <div className="scope-empty"><h3>暂无记录</h3><p>任务执行与权限变化会在这里记录。</p></div>}
        <footer className="scope-pane-footer"><span>{category==='scope'?'核验快照与最近关键事件。':'最近 150 条事件中的当前类别。'}</span>
          {pageCount>1&&<div className="scope-pagination"><button className="scope-button" aria-label="上一页记录" disabled={safePage===0} onClick={()=>setPage(safePage-1)}>‹</button><span>{safePage+1} / {pageCount}</span>
            <button className="scope-button" aria-label="下一页记录" disabled={safePage===pageCount-1} onClick={()=>setPage(safePage+1)}>›</button></div>}</footer>
      </section>}
    </>}
    {!data&&!error&&<section className="scope-pane scope-empty"><h2>{task?'正在读取任务…':'演示任务中的权限变化'}</h2><p>{task?'正在连接本地控制服务。':'新建一个独立文本统计项目，从默认只读开始。'}</p>
      {!task&&<button className="scope-button primary" disabled={busy} onClick={create}>新建任务</button>}</section>}
    <dialog ref={dialog} className="scope-dialog" aria-labelledby="scope-dialog-title" onCancel={()=>{setDetail(null);if(opener.current?.isConnected)opener.current.focus();else tabs.current[0]?.focus();}}>
      <header className="scope-drawer-head"><h2 id="scope-dialog-title">{detail?.title}</h2><button className="scope-icon-button" aria-label="关闭详情" onClick={close}>×</button></header>
      <div className="scope-drawer-body">
        {error&&detail?.type!=='error'&&<div className="scope-notice warn"><div><b>操作未完成，请回查状态。</b><details><summary>错误详情</summary><p className="scope-error-text">{error}</p></details></div></div>}
        {detail?.type==='request'&&<form className="scope-request-form" onSubmit={e=>{e.preventDefault();assess();}}><label>要求类型<select value={kind} onChange={e=>changeKind(e.target.value)}>
          {Object.entries(kinds).filter(([k])=>data.session.phase==='cold'?k==='task_grant':k!=='task_grant').map(([k,label])=><option key={k} value={k}>{label}</option>)}</select></label>
          <label>你的要求<textarea minLength={4} maxLength={2000} required value={text} onChange={e=>{setText(e.target.value);idempotence.current=null;}}/></label>
          <p className="scope-muted">{kind==='restrict'?'收紧要求将在下个工具边界暂停 Agent。':'Pi 生成候选，审核后才会应用权限。'}</p><button className="scope-button primary" disabled={busy||!!data.session.apply_id||ended||!!error}>{busy?'正在提交…':'生成权限候选'}</button></form>}
        {detailDelta&&<><Badge tone={detailState.ready?'warn':'neutral'}>{detailState.label}</Badge><h3>用户要求</h3><p>{detailDelta.input.text}</p><h3>权限变化</h3><Diff base={detailBase?.payload} next={detailDelta.proposal?.proposal}/>
          <p className="scope-muted">tests / config 的保护与平台底线始终保留。</p><h3>候选说明</h3><p>{proposalSummary(detailDelta)}</p>
          {detailDelta.proposal?.proposal?.explanation&&<details className="scope-pi-explanation"><summary>查看 Pi 原始说明</summary><p className="scope-evidence-copy">{detailDelta.proposal.proposal.explanation}</p></details>}
          {['guidance_only','no_change'].includes(detailDelta.proposal?.proposal?.decision)&&<p className="scope-muted">本候选只提供指导或无需变更，不会扩展文件权限。</p>}
          <div className="scope-review-states">{[['review_status','审核'],['compile_status','编译'],['apply_status','加载'],['verify_status','核验']].map(([key,label])=><div key={key}><small>{label}</small><b>{statusNames[detailDelta[key]]||detailDelta[key]}</b></div>)}</div>
          {detailState.job?.error&&<p className="scope-error-text">{detailState.job.error}</p>}{detailState.stale&&detailDelta.review_status==='pending'&&<p className="scope-error-text">输入版本已变化，需要重新分析。当前权限未因此改变。</p>}
          {!ended&&detailDelta.review_status==='pending'&&<div className="scope-drawer-actions">{detailState.ready&&<><button className="scope-button primary" disabled={busy||!!error} onClick={()=>review(detailDelta,'approve')}>{busy?'应用中…':'批准并应用'}</button>
            <button className="scope-button" disabled={busy||!!error} onClick={()=>review(detailDelta,'reject')}>拒绝候选</button></>}<button className="scope-link" disabled={busy}
              onClick={()=>{changeKind(detailDelta.kind);setText(detailDelta.input.text);setDetail({type:'request',title:'澄清并重新分析'});}}>澄清并重新分析</button></div>}
          <Evidence value={{delta:detailDelta,job:detailState.job}}/></>}
        {historical&&<><div className="scope-notice"><div><b>{historical.id===snapshot?.id&&effective?'当前有效权限':historical.revision===undefined?'默认策略，尚未核验':'历史核验快照'}</b>
          <p>{historical.confirmed_at?when(historical.confirmed_at):'冷启动规则'}{ended?'；本次临时授权已撤销。':''}</p></div>{historical.revision!==undefined&&<Badge>v{historical.revision}</Badge>}</div>
          <PermissionTable scope={historical.payload}/><p className="scope-muted">运行资产中的原生插件、凭据与平台底线保持保护。</p>
          {historical.verification&&<p>{historical.verification.probe?.checks?.filter(c=>c.passed).length||0} 项文件探针通过；执行域已核验。</p>}<Evidence value={historical}/></>}
        {detail?.type==='task'&&data&&<><h3>这次任务</h3><p>修复 backend 的文本统计，完善 frontend 的摘要，运行现有测试并将报告写入任务专属 output。</p>
          <dl className="scope-detail-fields"><dt>场景来源</dt><dd>自建 Python 标准库项目</dd><dt>执行 Agent</dt><dd>DSH</dd><dt>策略候选</dt><dd>Pi</dd><dt>权限核验</dt><dd>{snapshot?.verification?.passed&&snapshot?.verification?.root_owned_events?'实际执行域文件探针与内核事件':'尚未取得完整核验证据'}</dd><dt>任务 ID</dt><dd>{task}</dd><dt>当前状态</dt><dd>{state.label}</dd></dl><Evidence value={{task:data.task,session:data.session,execution:data.execution}}/></>}
        {detail?.type==='settings'&&<><dl className="scope-detail-fields"><dt>任务执行</dt><dd>DSH headless</dd><dt>策略分析</dt><dd>Pi</dd><dt>权限管理</dt><dd>ScopeManager</dd><dt>文件限制</dt><dd>Broker / ActPlane</dd><dt>运行环境</dt><dd>本机独立 Demo</dd></dl>
          <p className="scope-muted">开放报告目录需要重启 DSH，保存公开任务进展后继续执行。</p></>}
        {detail?.type==='connection'&&connection&&<><Badge tone={connection.tone}>{connection.label}</Badge>
          <dl className="scope-detail-fields"><dt>绑定任务</dt><dd>{task}</dd><dt>当前 DSH 进程</dt><dd>{connection.pid?'PID '+connection.pid:connection.label}</dd>
            <dt>当前执行域</dt><dd>{connection.domain||'没有已确认的运行中 DSH 执行域'}</dd>
            <dt>最近工具回传</dt><dd>{connection.tool?when(connection.tool.occurred_at)+' · '+(connection.tool.payload.name||'工具操作')+' · '+(connection.toolInCurrentDomain?'本执行域':'历史回传'):'尚无工具回传'}</dd>
            <dt>最近上下文送达</dt><dd>{connection.delivery?when(connection.delivery.occurred_at)+' · 消息 v'+connection.delivery.payload.message_revision:'尚无送达记录'}</dd>
            <dt>最近内核记录</dt><dd>{connection.kernel?when(connection.kernel.occurred_at)+' · '+connection.kernelSource:'尚无内核记录'}</dd></dl>
          {connection.historyOnly&&<p className="scope-muted">这些回传时间是历史记录，不能证明当前 DSH 在线。</p>}
          <p className="scope-muted">仅连接本工作台受管启动的 DSH。工具执行前检查权限，执行后回传结果，页面每 3 秒回查；空闲期间没有独立心跳，无新回传不能单独判定断线。</p>
          <button className="scope-button" disabled={busy} onClick={()=>perform(async()=>{})}>回查当前状态</button>
          <Evidence value={{execution:data.execution,process_epoch:data.session.process_epoch,last_tool_result:connection.tool,last_context_delivery:connection.delivery,last_kernel_event:connection.kernel}}/></>}
        {detail?.type==='event'&&<><p>{when(detail.value.occurred_at)}</p><p>{detail.value.source==='agent_report'?'以下内容由 Agent 自报，独立验收需另行核验。':detail.value.source==='kernel'?'此文件操作被内核限制，具体路径和进程绑定见技术证据。':'公开执行结果和控制服务记录。'}</p>
          {(detail.value.payload.text||detail.value.payload.summary||detail.value.payload.error)&&<div className="scope-evidence-copy">{detail.value.payload.text||detail.value.payload.summary||detail.value.payload.error}</div>}<Evidence value={detail.value}/></>}
        {detail?.type==='error'&&<div className="scope-evidence-copy">{detail.value}</div>}
        {detail?.type==='closure'&&data&&<><p>执行域已关闭，临时授权与任务凭据已撤销。新任务从默认只读开始。</p><Evidence value={{session:data.session,execution:data.execution,closure:data.events.find(e=>e.source==='ended')}}/></>}
        {detail?.type==='close'&&<><p>停止当前执行，撤销本任务的临时权限和凭据，保留权限历史与执行记录。</p><button className="scope-button danger" disabled={busy}
          onClick={async()=>{if(await perform(()=>post('/api/tasks/'+task+'/scope-manager/close')))close();}}>结束并撤销</button></>}
      </div>
    </dialog>
  </div>;
}
