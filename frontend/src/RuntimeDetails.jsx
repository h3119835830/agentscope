import React,{useEffect,useRef,useState} from 'react';
import {connectionView} from './runtimeView.mjs';

function Fields({items}) {return <dl className="record-fields">{items.map(([name,value])=><React.Fragment key={name}><dt>{name}</dt><dd>{typeof value==='boolean'?(value?'是':'否'):value??'未记录'}</dd></React.Fragment>)}</dl>;}

export default function RuntimeDetails({detail,onClose}) {
 const ref=useRef(null),[tab,setTab]=useState('summary'),domain=detail.domain,process=detail.process,runtime=detail.runtime;
 useEffect(()=>{const node=ref.current,previous=document.activeElement;node.showModal();return()=>{node.close();if(previous?.isConnected)previous.focus();};},[]);
 const connection=runtime?connectionView(runtime):null;
 return <dialog ref={ref} className="record-drawer" aria-label={domain?'执行域详情':process?'进程采样详情':'连接详情'} onCancel={onClose}>
  <div className="record-drawer-head"><h2>{domain?domain.title:process?process.title:'DSH 连接详情'}</h2><button className="button ghost tiny" onClick={onClose}>关闭</button></div>
  {domain&&<div className="record-drawer-tabs" role="tablist" aria-label="执行域详情">{[['summary','加载与标签'],['dsl','已加载 DSL']].map(([id,label])=><button key={id} role="tab" aria-selected={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>}
  <div className="record-drawer-body">
   {domain&&(tab==='dsl'?<>{domain.available?<pre className="record-code">{domain.dsl}</pre>:<p>未取得与加载回执一致的 DSL，不能用重新生成的策略替代。</p>}<p className="muted">这是该次加载的策略源。当前是否生效需结合进程绑定核验。</p></>:<><div className="record-tags">{domain.labels.map(label=><span className="record-tag" key={label}>{label}</span>)}</div><p className="muted">标签来自 DSL 的 source 声明；当前未提供逐进程内核污点标签查询。</p><Fields items={[["域 ID",domain.domain_id],["策略版本",`v${domain.version}`],["域职责",domain.role==='baseline'?'启动底线域':'任务执行域'],["加载源已核验",domain.available],["加载时核验通过",domain.loading_verification_passed],["历史记录",domain.historical],["证据来源",domain.source==='confirmed_policy_hash'?'策略包与加载回执 hash 一致':domain.source==='root_owned_watch_artifact'?'root 所有的 watch 策略与控制记录':'加载源缺失或未核验'],["策略包 hash",domain.policy_hash]]}/></>)}
   {process&&<><p className="record-statement">进程采样记录</p><Fields items={[["PID",process.pid],["父进程 PID",process.ppid],["进程启动 ticks",process.start_ticks],["采样时间",detail.checked_at],["成员依据",process.domain_verified?'当前任务 cgroup 与内核 cap_task 映射':'当前任务 cgroup'],["实际域已核验",process.domain_verified]]}/><p className="muted">子进程名称来自 /proc，不能仅凭名称认定为某个子 Agent。采样不保证进程持续存活。</p></>}
   {runtime&&<><p className="record-statement">{connection.label}</p><Fields items={[["最近核验",runtime.execution.checked_at],["观测方式",'3 秒轮询；不是独立空闲心跳'],["当前 DSH PID",connection.live?runtime.execution.executor?.pid:'未核验'],["当前执行域",connection.live?runtime.execution.domain_id:'未核验'],["内核域成员核验",runtime.execution.domain_verified],["任务 cgroup 核验",runtime.execution.cgroup_verified],["工具放行",runtime.effective],["会话",runtime.state.session_id]]}/><details className="record-note"><summary>上次加载的绑定记录</summary><Fields items={[["域 ID",runtime.last_binding.domain_id],["Task runner PID",runtime.last_binding.runner_pid],["ActPlane watch PID",runtime.last_binding.watch_pid]]}/><p>已保存的 PID 不是当前在线证据。</p></details></>}
  </div>
 </dialog>;
}
