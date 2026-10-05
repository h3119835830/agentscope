import React, {useEffect, useRef, useState} from 'react';
import './scope.css';

const kinds={task_grant:'开放 backend / frontend',restrict:'收紧至 backend',expand:'开放 output 报告目录',guidance:'任务指导'};
const stateNames={cold:'冷启动',running:'执行中',waiting_constraint:'等待约束落实',ended:'已结束'};
const statusNames={queued:'排队',running:'分析中',completed:'已分析',failed:'失败',interrupted:'已中断',pending:'待审核',expired:'已过期',approved:'已批准',rejected:'已拒绝',compiled:'已编译',not_checked:'未编译',not_applied:'未应用',applying:'应用中',loaded:'已加载',loaded_unverified:'加载过，核验失败',confirmed:'已核验',unverified:'未核验',not_required:'无需变更'};
const initialText={task_grant:'授权修改 backend 和 frontend，保护 tests/config；output 需要单独审批。',
  restrict:'暂时只修改 backend，停止修改 frontend，继续保护 tests/config。',
  expand:'申请 output 写入任务报告，保留已生效的所有仓库限制。',guidance:'请用简洁清楚的文字解释修复结果。'};
const when=t=>new Date(t).toLocaleString('zh-CN',{hour12:false});

export default function ScopeWorkbench({api,post,notify}) {
  const [task,setTask]=useState(()=>{
    const selected=new URLSearchParams(window.location.search).get('task')||'';
    return /^[a-f0-9]{16}$/.test(selected)?selected:localStorage.getItem('scopeDemoTask')||'';
  });
  const [tasks,setTasks]=useState([]);
  const [data,setData]=useState(null);
  const [tab,setTab]=useState('current');
  const [kind,setKind]=useState('task_grant');
  const [text,setText]=useState(initialText.task_grant);
  const [busy,setBusy]=useState(false);
  const [showReviewed,setShowReviewed]=useState(false);
  const [error,setError]=useState('');
  const [detail,setDetail]=useState(null);
  const dialog=useRef(null);
  const opener=useRef(null);
  const tabs=useRef([]);
  const idempotence=useRef(null);
  const reload=async()=>{
    const list=await api('/api/tasks');
    setTasks(list.filter(t=>t.repo==='AgentScope/custom-scope-demo'));
    if(task)setData(await api('/api/tasks/'+task+'/scope-manager'));
  };
  useEffect(()=>{
    let live=true; setData(null);setError('');
    const fetchData=async()=>{try{
      const list=await api('/api/tasks');
      if(live)setTasks(list.filter(t=>t.repo==='AgentScope/custom-scope-demo'));
      if(task){const value=await api('/api/tasks/'+task+'/scope-manager');if(live){setData(value);setError('');}}
    }catch(e){if(live)setError(e.message);}};
    fetchData();const timer=setInterval(fetchData,3000);
    return()=>{live=false;clearInterval(timer);};
  },[task,api]);
  useEffect(()=>{if(detail){dialog.current.showModal();dialog.current.querySelector('button')?.focus();}},[detail]);
  useEffect(()=>{if(data&&data.session.phase!=='cold'&&kind==='task_grant'){setKind('restrict');setText(initialText.restrict);}},[data?.session.phase,kind]);
  const choose=id=>{setTask(id);localStorage.setItem('scopeDemoTask',id);idempotence.current=null;};
  const perform=async fn=>{setBusy(true);setError('');try{await fn();await reload();}catch(e){setError(e.message);notify(e.message);}finally{setBusy(false);}};
  const create=()=>perform(async()=>{const value=await post('/api/scope-demo/tasks');choose(value.task_id);setTab('current');});
  const open=(value,event)=>{opener.current=event.currentTarget;setDetail(value);};
  const close=()=>{dialog.current.close();setDetail(null);opener.current?.focus();};
  const assess=()=>perform(async()=>{
    if(!idempotence.current)idempotence.current=crypto.randomUUID();
    await post('/api/tasks/'+task+'/scope-manager/changes',{kind,text,request_key:idempotence.current,expected_snapshot:data.session.active_snapshot_id});
    idempotence.current=null;setTab('review');
  });
  const review=(d,decision)=>perform(async()=>{
    await post('/api/tasks/'+task+'/scope-manager/changes/'+d.id+'/review',{decision,expected_proposal_hash:d.proposal_hash,reviewed_by:'工作台研究者'});
    notify(decision==='approve'?'应用结果已回查，请查看当前权限':'候选已拒绝；用户收紧要求仍然保留');
  });
  const snapshot=data?.current;
  const scope=snapshot?.payload||data?.default_scope;
  const ended=data?.session.phase==='ended';
  const pending=data?.deltas.filter(d=>d.review_status==='pending')||[];
  const live=data?.effective;
  const changeKind=k=>{setKind(k);setText(initialText[k]);idempotence.current=null;};
  return <div className="content scope-workbench">
    <div className="page-header scope-top"><div><p className="eyebrow">文件权限闭环 · DSH</p><h1>任务工作台</h1>
      <p>{task?'任务 '+task:'创建独立项目，演示默认只读、任务授权、收紧、扩权与撤销。'}</p></div>
      <div className="scope-actions"><select aria-label="选择 Demo 任务" value={task} disabled={busy} onChange={e=>choose(e.target.value)}>
        <option value="">选择任务</option>{tasks.map(t=><option key={t.id} value={t.id}>{t.id} · {t.status}</option>)}</select>
        <button className="button" disabled={busy} onClick={create}>新建 Demo</button>
        <button className="button ghost" onClick={e=>open({title:'Agent 设置',settings:true},e)}>设置</button></div>
    </div>
    {error&&<div role="alert" className="inline-notice warning">{error}</div>}
    {data&&<>
      <div className="scope-status" aria-live="polite"><span>{stateNames[data.session.phase]||data.session.phase}</span>
        <span>已核验版本 {snapshot?'v'+snapshot.revision:'—'}</span><span>{live?'执行域已确认':ended?'临时授权已撤销':'执行域未确认'}</span>
        <span>{data.session.gate==='open'?'工具边界已开放':'工具边界：'+data.session.gate}</span></div>
      {data.execution.executor?.mode==='managed'&&<p className="scope-caption">DSH：{data.execution.executor.state==='running'?'运行中':'当前无执行进程'}。执行域可保留用于权限核验，任务结束后统一撤销。</p>}
      <div role="tablist" aria-label="任务工作台" className="scope-tabs">
        {[['current','当前权限'],['review','变更审核'],['records','执行记录']].map(([key,label],i)=><button key={key} ref={el=>tabs.current[i]=el}
          role="tab" id={'scope-tab-'+key} aria-controls={'scope-panel-'+key} aria-selected={tab===key} tabIndex={tab===key?0:-1}
          onClick={()=>setTab(key)} onKeyDown={e=>{
            if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();
              const n=e.key==='Home'?0:e.key==='End'?2:(i+(e.key==='ArrowRight'?1:2))%3;
              setTab(['current','review','records'][n]);tabs.current[n].focus();}
          }}>{label}{key==='review'&&pending.length>0?' · '+pending.length:''}</button>)}
      </div>
      {tab==='current'&&<section role="tabpanel" id="scope-panel-current" aria-labelledby="scope-tab-current" className="panel scope-pane">
        <div className="panel-head"><div><h2>{ended?'已结束的权限记录':live?'当前有效权限':'默认权限 / 最近核验记录'}</h2>
          <p>{ended?'本次授权不再有效，新任务从冷启动开始。':snapshot?'仅依据完整快照和执行域核验展示。':'运行冷启动探针后才会创建第一个有效快照。'}</p></div>
          <button className="button ghost" onClick={e=>open({title:'Scope 完整证据',value:{snapshot,execution:data.execution,baseline:data.default_scope}},e)}>详情</button></div>
        <div className="scope-table-wrap"><table><thead><tr><th>资源</th><th>允许操作</th><th>限制</th></tr></thead><tbody>
          {['backend','frontend','tests','config','output','runtime / tmp'].map(resource=>{
            const writable=resource==='runtime / tmp'||(resource==='output'?scope.allow_output:scope.allowed_write_dirs.includes(resource));
            return <tr key={resource}><td><code>{resource}</code></td><td>{ended?'授权已撤销':writable?'读取、写入、删除':'读取'}</td>
              <td>{resource==='tests'||resource==='config'?'保护资产':writable?'仅限本任务':'写入、删除、改名被限制'}</td></tr>;
          })}</tbody></table></div>
        <p className="scope-caption">生效范围：本机受管进程域的文件写入及删除。网络权限动态更新不在本 Demo 范围内。</p>
        <div className="scope-actions">
          {!snapshot&&<button className="button primary" disabled={busy} onClick={()=>perform(()=>post('/api/tasks/'+task+'/scope-manager/cold'))}>验证冷启动</button>}
          {snapshot&&data.session.phase==='cold'&&<button className="button primary" disabled={busy} onClick={()=>{changeKind('task_grant');setTab('review');}}>开启任务授权</button>}
          {!ended&&snapshot&&<button className="button danger" disabled={busy} onClick={()=>perform(()=>post('/api/tasks/'+task+'/scope-manager/close'))}>结束并撤销</button>}
        </div>
      </section>}
      {tab==='review'&&<section role="tabpanel" id="scope-panel-review" aria-labelledby="scope-tab-review" className="scope-pane">
        {!ended&&snapshot&&<form className="panel scope-request" onSubmit={e=>{e.preventDefault();assess();}}>
          <h2>提出任务要求</h2><label>变更类型<select value={kind} onChange={e=>changeKind(e.target.value)}>
            {Object.entries(kinds).filter(([k])=>data.session.phase==='cold'?k==='task_grant':k!=='task_grant').map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
          <label>用户要求<textarea minLength={4} maxLength={2000} required value={text} onChange={e=>{setText(e.target.value);idempotence.current=null;}}/></label>
          <p>收紧要求会在下一个工具边界暂停执行；扩权待审期间可继续现有权限内的操作。</p>
          <button className="button primary" disabled={busy||!!data.session.apply_id}>交给 Pi 分析</button>
        </form>}
        {data.deltas.length===0&&<div className="panel empty-box">尚无变更。先验证冷启动，再生成任务授权候选。</div>}
        <div className="scope-actions"><button className="button ghost" onClick={()=>setShowReviewed(!showReviewed)}>{showReviewed?'只看待处理变更':'查看已处理变更'}</button></div>
        {data.deltas.filter(d=>showReviewed||d.review_status==='pending').map(d=>{
          const job=data.jobs.find(j=>j.delta_id===d.id), proposal=d.proposal?.proposal;
          const base=data.snapshots.find(s=>s.id===d.base_snapshot_id)?.payload;
          const stale=d.base_snapshot_id!==data.session.active_snapshot_id||d.message_revision!==data.session.message_revision||d.process_epoch!==data.session.process_epoch;
          return <article className="panel scope-delta" key={d.id}><div className="panel-head"><div><h2>{kinds[d.kind]}</h2><p>{d.input.text}</p></div><span>{statusNames[d.review_status]}</span></div>
            <p>{proposal?.explanation||'Pi 正在读取固定上下文和已审核历史。'}</p>
            {proposal&&<div className="scope-diff"><div><small>基础 Scope</small><p>{base?.allowed_write_dirs.join('、')||'仓库只读'}；output {base?.allow_output?'可写':'禁止写入'}</p></div>
              <div><small>候选 Scope</small><p>{proposal.allowed_write_dirs.join('、')||'仓库只读'}；output {proposal.allow_output?'可写':'禁止写入'}</p></div></div>}
            <p className="scope-caption">{['review_status','compile_status','apply_status','verify_status'].map(k=>statusNames[d[k]]||d[k]).join(' → ')} · Pi {statusNames[job?.status]||'—'}</p>
            {job?.error&&<p role="alert">{job.error}</p>}{stale&&d.review_status==='pending'&&<p>输入版本已过期，请重新分析。</p>}
            <div className="scope-actions"><button className="button ghost" onClick={e=>open({title:'变更与证据',value:{delta:d,job}},e)}>查看证据</button>
              {!ended&&(stale||job?.status==='failed')&&d.review_status==='pending'&&<button className="button ghost" disabled={busy}
                onClick={()=>{changeKind(d.kind);setText(d.input.text);document.querySelector('.scope-request textarea')?.focus();}}>重新分析此请求</button>}
              {d.review_status==='pending'&&d.proposal_hash&&job?.status==='completed'&&!stale&&<>
                <button className="button primary" disabled={busy} onClick={()=>review(d,'approve')}>批准并应用</button>
                <button className="button" disabled={busy} onClick={()=>review(d,'reject')}>拒绝候选</button>
                <button className="button ghost" disabled={busy} onClick={()=>{changeKind(d.kind);setText(d.input.text);document.querySelector('.scope-request textarea')?.focus();}}>澄清并重新分析</button>
              </>}</div>
          </article>;
        })}
      </section>}
      {tab==='records'&&<section role="tabpanel" id="scope-panel-records" aria-labelledby="scope-tab-records" className="panel scope-pane">
        <h2>权限与执行时间线</h2><p>公开工具结果、内核拒绝、检查点和执行域切换持续在后台采集。</p>
        <ol className="scope-timeline">{data.events.map(e=><li key={e.id}><div><strong>{({confirmed:'权限核验成功',kernel:'内核拒绝',user_message:'用户要求',agent_request:'DSH 申请',candidate:'Pi 候选',checkpoint:'公开任务检查点',tool_result:'DSH 工具执行',ended:'任务结束',review:'候选审核',analysis_failure:'分析失败',apply_failure:'应用失败',agent_report:'DSH 公开报告',asset_manifest:'固定项目资产'})[e.source]||e.source}</strong>
          <time>{when(e.occurred_at)}</time></div><p>{e.payload.explanation||e.payload.text||e.payload.summary||e.payload.name||e.payload.event?.target||e.payload.error||('版本 '+(e.payload.revision??'—'))}</p>
          <button className="button ghost" onClick={event=>open({title:'执行证据',value:e},event)}>详情</button></li>)}</ol>
      </section>}
    </>}
    {!data&&!error&&<section className="panel empty-box">{task?'正在读取任务…':'新建 Demo 后，从冷启动验证开始。历史策略继续通过左侧独立入口查看。'}</section>}
    <dialog ref={dialog} className="scope-dialog" onCancel={()=>{setDetail(null);opener.current?.focus();}}>
      <div className="panel-head"><h2>{detail?.title}</h2><button className="button" onClick={close}>关闭</button></div>
      {detail?.settings?<><p>执行 Agent：DSH headless。策略生成：Pi。应用权限：ScopeManager → Broker / ActPlane。</p>
        <p>使用本机独立 Demo 实例和任务凭据，扩权会重启 DSH 并恢复公开任务检查点。</p></>:<pre>{JSON.stringify(detail?.value,null,2)}</pre>}
    </dialog>
  </div>;
}
