import React,{useEffect,useRef,useState} from 'react';
import {sceneBusy,sceneUsable,sceneInput} from './policyScene.mjs';

export default function AgentPolicyScene({target,context,api,post,scene,onScene,onAdopt,disabled}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[open,setOpen]=useState(false);
 const alive=useRef(true),request=useRef(null),epoch=useRef(0);
 const base='/api/agent-instances/'+encodeURIComponent(target.id)+'/policy-scenes';
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
 useEffect(()=>{let active=true;const version=epoch.current;if(context?.ready)api(base+'?session_id='+encodeURIComponent(context.session_id)).then(value=>{if(active&&version===epoch.current){onScene(value.scene);setOpen(Boolean(value.scene));}}).catch(()=>{if(active&&version===epoch.current)setError('暂时无法读取场景记录，请重试。');});return()=>{active=false;};},[api,base,context?.session_id,context?.context_hash]);
 useEffect(()=>{if(!sceneBusy(scene))return;let active=true,timer;async function poll(){try{const value=await api(base+'/'+scene.id);if(active)onScene(value);}catch{if(active)setError('场景状态暂时读取失败，请重新读取。');}finally{if(active)timer=setTimeout(poll,2500);}}timer=setTimeout(poll,2500);return()=>{active=false;clearTimeout(timer);};},[api,base,scene?.id,scene?.status]);
 async function read(){if(busy||disabled)return;epoch.current++;setBusy(true);setError('');setOpen(true);try{const selection=JSON.stringify([context?.session_id,context?.context_hash]);if(request.current?.selection!==selection)request.current={selection,key:crypto.randomUUID()};const value=await post(base,sceneInput(context,request.current.key));if(alive.current){onScene(value);request.current=null;}}catch{if(alive.current)setError('读取未能开始，请刷新 Agent 连接并检查项目文本后重试。');}finally{if(alive.current)setBusy(false);}}
 async function adopt(item){if(busy)return;setError('');try{const fresh=await api(base+'/'+scene.id);if(!alive.current)return;onScene(fresh);if(!sceneUsable(fresh))throw Error();onAdopt(item.policy);setOpen(false);}catch{if(alive.current)setError('场景已变化或暂时不可用，请重新读取后选择建议。');}}
 const reading=busy||sceneBusy(scene),usable=sceneUsable(scene),recommendations=scene?.recommendations||[];
 return <section className="assistant-scene" aria-label="工作区场景">
  <div className="assistant-scene-bar"><div><span className="assistant-scene-icon">⌕</span><strong>{scene?'工作区场景':'先了解当前工作场景'}</strong><span role="status">{reading?'正在读取项目文本…':scene?(usable?'已读取 '+scene.file_count+' 个文件':scene.message||'读取尚未完成'):'读取任务说明与项目文件，提供有依据的策略建议'}</span></div><div>{scene&&<button className="assistant-text-button" aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'收起':'查看场景'}</button>}<button type="button" className="button tiny ghost" disabled={!context?.ready||reading||disabled} onClick={read}>{reading?'读取中…':scene?'重新读取':'读取场景'}</button></div></div>
  {error&&<p className="inline-notice warning" role="alert">{error}</p>}
  {open&&scene&&<div className="assistant-scene-body">
   {scene.summary&&<p className="assistant-scene-summary">{scene.summary}</p>}
   {usable&&!recommendations.length&&<p>尚无明确的策略建议，请补充任务目标后重新读取。</p>}
   {!!recommendations.length&&<div className="assistant-scene-list" role="list" aria-label="场景策略建议">{recommendations.map(item=><article role="listitem" key={item.id}><div><strong>{item.title}</strong><p>{item.policy}</p><details><summary>文件依据 · {[...new Set(item.evidence.map(e=>e.relative_path))].join('、')}</summary>{item.evidence.map((e,i)=><blockquote key={i}><cite>{e.relative_path}</cite><p>{e.quote}</p></blockquote>)}</details></div><button className="button tiny ghost" disabled={!usable||disabled||reading} onClick={()=>adopt(item)}>采用建议</button></article>)}</div>}
   {!!scene.sources?.length&&<details className="assistant-scene-files"><summary>已读取文件 · {scene.file_count}</summary><ul>{scene.sources.map(s=><li key={s.relative_path}>{s.relative_path}</li>)}</ul></details>}
   <p className="assistant-scene-note">建议供你选择；采用后仍需起草并提交审批。</p>
  </div>}
 </section>;
}
