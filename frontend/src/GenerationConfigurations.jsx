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
 return <section className="assistant-generated-results" aria-label="本轮生成的策略配置">
 {!snapshots?.length?<p>此轮配置快照暂不可用。</p>:<div className="assistant-policy-table-scroll" tabIndex={0} role="region" aria-label="生成策略表格，可横向滚动"><table className="assistant-policy-table"><thead><tr><th>策略名称</th><th>匹配对象</th><th>操作与处置</th><th>审批状态</th><th>详情</th></tr></thead><tbody>{snapshots.map(row=>{
  if(row.unavailable)return <tr key={row.id}><td colSpan={5}>此项配置快照暂不可用。</td></tr>;
  const parameters=row.parameters||{},fields=row.template.parameters.filter(p=>Object.hasOwn(parameters,p.key)),subjects=fields.filter(p=>['path','endpoint'].includes(p.type)),targets=subjects.length?subjects:fields.filter(p=>['program','lines'].includes(p.type)),execution=row.execution||{};
  const ops=execution.effective_operations||parameters.operations||[],effect=execution.effect||parameters.effect;
  return <tr key={row.id}><td><strong>{row.name}</strong><small>{row.template.name} · v{row.template.version}</small></td>
   <td>{targets.length?targets.map(p=><span className="assistant-match-value" key={p.key}>{targets.length>1&&<small>{p.label}</small>}<code>{parameter(parameters[p.key],p.type)}</code></span>):'模板固定条件'}</td>
   <td>{ops.length?<span>{parameter(ops,'operations')}</span>:<span>操作未记录</span>}{row.template.fixed_fields&&<small><code>{Object.values(row.template.fixed_fields).join(' ')}</code></small>}<small>{effect?parameter(effect,'effect'):'处置未记录'}</small></td>
   <td><span className="assistant-generation-status" aria-label="审批状态">{approval(row)}</span></td>
   <td><details className="assistant-policy-detail"><summary>查看</summary><dl><div><dt>选用模板</dt><dd>{row.template.name} · v{row.template.version}</dd></div><div><dt>作用范围</dt><dd>{row.scope.label}</dd></div>
    {row.template.fixed_fields&&<div><dt>固定命令</dt><dd>{Object.values(row.template.fixed_fields).join(' ')}</dd></div>}
    {fields.map(p=><div key={p.key}><dt>{p.label}</dt><dd>{parameter(parameters[p.key],p.type)}</dd></div>)}
    {execution.reason&&<div><dt>匹配后反馈</dt><dd>{execution.reason}</dd></div>}
    {execution.coverage_warning&&<div><dt>覆盖范围</dt><dd>{execution.coverage_warning}</dd></div>}
   </dl></details></td></tr>;
 })}</tbody></table></div>}
 <p className="assistant-snapshot-note">展示生成时配置；审批状态对应此版本，后续编辑不会改写本轮记录。</p>
 </section>;
}
