import React,{useEffect,useReducer,useRef,useState} from 'react';
import {runtimeHooksPath,readRuntimeHooksPage,runtimeHooksState,runtimeHooksReducer,runtimeHookLabel,runtimeHookMissingLabel,runtimeHookStatus,runtimeHookPosition,runtimeHookTime,runtimeHookFocusState,registerRuntimeHookButton,restoreRuntimeHookFocus} from './runtimeHooks.mjs';
import './runtimeHooks.css';

function HookFields({items}) {
  return <dl className="runtime-hook-fields">{items.map(([label,value]) => <React.Fragment key={label}><dt>{label}</dt><dd>{value === null || value === undefined || value === '' ? '未记录' : value}</dd></React.Fragment>)}</dl>;
}

export function RuntimeHookOverview({mechanism}) {
  if (!mechanism) return null;
  return <>
    <p className="runtime-hooks-note">当前触发来源：{mechanism.events.length ? mechanism.events.join('、') : '当前定义未列出触发来源'}。</p>
    <details className="runtime-hook-mechanism">
      <summary>当前接入说明，非历史冻结配置</summary>
      <HookFields items={[["接入名称",mechanism.name],["说明来源",'当前代码定义'],["历史配置",'未保存历史冻结配置']]}/>
      <h4>当前处理链</h4>
      {mechanism.sequence.length ? <ol className="runtime-hook-sequence">{mechanism.sequence.map((step,index) => <li key={index}>{step}</li>)}</ol> : <p className="runtime-hooks-note">当前定义未列出处理步骤。</p>}
    </details>
  </>;
}

export function RuntimeHookDetail({record,onBack}) {
  const heading = useRef(null);
  useEffect(() => {heading.current?.focus();},[record.id]);
  const trigger = record.trigger || {}, observations = trigger.observations || [];
  return <section className="runtime-hook-record" aria-label="Hook 触发记录详情">
    <div className="runtime-hooks-head"><h4 ref={heading} tabIndex={-1}>触发记录详情</h4><button type="button" className="button ghost tiny" onClick={onBack}>返回触发记录</button></div>
    <HookFields items={[
      ["发生时间",runtimeHookTime(record.time)],["触发来源",runtimeHookLabel(trigger.name)],
      ["触发方",runtimeHookLabel(trigger.actor)],["执行轮次",trigger.turn],["接收轮次",trigger.accepted_turn],
      ["上下文修订",trigger.revision],["生成作业",record.job_id],["关联请求",record.request_id],
      ["生成状态",runtimeHookLabel(record.generation_status)],["触发材料",runtimeHookStatus(record)],
    ]}/>
    {record.missing_fields?.length > 0 && <p className="runtime-hooks-note">未记录字段：{record.missing_fields.map(runtimeHookMissingLabel).join('、')}。</p>}
    <h4>来源观测</h4>
    <p className="runtime-hooks-note">保存于该次评估的上下文快照，条目不一定都是本轮新触发。</p>
    <p className="runtime-hooks-note">观测材料：{trigger.observations_status === 'recorded' ? '字段已记录' : '存在未记录字段'}。</p>
    {observations.length ? <ul className="runtime-hook-observations">{observations.map((observation,index) => <li key={index}><HookFields items={[["观测类别",runtimeHookLabel(observation.category)],["事件类型",runtimeHookLabel(observation.type)],["观测序号",observation.seq],["材料状态",observation.status === 'recorded' ? '字段已记录' : '存在未记录字段']]}/>{observation.missing_fields?.length > 0 && <p className="runtime-hooks-note">未记录字段：{observation.missing_fields.map(runtimeHookMissingLabel).join('、')}。</p>}</li>)}</ul> : <p className="runtime-hooks-note">未保存来源观测条目。</p>}
    <details className="runtime-hook-technical"><summary>记录编号、证据引用与原始标识</summary>
      <HookFields items={[["记录编号",record.id],["触发来源原值",trigger.name],["触发方原值",trigger.actor]]}/>
      <h4>证据引用</h4>{record.evidence_refs?.length ? <ul>{record.evidence_refs.map((reference,index) => <li key={index}>{reference}</li>)}</ul> : <p className="runtime-hooks-note">未记录证据引用。</p>}
      {observations.length > 0 && <><h4>观测原始标识</h4>{observations.map((observation,index) => <HookFields key={index} items={[["观测条目",index + 1],["类别原值",observation.category],["事件类型原值",observation.type],["内容 hash",observation.content_hash]]}/>)}</>}
    </details>
  </section>;
}

export function RuntimeHookList({records,total,shown=5,busy=false,loaded=true,error='',nextCursor=null,onOpen,onButtonRef,onShowMore,onLoadMore}) {
  return <>
    <div className="runtime-hook-table-wrap"><table className="runtime-hook-table"><thead><tr><th scope="col">时间</th><th scope="col">触发来源</th><th scope="col">轮次 / 修订</th><th scope="col">生成作业</th><th scope="col">记录状态</th><th scope="col">详情</th></tr></thead><tbody>
      {records.slice(0,shown).map(record => <tr key={record.id}>
        <td>{runtimeHookTime(record.time)}</td><td>{runtimeHookLabel(record.trigger?.name)}<small>{runtimeHookLabel(record.trigger?.actor)}</small></td>
        <td>{runtimeHookPosition(record)}</td><td title={record.job_id || undefined}>{record.job_id || '未记录'}</td>
        <td><span className="runtime-hook-label">{runtimeHookStatus(record)}</span><small>生成：{runtimeHookLabel(record.generation_status)}</small></td>
        <td><button ref={button => onButtonRef?.(record.id,button)} type="button" className="button ghost tiny" onClick={() => onOpen?.(record)}>查看详情</button></td>
      </tr>)}
      {!records.length && <tr><td colSpan={6}>{!loaded && !error ? '正在读取触发记录…' : error ? '触发记录读取失败，请重试。' : '未保存实际 Hook 触发记录。'}</td></tr>}
    </tbody></table></div>
    <div className="runtime-hook-counts"><span>已显示 {Math.min(shown,records.length)} / 已载入 {records.length} 条{loaded ? ` · 共 ${total} 条` : ''}</span>
      {shown < records.length ? <button type="button" className="button ghost tiny" onClick={onShowMore}>再显示 12 条触发记录</button> : nextCursor !== null && <button type="button" className="button ghost tiny" disabled={busy} onClick={onLoadMore}>{busy ? '正在读取…' : '载入更早触发记录'}</button>}
    </div>
  </>;
}

export default function RuntimeHooks({task,api}) {
  const [state,dispatch] = useReducer(runtimeHooksReducer,task,runtimeHooksState);
  const [retry,setRetry] = useState(0),[shown,setShown] = useState(5),[selected,setSelected] = useState(null);
  const sequence = useRef(0), focus = useRef(null);
  if (focus.current?.task !== task) focus.current = runtimeHookFocusState(task);
  const current = state.task === task ? state : runtimeHooksState(task);
  async function readPage(before=null,append=false) {
    const request = ++sequence.current;
    dispatch({type:'start',task,request,append});
    try {
      const page = readRuntimeHooksPage(await api(runtimeHooksPath(task,before)));
      if (before !== null && page.next_cursor === before) throw new Error('更早记录的游标未前进，请重新读取。');
      if (sequence.current === request) dispatch({type:'success',task,request,page,append});
    } catch (error) {
      if (sequence.current === request) dispatch({type:'error',task,request,error:error.message || '触发记录读取失败。'});
    }
  }
  useEffect(() => {
    setShown(5);setSelected(null);readPage();
    return () => {sequence.current++;};
  },[task,api,retry]);
  const detail = current.records.find(record => record.id === selected);
  return <section className="runtime-hooks" aria-label="Hook 触发点">
    <div className="runtime-hooks-head"><div><h3>Hook 触发点</h3><p>已保存触发记录；手动刷新读取最新保存结果，不是实时事件流。</p></div><button type="button" className="button ghost tiny" disabled={current.busy} onClick={() => setRetry(value => value + 1)}>刷新触发记录</button></div>
    <RuntimeHookOverview mechanism={current.mechanism}/>
    {current.error && <p className="runtime-hook-error" role="alert">读取失败：{current.error} <button type="button" className="button ghost tiny" onClick={() => setRetry(value => value + 1)}>重试触发记录</button></p>}
    {detail ? <RuntimeHookDetail record={detail} onBack={() => {const previous=focus.current;setSelected(null);requestAnimationFrame(() => {if (focus.current===previous) restoreRuntimeHookFocus(focus.current,task,detail.id);});}}/> : <RuntimeHookList records={current.records} total={current.total} shown={shown} busy={current.busy} loaded={current.loaded} error={current.error} nextCursor={current.next_cursor} onButtonRef={(id,button) => registerRuntimeHookButton(focus.current,task,id,button)} onOpen={record => {focus.current.record=record.id;setSelected(record.id);}} onShowMore={() => setShown(value => value + 12)} onLoadMore={() => {setShown(value => value + 12);readPage(current.next_cursor,true);}}/>}
    <p className="runtime-hooks-note">这些历史触发材料不能证明策略已批准、加载或生效。</p>
  </section>;
}
