import React from 'react';
export default function PolicyContextEvidence({usage}){
 if(!usage)return null;
 return <details className="policy-context-evidence"><summary>{usage.file_count?'本次参考 · '+usage.file_count+' 个文件':'本次依据 · 未读取正文'}</summary>
 {!usage.file_count&&<p>仅依据你的需求、系统约束和已发布模板；没有把目录浏览当作正文读取。</p>}
 {usage.sources?.map((source,i)=><div key={i}><strong>{source.workspace}</strong><ul>{source.paths.map(path=><li key={path}>{path}</li>)}</ul></div>)}
 {!!usage.activity?.length&&<ol>{usage.activity.map((event,i)=><li key={i}>{event.tool==='list_directory'?'查看目录':'读取正文'} · {event.workspace}{event.path?' / '+event.path:''}{event.paths?' / '+event.paths.join('、'):''} · {event.status==='denied'?'已拒绝':event.tool==='list_directory'?'已查看':'已读取'}</li>)}</ol>}
 <p>这些是本次生成的资料记录；提交和应用前仍会核对文件与策略是否变化。</p>
 </details>;
}
