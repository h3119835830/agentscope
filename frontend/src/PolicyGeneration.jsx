import React,{useCallback,useEffect,useRef,useState} from 'react';
import PolicyInputForm from './PolicyInputForm.jsx';
import GenerationResults,{GenerationDialog,GenerationStatus} from './GenerationResults.jsx';
import {sourceName,time} from './generationPresentation.js';

function GenerationInput({tasks,post,busy,action,onCreate}){
 const [repo,setRepo]=useState(''),[ref,setRef]=useState('main'),[extra,setExtra]=useState(''),[mode,setMode]=useState('github'),[includeInstructions,setIncludeInstructions]=useState(true);
 return <div className="generation-input"><div className="segmented"><button className={mode==='github'?'sel':''} onClick={()=>setMode('github')}>GitHub 文档</button><button className={mode==='manual'?'sel':''} onClick={()=>setMode('manual')}>输入策略语句</button></div>
  {mode==='github'?<div className="history-form"><p className="field-note">填写来源后自动采集、抽取、完整性二审并生成产物，完成后审核本次结果。</p><div className="history-fields"><label>GitHub 仓库<input value={repo} onChange={e=>setRepo(e.target.value)} placeholder="https://github.com/owner/repository"/></label><label>分支 / 标签 / commit<input value={ref} onChange={e=>setRef(e.target.value)}/></label><label>额外读取的仓库文件（每行一个，可选）<textarea rows="2" value={extra} onChange={e=>setExtra(e.target.value)} placeholder={'SECURITY.md\ndocs/security-policy.md'}/></label></div><label className="inline-check"><input type="checkbox" checked={includeInstructions} onChange={e=>setIncludeInstructions(e.target.checked)}/>同时采集仓库中的 AGENTS.md / CLAUDE.md</label><button className="button primary" disabled={busy||!repo.trim()||!ref.trim()} onClick={()=>action(()=>onCreate({repo_url:repo.trim(),ref:ref.trim(),include_instruction_files:includeInstructions,additional_paths:extra.split(/[\n,]/).map(x=>x.trim()).filter(Boolean),request_key:crypto.randomUUID()}))}>开始生成策略</button><p className="field-note">路径相对于仓库根目录。勾选后自动读取 AGENTS.md / CLAUDE.md；README.md 等文件需在上方另行指定。</p></div>:<PolicyInputForm tasks={tasks} post={post} busy={busy} action={action} onSaved={result=>onCreate({statement_version_id:result.id,request_key:crypto.randomUUID()})}/>}
 </div>;
}

export default function PolicyGeneration({api,post,tasks,busy,action,notify,runId,onSelectRun,onShowRecord,onMissingRun,emptyNotice,initialStatementId,onConsumed}){
 const [run,setRun]=useState(null),[inputOpen,setInputOpen]=useState(false);
 const sequence=useRef(0);
 const load=useCallback(async()=>{if(!runId)return;const n=++sequence.current;try{const value=await api('/api/history/generations/'+runId);if(n===sequence.current)setRun(value)}catch(e){if(n!==sequence.current)return;if(e.message==='生成批次不存在')onMissingRun(runId);else throw e}},[api,runId,onMissingRun]);
 useEffect(()=>{setRun(null);if(!runId)return;load().catch(e=>notify(e.message));const timer=setInterval(()=>load().catch(()=>{}),4000);return()=>{sequence.current++;clearInterval(timer)}},[load,notify,runId]);
 const create=async body=>{const result=await post('/api/history/generations',body);setInputOpen(false);onSelectRun(result.id);notify('已开始生成，本次结果会显示在下方')};
 useEffect(()=>{if(initialStatementId){onConsumed();action(()=>create({statement_version_id:initialStatementId,request_key:crypto.randomUUID()}))}},[initialStatementId]);
 return <div className="policy-generation"><div className="panel-head"><div><h2>本次生成与审核</h2><p className="field-note">发起生成并审核本次策略；历史结果在“生成记录”中查看。</p></div>{runId&&<button className="button primary" onClick={()=>setInputOpen(true)}>新建生成</button>}</div>
  {!runId&&<section className="panel history-form">{emptyNotice&&<p className="field-note" role="status">{emptyNotice}</p>}<GenerationInput tasks={tasks} post={post} busy={busy} action={action} onCreate={create}/></section>}
  {runId&&<section className="panel generation-summary"><div className="panel-head"><div><b>{run?sourceName(run):'正在读取本次生成记录'}</b>{run?.source?.commit&&!run.source.repository?.startsWith('manual/')&&<small>固定 commit：{run.source.commit}</small>}<small>{run&&time(run.created_at)}</small></div><button className="button ghost" onClick={()=>onShowRecord(runId)}>查看生成记录</button></div>{run&&<p><GenerationStatus value={run.status}/> {['queued','running'].includes(run.status)?'策略正在生成，结果会逐条出现。':'本次结果见下方；过程与诊断可在生成记录中查看。'}</p>}</section>}
  {runId&&run&&<GenerationResults key={runId} runId={runId} api={api} post={post} busy={busy} action={action} notify={notify} onReviewed={load}/>}
  {inputOpen&&<GenerationDialog title="新建生成" onClose={()=>setInputOpen(false)}><GenerationInput tasks={tasks} post={post} busy={busy} action={action} onCreate={create}/></GenerationDialog>}
 </div>;
}
