import React, { useEffect, useState } from 'react';
import './bootstrap.css';

const cases = ['safety-delete-config', 'safety-impossible-tests', 'safety-abusive-apology'];
export default function BootstrapPanel({ task, api, post, action, busy, selectTask, refresh }) {
  const [state, setState] = useState(null);
  const [error, setError] = useState('');
  const [scene, setScene] = useState(cases[0]);
  const [condition, setCondition] = useState('B');
  const eligible = task && cases.includes(task.name);
  const load = async () => {
    if (!eligible) return;
    try { setState(await api(`/api/tasks/${task.id}/bootstrap`)); setError(''); }
    catch (e) { setError(e.message); }
  };
  useEffect(() => { setState(null); setError(''); if (!eligible) return; load(); const timer = setInterval(load, 3000); return () => clearInterval(timer); }, [task?.id]);
  if (task && !eligible) return null;
  const proposal = state?.proposals?.[0];
  const data = proposal?.proposal || {};
  const job = state?.jobs?.[0];
  const link = state?.versions?.[0];
  const run = fn => action(async () => { await fn(); await load(); await refresh(); });
  return <section className="panel bootstrap-panel">
    <div className="panel-head"><div><h2>Pi 启动前策略生成 · RQ5 扩展验收</h2><p>场景证据与已审历史共同生成候选，审批后加载到 DSH 进程域。</p></div></div>
    {!task ? <div className="bootstrap-controls"><select aria-label="RQ5 场景" value={scene} onChange={e => setScene(e.target.value)}>{cases.map(c => <option key={c}>{c}</option>)}</select><button className="button primary" disabled={busy} onClick={() => run(async () => { const created = await post(`/api/rq5/scenarios/${scene}/tasks`); selectTask(created.id); })}>创建固定场景任务</button><small>独立工作区；历史测试样例仅在验收实例中启用。</small></div> : <>
      <p>场景 hash：<code>{state?.context?.scenario_hash}</code><br/>上下文 hash：<code>{state?.context?.context_hash}</code></p>
      <div className="bootstrap-controls"><button className="button primary" disabled={busy || !['prepared','policy_review','approved'].includes(task.status)} onClick={() => run(() => post(`/api/tasks/${task.id}/bootstrap`))}>启动 Pi 生成</button><span>作业：{job?.status || '尚未生成'} · {state?.tool_events?.length || 0} 次工具记录</span>{['queued','running'].includes(job?.status) && <button className="button ghost" onClick={() => run(() => post(`/api/tasks/${task.id}/bootstrap/jobs/${job.id}/cancel`))}>中断生成</button>}</div>
      {(error || job?.error) && <div className="inline-notice warning">{error || job.error}</div>}
      {data.draft && <><h3>{data.draft.summary}</h3>{data.draft.no_op && <p>no-op：新增执行 DSL 为空；语义要求作为指导项展示。</p>}
        {proposal.state === 'needs_clarification' && <div className="inline-notice warning">待澄清：{data.gaps.join('；')}。执行缺口解决前不能构建加载包。</div>}
        {data.policy_ir?.atoms?.map((atom, i) => <article className="bootstrap-atom" key={i}><b>{atom.decision} · {atom.statement}</b><p>{atom.reason}</p><code>{atom.paths.join('\n')}</code><small>历史来源：{atom.history_id || '当前任务新候选'} {atom.history_hash || ''}</small><small>证据：{atom.evidence_ids.join(', ')}</small></article>)}
        <h4>批准时一并保留的指导项</h4><ul>{data.guidance?.map((g, i) => <li key={i}>{g}</li>)}</ul>
        <details><summary>证据、参数来源、范围差异与编译诊断</summary><pre>{JSON.stringify({history: data.history_bindings, scope: data.scope_diff, validation: proposal.validation, gaps: data.gaps}, null, 2)}</pre></details>
        <details><summary>确定性生成的新增 DSL 与伪代码</summary><pre>{data.actplane_dsl || '(空)'}</pre><pre>{data.metadata_pseudocode?.join('\n')}</pre></details>
        <div className="bootstrap-controls"><select aria-label="实验组" value={condition} onChange={e => setCondition(e.target.value)}><option value="A">A：基础限制与指导项</option><option value="B">B：增加任务执行规则</option></select><button className="button primary" disabled={busy || proposal.state !== 'validated' || !['prepared','policy_review','approved'].includes(task.status)} onClick={() => run(() => post(`/api/tasks/${task.id}/bootstrap/proposals/${proposal.id}/versions`, {condition}))}>构建待审整包</button>{link && <button className="button success" disabled={busy || link.compile_state !== 'compiled' || !['prepared','policy_review','approved'].includes(task.status)} onClick={() => run(() => post(`/api/tasks/${task.id}/versions/${link.version}/approve`, {decision:'approve', reviewed_by:'研究者', expected_context_hash:link.context_hash, expected_proposal_hash:link.proposal_hash}))}>按 hash 批准 v{link.version} · {link.condition}</button>}</div>
      </>}
      {state?.acceptance && <details open><summary>独立验收结果</summary><pre>{JSON.stringify(state.acceptance, null, 2)}</pre></details>}
      <details><summary>生成进度、任务合同与已登记证据</summary><pre>{JSON.stringify(state?.tool_events?.map(e => ({time:e.occurred_at, tool:e.tool, valid:e.output?.valid, diagnostic:e.output?.diagnostic})), null, 2)}</pre><pre>{JSON.stringify({workspace:state?.context?.mapping, asset_layout:state?.context?.asset_layout_mapping, requirements:state?.context?.declared_constraints}, null, 2)}</pre></details>
    </>}
  </section>;
}
