import React,{useState} from 'react';
import {connectionView,relativeTarget} from './runtimeView.mjs';
import {auditSource,auditIdentity} from './consoleState.mjs';
import {RuntimeModeTabs} from './WorkbenchRecordViews.jsx';
import DomainGraph from './DomainGraph.jsx';

const operations={replace:'替换',hardlink:'硬链接',symlink_write:'经符号链接写入',ancestor_rename:'改名父目录',mmap_new:'共享映射写入',hold:'持有文件句柄',fd_write:'通过已有句柄写入',write:'写入',write_open:'打开写入',read:'读取',unlink:'删除',rename:'重命名',mkdir:'创建目录',rmdir:'删除目录',execute:'执行'};
const resultNames={denied:'已拦截',correct_block:'核验拦截',correct_allow:'核验允许',false_block:'误拦截',missed_block:'漏拦截',operation_failed:'操作失败',unverified_denial:'拒绝待核验'};
const clock=value=>value?new Date(value).toLocaleTimeString('zh-CN',{hour12:false}):'—';

export default function RuntimeOverview({data,binding,files,tools,failed,graph,now,onVersion,onDomain,onProcess,onAudit,onDetails,onShowAudit}) {
  const [pane,setPane]=useState('graph');
  const connection=connectionView(data,{failed,now}),e=data.execution,resources=data.resources;
  const latest=tools.records.find(row=>row.kind==='tool_result');
  const processes=[...(e.processes||[]).map(p=>({name:p.title,pid:p.pid,role:p.role==='agent'?'任务执行':p.role==='runner'?'执行进程父级':'子进程',domain:p.domain_verified?e.domain_id:null})),
    ...(e.watch_pid?[{name:'ActPlane watch',role:'策略监控 · 控制面',pid:e.watch_pid,control:true}]:[])];
  return <section className="runtime-overview" aria-label="任务运行总览">
    <RuntimeModeTabs mode={pane} onMode={setPane}>{pane==='files'&&<button className="text-action" onClick={onShowAudit}>全部审计 →</button>}</RuntimeModeTabs>
    <div id="runtime-panel" role="tabpanel" aria-labelledby={'runtime-'+pane}>
    {pane==='graph'&&<DomainGraph graph={graph} files={files} workspace={binding.workspace} fresh={connection.fresh&&now-Date.parse(graph?.checked_at||'')<10000} onVersion={onVersion} onDomain={onDomain} onProcess={onProcess} onAudit={onAudit}/>}
    {pane==='files'&&<div role="tabpanel" aria-label="文件活动"><div className="runtime-table-wrap"><table className="runtime-table"><thead><tr><th>文件 / 执行来源</th><th>操作</th><th>真实结果</th><th>时间</th></tr></thead><tbody>{files.records.slice(0,8).map(a=><tr key={a.id}><td><button className="file-link" onClick={()=>onAudit(a)} title={a.target}>{relativeTarget(a.target,binding.workspace)}</button><small className="audit-identity">{auditIdentity(a)}</small></td><td>{operations[a.operation]||a.operation}</td><td><span className={'activity-result '+(['denied','correct_block','false_block','missed_block'].includes(a.result)?'warning':'')}>{resultNames[a.result]||a.result}</span></td><td><time title={a.time}>{clock(a.time)}</time></td></tr>)}</tbody></table></div>{!files.records.length&&<div className="runtime-empty"><strong>尚无文件操作证据</strong><p>受管任务产生内核拒绝或独立效果核验后，将出现在这里。</p></div>}<footer className="runtime-footnote">记录内核拒绝与独立核验；不包含全部文件读取。{latest&&<span>最近工具：{latest.operation} · {latest.result==='success'?'返回成功':latest.result==='failure'?'返回失败':latest.result} · {clock(latest.time)}</span>}</footer></div>}
    {pane==='processes'&&<div role="tabpanel" aria-label="关联进程"><div className="runtime-table-wrap"><table className="runtime-table"><thead><tr><th>进程</th><th>PID</th><th>职责</th><th>观测</th></tr></thead><tbody>{connection.live&&processes.map(p=><tr key={p.pid}><td>{p.name}</td><td>{p.pid}</td><td>{p.role}</td><td>{p.domain?'域成员已核验':p.control?'监控进程运行':'任务 cgroup'}</td></tr>)}</tbody></table></div>{!connection.live&&<div className="runtime-empty"><strong>{connection.label}</strong><p>没有核验到当前 DSH 执行进程。已保存的 PID 不作为在线证据。</p></div>}<footer className="runtime-footnote">显示当前任务的 DSH、执行器和策略监控进程。</footer></div>}
    {pane==='scope'&&<div role="tabpanel" aria-label="权限范围"><div className="runtime-table-wrap"><table className="runtime-table"><thead><tr><th>资源</th><th>策略声明</th></tr></thead><tbody><tr><td>工作区写入范围</td><td>{resources.allowed_write_dirs.join('、')||'未开放'}</td></tr><tr><td>output</td><td>{resources.allow_output?'已授权写入':'未授权写入'}</td></tr>{[...new Set([...resources.protected,...resources.runtime_protected])].map(p=><tr key={p}><td className="resource-path">{relativeTarget(p,binding.workspace)}</td><td>保护项</td></tr>)}</tbody></table></div><footer className="runtime-footnote">{data.effective&&connection.live?'当前绑定与工具放行均已核验。':'以上为已保存策略；当前未核验为有效运行权限。'}具体操作结果请查看文件证据。</footer></div>}
    </div>
    <div className="runtime-observation"><span>{connection.fresh?`最近核验 ${clock(e.checked_at)} · 每 3 秒刷新`:'观测不可用 · 当前在线状态未确认'}</span><button className="text-action" onClick={onDetails}>连接详情 ↗</button></div>
  </section>;
}
