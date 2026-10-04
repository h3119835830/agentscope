import React, { useEffect, useRef, useState } from 'react';

const when = value => value ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '—';
const labels = {connected:'近期已通信',waiting:'等待接入',offline:'暂未通信',revoked:'已撤销',expired:'已过期',ended:'任务已结束',stale:'旧运行连接'};
const kinds = {progress:'任务进展',tool_feedback:'工具反馈',scope_blocked:'Scope 阻断反馈',result:'任务结果'};
const decisions = {approved:'已批准',rejected:'已拒绝',failed:'执行失败'};

export default function AgentBridge({tasks,selected,onSelect,api,post,notify}) {
  const [data,setData] = useState(null);
  const [error,setError] = useState('');
  const [name,setName] = useState('外部 HTTP Agent');
  const [text,setText] = useState('');
  const [busy,setBusy] = useState(false);
  const [pairing,setPairing] = useState(null);
  const dialog = useRef(null);
  const pairButton = useRef(null);
  const messageKey = useRef(null);
  const task = tasks.find(item=>item.id===selected);
  const reload = async()=>{if(selected)setData(await api(`/api/tasks/${selected}/agent-bridge`));};
  useEffect(()=>{
    let active=true;
    setData(null);setError('');setText('');setPairing(null);messageKey.current=null;
    const refresh=async()=>{if(!selected)return;try{const value=await api(`/api/tasks/${selected}/agent-bridge`);if(active){setData(value);setError('');}}catch(e){if(active)setError(e.message);}};
    refresh();const timer=setInterval(refresh,5000);
    return()=>{active=false;clearInterval(timer);};
  },[selected,api]);
  useEffect(()=>{if(pairing&&dialog.current){dialog.current.showModal();dialog.current.querySelector('button')?.focus();}},[pairing]);
  const closePairing=()=>{dialog.current?.close();setPairing(null);pairButton.current?.focus();};
  const perform=async fn=>{setBusy(true);try{await fn();await reload();}catch(e){notify(e.message);}finally{setBusy(false);}};
  const pair=()=>perform(async()=>{const value=await post(`/api/tasks/${selected}/agent-connections`,{name,ttl_seconds:3600});setPairing(value);});
  const send=()=>perform(async()=>{
    if(!messageKey.current)messageKey.current=crypto.randomUUID();
    await post(`/api/tasks/${selected}/agent-messages`,{text,request_key:messageKey.current});
    setText('');messageKey.current=null;notify('任务消息已排队，等待 Agent 读取与确认');
  });
  return <div className="content agent-bridge">
    <div className="page-header"><div><p className="eyebrow">第三层 · 外部执行 Agent</p><h1>运行时 Agent 接入</h1><p>DSH 使用受管任务凭据；其他 Agent 使用 HTTP 适配器，读取 Scope、接收任务消息、回传反馈和提交变更申请。</p></div>
      <label>任务<select className="task-select" disabled={busy} value={selected} onChange={e=>onSelect(e.target.value)}><option value="">选择任务</option>{tasks.map(t=><option key={t.id} value={t.id}>{t.name} · {t.status}</option>)}</select></label>
    </div>
    <div className="inline-notice">HTTP 接入只提供通信。远程 Agent 的进程不受本机 ActPlane 约束；消息确认是 Agent 自报，内核效果仍须独立回查与探针验证。运行时 Pi 增量生成尚未接通。</div>
    {error&&<div role="alert" className="inline-notice warning">{error}</div>}
    {!task?<section className="panel empty-box">选择一个任务查看连接和通信记录。新接入需要任务已经批准并运行。</section>:<>
      <section className="panel"><div className="panel-head"><div><h2>当前任务与 Scope</h2><p>{task.repo} · 固定 commit <code>{task.commit_sha}</code></p></div><button className="button ghost" disabled={busy} onClick={()=>perform(async()=>{})}>刷新</button></div>
        <p>{data?.current?`策略 v${data.current.policy_version} · Scope 修订 ${data.current.scope_revision}`:'任务没有可接入的运行中批准版本'}</p>
        {data?.current&&<details><summary>查看运行绑定、策略 hash 与 DSL</summary><pre>{JSON.stringify({run_key:data.current.run_key,bundle_hash:data.current.bundle_hash,domain:data.current.task_domain,runner_pid:data.current.task_runner_pid},null,2)}</pre><pre>{data.current.dsl}</pre></details>}
      </section>
      <div className="grid-two"><section className="panel"><h2>接入其他 Agent</h2><p>先创建限时任务凭据，再交给该 Agent 的适配器。凭据仅适用于当前运行，不能审批或加载策略。</p>
        <label>连接名称<input maxLength={80} value={name} onChange={e=>setName(e.target.value)} /></label>
        <button ref={pairButton} className="button primary" disabled={busy||!data?.current||!name.trim()} onClick={pair}>创建 HTTP 接入凭据</button>
        <p className="field-note">有效期 1 小时。DSH 无需手工配对；调用接入工具后自动登记。开发服务保持本机访问，远程接入部署须配置 HTTPS。</p>
      </section><section className="panel"><h2>发送任务消息</h2><p>消息保存在队列中，Agent 主动读取后回传确认。此操作不会直接修改内核权限。</p>
        <label>消息内容<textarea rows={3} maxLength={4000} value={text} onChange={e=>{setText(e.target.value);messageKey.current=null;}} placeholder="例如：请先保存当前进展，并说明后续需要的操作范围。"/></label>
        <button className="button primary" disabled={busy||!data?.current||!text.trim()} onClick={send}>发送给当前任务 Agent</button>
      </section></div>
      <section className="panel"><h2>连接记录</h2><div className="table-scroll"><table><thead><tr><th>连接</th><th>适配器 / 状态</th><th>最近通信 / 到期</th><th>操作</th></tr></thead><tbody>{data?.connections.map(c=><tr key={c.id}><td>{c.name}<small>{c.id.slice(0,12)}</small></td><td>{c.adapter==='dsh'?'DSH 受管插件':'HTTP 通信适配器'}<small>{labels[c.status]}</small></td><td>{when(c.last_seen_at)}<small>到期：{when(c.expires_at)}</small></td><td><button className="button tiny ghost" disabled={busy||c.status==='revoked'} onClick={()=>perform(async()=>{await post(`/api/tasks/${selected}/agent-connections/${c.id}/revoke`);notify('接入凭据已撤销');})}>撤销接入</button></td></tr>)}{!data?.connections.length&&<tr><td colSpan={4}>暂无连接。DSH 首次调用通信工具后登记。</td></tr>}</tbody></table></div></section>
      <section className="panel"><h2>发出消息与接收确认</h2><p className="field-note">最多展示最近 100 条，包含历史运行；旧运行消息不会交付到新进程。处理确认不能证明模型遵从或内核生效。</p>
        {data?.messages.map(m=><article className="request-card" key={m.id}><b>{m.kind==='user_message'?'用户任务消息':'Scope 审核通知'}</b><p>{m.content.text||`申请 ${m.content.request_id} · ${decisions[m.content.status]||m.content.status}`}</p><small>{when(m.created_at)} · {m.run_key===data.current?.run_key?'当前运行':'历史运行'}</small><p>已确认接收 {m.receipts.length} · 自报已处理 {m.receipts.filter(r=>r.status==='handled').length}</p><details><summary>消息与回执</summary><pre>{JSON.stringify({id:m.id,content:m.content,receipts:m.receipts},null,2)}</pre></details></article>)}
        {!data?.messages.length&&<div className="empty-box">暂无任务消息或审核通知。</div>}
      </section>
      <section className="panel"><h2>Agent 反馈</h2><p className="field-note">独立保存 Agent 自报，不混入 ActPlane 内核事件。</p>{data?.feedback.map(f=><article className="request-card" key={f.id}><b>{kinds[f.kind]} · Agent 自报</b><p>{f.summary}</p><small>{f.operation} {f.target} · {when(f.created_at)}</small></article>)}{!data?.feedback.length&&<div className="empty-box">暂无反馈。</div>}</section>
    </>}
    {pairing&&<dialog ref={dialog} className="bridge-pair-dialog" onCancel={event=>{event.preventDefault();closePairing();}}><div className="panel-head"><h2>HTTP 接入凭据</h2><button className="button ghost" onClick={closePairing} aria-label="关闭接入凭据">关闭</button></div>
      <p>仅展示本次，关闭后不再显示。把凭据配置在适配器进程环境中，勿放入聊天或提交记录。</p><label>任务 ID<input readOnly value={pairing.task_id}/></label><label>接入凭据<input type="password" readOnly value={pairing.token} autoComplete="off"/></label>
      <button className="button primary" onClick={async()=>{try{await navigator.clipboard.writeText(pairing.token);notify('已复制任务接入凭据');}catch{notify('复制不可用，请选中凭据输入框复制');}}}>复制接入凭据</button><p className="field-note">到期：{when(pairing.expires_at)} · 仅控制面通信权限</p>
    </dialog>}
  </div>;
}
