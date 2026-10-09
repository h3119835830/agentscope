import React, {useEffect, useRef, useState} from 'react';
import {phaseName, timeLabel} from './taskPresentation.mjs';
import {tabKeys} from './consoleState.mjs';
import {workspaceTasks, workspaceSessions, policySentence, policyOutcome} from './workspaceRecords.mjs';

function WorkspacePolicies({workspace, tasks, api, onOpenTask}) {
  const [taskId, setTaskId] = useState(tasks[0]?.id || '');
  const [stage, setStage] = useState('startup');
  const [data, setData] = useState(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const [retry, setRetry] = useState(0);
  const request = useRef(0);
  const task = tasks.find(row => row.id === taskId);
  useEffect(() => {
    if (!tasks.some(row => row.id === taskId)) setTaskId(tasks[0]?.id || '');
  }, [tasks, taskId]);
  async function load(cursor) {
    const sequence = ++request.current;
    setLoading(true); setError('');
    try {
      const query = new URLSearchParams({stage, view: 'statements_only', limit: '12'});
      if (cursor) query.set('cursor', cursor);
      const result = await api(`/api/tasks/${encodeURIComponent(taskId)}/archive/policies?${query}`);
      if (sequence === request.current) setData(previous => ({...result, records: cursor ? [...(previous?.records || []), ...result.records] : result.records}));
    } catch (e) { if (sequence === request.current) setError(e.message); }
    finally { if (sequence === request.current) setLoading(false); }
  }
  useEffect(() => {
    setData(null); setError('');
    if (taskId) load();
    return () => { request.current++; };
  }, [taskId, stage, retry, api]);
  if (!tasks.length) return <p className="task-empty">此工作区还没有关联的任务策略记录。</p>;
  return <>
    <div className="workspace-policy-filters">
      <label>所属任务<select aria-label="所属任务" value={taskId} onChange={event => setTaskId(event.target.value)}>{tasks.map(row => <option key={row.id} value={row.id}>{row.name || row.id}（{row.id.slice(0, 8)}）</option>)}</select></label>
      <label>记录阶段<select aria-label="记录阶段" value={stage} onChange={event => setStage(event.target.value)}><option value="startup">运行前</option><option value="runtime">运行时</option></select></label>
    </div>
    <dl className="task-fields workspace-record-facts"><dt>来源工作区</dt><dd>{workspace.path}</dd><dt>任务执行目录</dt><dd>{task?.workspace || '未记录'}</dd><dt>记录含义</dt><dd>以下为该任务保存的策略，当前生效状态未在此核验。</dd></dl>
    {error && <p role="alert" className="inline-notice warning">读取失败：{error} <button type="button" className="button ghost tiny" onClick={() => data ? load(data.next_cursor) : setRetry(value => value + 1)}>重试</button></p>}
    {loading && !data && <p role="status" className="task-empty">正在读取策略记录…</p>}
    {data && <>
      <div className="table-scroll"><table className="task-record-table workspace-policy-table" aria-label="工作区关联任务的策略记录"><thead><tr><th>策略语句</th><th>类型</th><th>处理结果</th></tr></thead><tbody>
        {[...data.records].sort((a, b) => Number(['guidance', 'guidance_only'].includes(a.effect)) - Number(['guidance', 'guidance_only'].includes(b.effect))).map(record => <tr key={record.id}><td><p className="workspace-policy-sentence">{policySentence(record)}</p>{record.statement && policySentence(record) !== record.statement && <details className="workspace-source-statement"><summary>原始说明</summary><p>{record.statement}</p></details>}<small>{record.created_at ? timeLabel(record.created_at) : '记录时间未提供'}</small></td><td>{['guidance', 'guidance_only'].includes(record.effect) ? '行为约定' : '执行规则'}</td><td>{policyOutcome(record)}</td></tr>)}
        {!data.records.length && <tr><td colSpan={3} className="task-empty">此阶段尚无策略语句记录。</td></tr>}
      </tbody></table></div>
      <div className="task-table-foot"><span>已显示 {data.records.length} / {data.total} 条</span>{data.next_cursor && <button type="button" className="button ghost tiny" disabled={loading} onClick={() => load(data.next_cursor)}>{loading ? '正在读取…' : '更多记录'}</button>}</div>
    </>}
    <button type="button" className="button ghost workspace-open-task" onClick={() => onOpenTask?.(taskId)}>查看完整任务记录</button>
  </>;
}

export default function WorkspaceRecords({workspace, agent, tasks, api, files, onFilesActive, onOpenTask, onCreateTask, canCreate, onClose, trigger}) {
  const dialog = useRef(null), origin = useRef(trigger || document.activeElement);
  const [tab, setTab] = useState('associations'), [visible, setVisible] = useState(12);
  const related = workspaceTasks(workspace, tasks), sessions = workspaceSessions(workspace);
  const tabs = [['associations', '关联记录'], ['policies', '策略记录'], ['files', '文件']];
  useEffect(() => {
    dialog.current?.showModal(); dialog.current?.querySelector('button')?.focus();
    return () => { dialog.current?.close(); if (origin.current?.isConnected) origin.current.focus({preventScroll: true}); };
  }, []);
  useEffect(() => { onFilesActive(tab === 'files'); return () => onFilesActive(false); }, [tab, onFilesActive]);
  const records = [...sessions.map(id => ({id, type: 'session'})), ...related.map(task => ({...task, type: 'task'}))];
  return <dialog ref={dialog} className="record-drawer workspace-record-drawer" aria-label="工作区记录" onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className="record-drawer-head"><h2>{workspace.name || '工作区记录'}</h2><button type="button" className="button ghost tiny" onClick={onClose}>关闭</button></div>
    <div className="record-drawer-tabs" role="tablist" aria-label="工作区记录内容">{tabs.map(([key, label]) => <button type="button" key={key} role="tab" id={`workspace-record-tab-${key}`} aria-controls={`workspace-record-pane-${key}`} aria-selected={tab === key} tabIndex={tab === key ? 0 : -1} onClick={() => setTab(key)} onKeyDown={event => tabKeys(event, tabs.map(([value]) => value), tab, setTab)}>{label}</button>)}</div>
    <div className="record-drawer-body" role="tabpanel" id={`workspace-record-pane-${tab}`} aria-labelledby={`workspace-record-tab-${tab}`}>
      {tab === 'associations' && <>
        <dl className="task-fields workspace-record-facts"><dt>所属实例</dt><dd>{agent?.name || workspace.agent_id}</dd><dt>工作区目录</dt><dd>{workspace.path}</dd><dt>读取状态</dt><dd>{workspace.readable ? '可读取' : '不可读取'}</dd><dt>会话关联</dt><dd>原生工作区注册表登记了 {sessions.length} 个会话，未提供这些会话的运行状态。</dd><dt>任务关联</dt><dd>{related.length} 个任务以此工作区为来源；任务在各自的执行目录中运行。</dd></dl>
        <div className="table-scroll"><table className="task-record-table workspace-association-table" aria-label="工作区会话与来源任务"><thead><tr><th>记录类型</th><th>名称与标识</th><th>处理状态</th><th>操作</th></tr></thead><tbody>
          {records.slice(0, visible).map(row => <tr key={`${row.type}:${row.id}`}><td>{row.type === 'session' ? '原生会话' : '来源任务'}</td><td>{row.type === 'task' && <b>{row.name || '未命名任务'}</b>}<span className="task-path">{row.id}</span>{row.type === 'task' && <small>执行目录：{row.workspace || '未记录'}</small>}</td><td>{row.type === 'session' ? '运行状态未提供' : phaseName(row.phase || row.status)}</td><td>{row.type === 'task' ? <button type="button" className="button ghost tiny" onClick={() => onOpenTask?.(row.id)}>查看任务</button> : '—'}</td></tr>)}
          {!records.length && <tr><td colSpan={4} className="task-empty">原生注册表尚无会话记录，此工作区也没有来源任务。</td></tr>}
        </tbody></table></div>
        {records.length > visible && <button type="button" className="button ghost tiny" onClick={() => setVisible(count => count + 12)}>更多关联记录</button>}
        <details className="workspace-mapping-evidence"><summary>映射依据</summary><dl className="task-fields"><dt>工作区标识</dt><dd>{workspace.id}</dd><dt>原生工作区标识</dt><dd>{workspace.native_workspace_id || '未提供'}</dd><dt>实例标识</dt><dd>{workspace.agent_id}</dd><dt>观测实例代次</dt><dd>{workspace.instance_generation || '未提供'}</dd><dt>关联依据</dt><dd>会话来自原生注册表；来源任务按保存的工作区标识关联，不通过目录名称猜测。</dd><dt>执行保护</dt><dd>当前执行进程与策略生效需在策略工作台单独核验。</dd></dl></details>
        <button type="button" className="button primary workspace-open-task" disabled={!canCreate} onClick={() => onCreateTask(workspace.id)}>在此工作区新建任务</button>
      </>}
      {tab === 'policies' && <WorkspacePolicies workspace={workspace} tasks={related} api={api} onOpenTask={onOpenTask}/>}
      {tab === 'files' && (workspace.readable ? files : <p className="task-empty">此工作区当前不可读取。</p>)}
    </div>
  </dialog>;
}
