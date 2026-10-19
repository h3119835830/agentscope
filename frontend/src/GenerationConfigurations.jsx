import React from 'react';

const operations={open:'打开文件',write:'修改文件',unlink:'删除文件',exec:'启动程序',connect:'连接网络'};
const effects={block:'阻止并反馈',notify:'记录并提醒',kill:'终止命中进程'};
const statuses={draft:'待提交审批',pending:'待审批',approved:'已批准 · 待应用',applied:'已应用',rejected:'已拒绝',stale:'需重新校验',invalid:'校验未通过',failed:'应用失败',applying:'正在应用',unavailable:'审批状态暂不可用'};
function parameter(value,type){
 if(type==='operations')return (Array.isArray(value)?value:String(value).split(',')).map(v=>operations[v]||v).join('、');
 if(type==='effect')return effects[value]||value;
 return Array.isArray(value)?value.join('、'):String(value);
}
function approval(row){
 const status=row.execution_support?.applicable===false?'暂不支持 · 仅参数草案':statuses[row.approval_status]||'审批状态暂不可用';
 return row.approval_operation==='disable'?(row.approval_status==='applied'?'已停用':'停用 · '+status):status;
}
export default function GenerationConfigurations({generation}){
 if(!generation.items?.length)return null;
 const snapshots=generation.configuration_snapshots;
 return <section className="assistant-generated-results" aria-label="本轮生成的策略配置"><p className="assistant-snapshot-note">生成时配置 · 审批状态对应此配置版本</p>
 {!snapshots?.length?<p>此轮配置快照暂不可用。</p>:snapshots.map(row=>row.unavailable?<p key={row.id}>此项配置快照暂不可用。</p>:<article className="assistant-generated-record" key={row.id}>
 <header><div><span className="assistant-snapshot-label">实际策略名称</span><strong>{row.name}</strong></div><span className="assistant-generation-status" aria-label="审批状态">{approval(row)}</span></header>
 <dl><div><dt>选用模板</dt><dd>{row.template.name}<span className="assistant-template-version">v{row.template.version}</span></dd></div>
 <div><dt>填写的参数</dt><dd>{row.template.parameters.filter(p=>Object.hasOwn(row.parameters,p.key)).length?<dl className="assistant-generated-parameters">{row.template.parameters.filter(p=>Object.hasOwn(row.parameters,p.key)).map(p=><div key={p.key}><dt>{p.label}</dt><dd>{parameter(row.parameters[p.key],p.type)}</dd></div>)}</dl>:'此模板无需填写参数'}</dd></div>
 <div><dt>作用范围</dt><dd>{row.scope.label}</dd></div></dl>
 </article>)}
 </section>;
}
