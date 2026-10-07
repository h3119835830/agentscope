import React,{useEffect,useRef,useState} from 'react';
import {latestRequest} from './consoleState.mjs';
import {sceneReadPath,sceneReadMatches,validateSceneRead,canUseSceneDraft,sceneCreateBody,sceneReadLabel,sceneErrorMessage,sceneEvidence,sceneStorageKey,sceneStoredValue,restoreSceneContext} from './workspaceScene.mjs';
import WorkspaceSceneSummary from './WorkspaceSceneSummary.jsx';
import './workspaceScene.css';

export default function WorkspaceSceneRead({workspaceId,agentId,manifestHash,sourceGeneration,canRead,api,post,onUseDraft,onOpenTask,onRefresh,busy=false}){
 const [read,setRead]=useState(null),[input,setInput]=useState(null),[supplement,setSupplement]=useState(''),[editing,setEditing]=useState(false);
 const [starting,setStarting]=useState(false),[restoring,setRestoring]=useState(false),[creating,setCreating]=useState(false),[error,setError]=useState(''),[pollError,setPollError]=useState(''),[note,setNote]=useState(''),[retry,setRetry]=useState(0);
 const gate=useRef(latestRequest()),ticket=useRef(0),previousManifest=useRef(manifestHash);
 const context={workspaceId,agentId,manifestHash,sourceGeneration,supplement};
 const current=sceneReadMatches(read,input,context),ready=canUseSceneDraft(read,input,context);
 const pending=current&&['queued','running'].includes(read.status),needsGoal=current&&read.status==='completed'&&read.draft?.state==='needs_clarification';
 const adopted=current&&!!read.task_id;
 const disabled=!canRead||busy||starting||restoring||pending||creating;

 function save(expected,readId=null){const snapshot={...expected,manifestHash:expected.manifestHash||previousManifest.current};if(!snapshot.workspaceId||!snapshot.manifestHash)return;try{localStorage.setItem(sceneStorageKey(snapshot),sceneStoredValue(snapshot,readId));}catch{}}

 useEffect(()=>()=>gate.current.invalidate(),[]);
 useEffect(()=>{
  const sequence=gate.current.begin();ticket.current=sequence;setRead(null);setInput(null);setStarting(false);setRestoring(false);setError('');setPollError('');
  if(!workspaceId||!manifestHash)return()=>gate.current.invalidate();
  let saved=null;try{saved=restoreSceneContext(localStorage.getItem(sceneStorageKey(context)),context);}catch{}
  if(saved){
   setSupplement(saved.context.supplement);setEditing(!!saved.context.supplement);
   if(saved.stale){setNote('工作区文件或连接实例已变化，请重新读取场景。已填写的补充会保留。');save(saved.context);}
   else if(saved.read_id){
    setRestoring(true);setInput(saved.context);
    api(sceneReadPath(workspaceId,saved.read_id)).then(result=>{if(gate.current.current(sequence))accept(result,saved.context);}).catch(e=>{if(gate.current.current(sequence))setError(sceneErrorMessage(e.message));}).finally(()=>{if(gate.current.current(sequence))setRestoring(false);});
   }
  }else if(previousManifest.current&&previousManifest.current!==manifestHash){setNote('工作区文件清单已更新，请重新读取场景。已填写的补充会保留。');save(context);}
  previousManifest.current=manifestHash;
  return()=>gate.current.invalidate();
 },[workspaceId,agentId,manifestHash,sourceGeneration,api]);

 function accept(value,expected){
  const result=validateSceneRead(value,expected);setRead(result);
  if(result.status==='completed'&&result.draft?.state==='needs_clarification')setEditing(true);
  if(result.status==='completed'&&result.draft?.state==='ready')setEditing(false);
 }
 useEffect(()=>{
  if(!current||!pending||pollError)return;
  let active=true;const sequence=ticket.current;
  const timer=setTimeout(async()=>{
   try{const result=await api(sceneReadPath(workspaceId,read.id));if(active&&gate.current.current(sequence))accept(result,input);}
   catch(e){if(active&&gate.current.current(sequence))setPollError(sceneErrorMessage(e.message));}
  },1200);
  return()=>{active=false;clearTimeout(timer);};
 },[read,input,current,pending,pollError,retry,workspaceId,api]);

 async function analyse(event){
  event?.preventDefault();if(disabled)return;
  const expected={...context,supplement:supplement.trim()},sequence=gate.current.begin();ticket.current=sequence;
  setRead(null);setInput(expected);setStarting(true);setError('');setPollError('');setNote('');save(expected);
  try{
   const result=await post(sceneReadPath(workspaceId),{expected_manifest_hash:manifestHash,supplement:expected.supplement});
   if(gate.current.current(sequence)){validateSceneRead(result,expected);save(expected,result.id);accept(result,expected);}
  }catch(e){if(gate.current.current(sequence))setError(sceneErrorMessage(e.message));}
  finally{if(gate.current.current(sequence))setStarting(false);}
 }
 function changeSupplement(value){
  gate.current.invalidate();setSupplement(value);setRead(null);setInput(null);setStarting(false);setRestoring(false);setError('');setPollError('');save({...context,supplement:value});
  setNote('补充已修改，请重新读取场景后再生成策略。');
 }
 async function useDraft(){
  if(!ready||disabled)return;setCreating(true);setError('');
  try{await onUseDraft(sceneCreateBody(read,input,context));}
  catch(e){gate.current.invalidate();setRead(null);setInput(null);save(context);setError(`${sceneErrorMessage(e.message)}。请重新读取场景后再生成策略。`);}
  finally{setCreating(false);}
 }
 const serverError=current&&['failed','interrupted'].includes(read.status)?sceneErrorMessage(read.error||'scene_read_failed'):'';
 const draft=current&&read.status==='completed'?read.draft:null;
 const evidence=draft?sceneEvidence(draft,input?.supplement):[];
 const showSupplement=editing||needsGoal;
 return <section className="panel task-section scene-read" aria-label="读取场景并识别任务">
  <div className="task-section-heading"><h2>读取场景</h2></div>
  <p className="scene-description">让 Agent 读取工作区文件，识别已有任务和约束，并自动生成名称。读取完成后再生成策略。</p>
  {(starting||restoring||current)&&<div className="scene-status" role="status" aria-live="polite"><span className="tag">{restoring?'正在恢复读取记录':starting?'正在请求场景读取':pollError?'读取状态待检查':sceneReadLabel(read)}</span><p>{pending?'正在读取文件和整理来源证据。':''}</p></div>}
  {(error||serverError)&&<p className="inline-notice warning scene-error" role="alert">{error||serverError} {onRefresh&&<button type="button" className="button ghost tiny" onClick={onRefresh}>刷新文件清单</button>}</p>}
  {pollError&&<p className="inline-notice warning scene-error" role="alert">暂时无法检查读取状态：{pollError} <button type="button" className="button ghost tiny" onClick={()=>{setPollError('');setRetry(v=>v+1);}}>继续检查</button></p>}
  {note&&<p className="field-note" role="status">{note}</p>}
  {draft&&<WorkspaceSceneSummary name={draft.name} goal={draft.goal} constraints={draft.constraints} evidence={evidence}/>}
  {needsGoal&&<p className="field-note">{draft.clarification||'场景文件里没有明确的本次目标，请补充一句希望完成什么。'}</p>}
  <form onSubmit={analyse}>
   {showSupplement&&<div className="scene-supplement"><label>补充本次目标<textarea aria-label="补充本次目标" rows={3} maxLength={8000} value={supplement} onChange={e=>changeSupplement(e.target.value)} placeholder="例如：修复支付验证问题，保留现有测试。" disabled={creating}/></label><p className="field-note">只补充文件中没有说明的目标，无需重复粘贴场景内容。</p></div>}
   <div className="scene-actions">
    {ready&&<button type="button" className="button primary" disabled={disabled} onClick={useDraft}>{creating?'正在生成…':'使用此任务生成策略'}</button>}
    {adopted&&onOpenTask&&<button type="button" className="button primary" onClick={()=>onOpenTask(read.task_id)}>查看已创建任务</button>}
    {!ready&&<button type="submit" className={'button '+(adopted?'ghost':'primary')} disabled={disabled||(needsGoal&&supplement.trim().length<3)}>{restoring?'正在恢复读取…':starting||pending?'Agent 正在读取…':adopted?'读取新场景':showSupplement&&supplement.trim()?'按补充重新识别':'让 Agent 读取场景'}</button>}
    {ready&&<><button type="button" className="button ghost tiny" disabled={disabled} onClick={()=>setEditing(v=>!v)}>{editing?'收起补充':'补充或修改目标'}</button><button type="button" className="button ghost tiny" disabled={disabled} onClick={analyse}>重新读取</button></>}
   </div>
  </form>
  <p className="field-note">{ready?'继续后会生成策略供你确认，确认前不会启动任务执行。':'这一步只读取场景，不会启动任务执行。'}</p>
 </section>;
}
