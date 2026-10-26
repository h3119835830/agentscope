import React from 'react';
import {activitySummary,referenceFiles} from './policyAssistantResponse.mjs';
export default function PolicyContextEvidence({usage}){
 if(!usage)return null;
 const provided=usage.provided_files||[],count=referenceFiles(usage).length;
 return <details className="policy-context-evidence"><summary>{count?'本次参考 · '+count+' 个文件':'本次依据 · 未读取正文'}</summary>
 {!usage.file_count&&<p>{provided.length?'已将所附文本正文提供给助手，未读取实例工作区正文。':'仅依据你的需求、系统约束和已发布模板；没有把目录浏览当作正文读取。'}</p>}
 {!!provided.length&&<div><strong>上传的参考文件</strong><ul>{provided.map((f,i)=><li key={i}>{f.name} · {f.characters} 字符</li>)}</ul></div>}
 {usage.sources?.map((source,i)=><div key={i}><strong>{source.workspace}</strong><ul>{source.paths.map(path=><li key={path}>{path}</li>)}</ul></div>)}
 {!!usage.activity?.length&&<details className="assistant-tool-history"><summary>资料与验证过程 · {usage.activity.length} 步</summary><ol>{usage.activity.map((event,i)=>{const a=activitySummary(event);return <li key={i}>{a.label}{a.location?' · '+a.location:''} · {event.status==='denied'?'已拒绝':a.status}</li>;})}</ol></details>}
 <p>这些是本次生成的资料记录；提交和应用前仍会核对已登记文件与策略是否变化。上传文本作为参考，不改变读取权限。</p>
 </details>;
}
