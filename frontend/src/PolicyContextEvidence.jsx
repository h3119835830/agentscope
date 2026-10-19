import React from 'react';
export default function PolicyContextEvidence({usage}){
 if(!usage)return null;
 const provided=usage.provided_files||[],count=(usage.file_count||0)+provided.length;
 return <details className="policy-context-evidence"><summary>{count?'本次参考 · '+count+' 个文件':'本次依据 · 未读取正文'}</summary>
 {!usage.file_count&&<p>{provided.length?'已将所附文本正文提供给助手，未读取实例工作区正文。':'仅依据你的需求、系统约束和已发布模板；没有把目录浏览当作正文读取。'}</p>}
 {!!provided.length&&<div><strong>上传的参考文件</strong><ul>{provided.map((f,i)=><li key={i}>{f.name} · {f.characters} 字符</li>)}</ul></div>}
 {usage.sources?.map((source,i)=><div key={i}><strong>{source.workspace}</strong><ul>{source.paths.map(path=><li key={path}>{path}</li>)}</ul></div>)}
 {!!usage.activity?.length&&<ol>{usage.activity.map((event,i)=><li key={i}>{event.tool==='list_directory'?'查看目录':'读取正文'} · {event.workspace}{event.path?' / '+event.path:''}{event.paths?' / '+event.paths.join('、'):''} · {event.status==='denied'?'已拒绝':event.tool==='list_directory'?'已查看':'已读取'}</li>)}</ol>}
 <p>这些是本次生成的资料记录；提交和应用前仍会核对已登记文件与策略是否变化。上传文本作为参考，不改变读取权限。</p>
 </details>;
}
