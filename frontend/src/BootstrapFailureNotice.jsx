import React from 'react';
import './bootstrapFailure.css';

export function bootstrapFailureSummary(failure={}){
 if(typeof failure.summary==='string'&&failure.summary.trim())return failure.summary;
 if(failure.code==='engine_pattern_limit_exceeded')return '保护目标路径超过执行引擎长度上限，需要按已登记的短路径重新准备候选。';
 if(failure.code==='source_read_receipt_missing')return '生成策略引用了尚未核验读取的文件，需要补齐来源证据后重新生成。';
 if(failure.code==='validation_budget_exhausted')return '本轮候选校验次数已用尽，尚未生成通过校验的策略。';
 return '启动策略尚未通过服务端校验，没有可确认加载的候选。';
}
export function bootstrapDiagnosticText(diagnostic){
 if(typeof diagnostic==='string')return diagnostic;
 if(diagnostic?.code==='engine_pattern_limit_exceeded'&&Number.isInteger(diagnostic.max_utf8_bytes))return `执行引擎单个路径模式最多 ${diagnostic.max_utf8_bytes} UTF-8 字节。`;
 return '';
}
// Presentation only. Recovery eligibility and callbacks must come from the owning controller.
export default function BootstrapFailureNotice({failure={},candidateId,recoveryReady=false,progressTaskId,progressStatus,onViewProgress,canViewCandidate=false,canRegenerate=false,onViewCandidate,onRegenerate,busy=false,blockedReason}){
 const diagnostics=[failure.diagnostic,...(Array.isArray(failure.diagnostics)?failure.diagnostics:[]),failure.error].map(bootstrapDiagnosticText).filter(value=>value.trim());
 return <section className="bootstrap-failure" aria-label="启动策略失败与恢复"><div className="bootstrap-failure-line"><span className="record-tag">原生成失败</span>{candidateId&&recoveryReady&&<span className="record-tag recovery-ready">恢复候选待确认</span>}{progressTaskId&&<span className="record-tag">{({generating:"恢复候选生成中",prepared:"恢复任务待生成",failed:"恢复任务生成失败"})[progressStatus]||"恢复任务进度"}</span>}<p role="alert">{bootstrapFailureSummary(failure)}</p><div className="actions">{progressTaskId&&onViewProgress&&<button className="button ghost tiny" onClick={()=>onViewProgress(progressTaskId)}>查看恢复进度</button>}{candidateId&&canViewCandidate&&onViewCandidate&&<button className="button ghost tiny" disabled={busy} onClick={()=>onViewCandidate(candidateId)}>查看恢复候选</button>}{canRegenerate&&onRegenerate&&<button className="button ghost tiny" disabled={busy} onClick={onRegenerate}>重新生成</button>}</div></div><details><summary>失败详情</summary>{candidateId&&recoveryReady&&<p>恢复任务：{candidateId} · 候选待人工确认</p>}{progressTaskId&&<p>恢复任务：{progressTaskId} · 状态以该任务记录为准</p>}{failure.job_id&&<p>失败作业：{failure.job_id}</p>}{diagnostics.map((value,i)=><p className="bootstrap-failure-diagnostic" key={i}>{value}</p>)}{Array.isArray(failure.targets)&&failure.targets.length>0&&<ul>{failure.targets.map((target,i)=><li key={target.path||i}>{target.path} · {target.utf8_bytes??'未记录'} 字节{failure.max_utf8_bytes?`（上限 ${failure.max_utf8_bytes}）`:''}</li>)}</ul>}{!diagnostics.length&&!failure.targets?.length&&<p>未保存更具体的失败诊断。</p>}<p>原失败记录保留；重新生成不表示候选已确认或策略已加载。</p></details>{blockedReason&&<p className="bootstrap-failure-blocked">{blockedReason}</p>}</section>;
}
