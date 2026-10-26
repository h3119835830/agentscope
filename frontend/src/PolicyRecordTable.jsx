import React from 'react';
import {policyRecord,policyRecordFields} from './policyRecords.mjs';

export function PolicyRecordCells({record:r,name,scope}){
 return <><td>{name||<strong>{r.name}</strong>}</td><td>{scope||r.scope}</td><td><span className="policy-record-value" title={r.target}>{r.target}</span></td><td>{r.operation}</td><td><span className="policy-record-value" title={r.conditions}>{r.conditions}</span></td><td>{r.effect}</td><td>{r.status}</td></>;
}
export default function PolicyRecordTable({rows,label='策略记录',actions,detail=false}){
 return <div className="policy-record-scroll" tabIndex={0} role="region" aria-label={label+'，可横向滚动'}><table className="policy-record-table" aria-label={label}><thead><tr>{policyRecordFields.map(field=><th key={field}>{field}</th>)}{actions&&<th>操作</th>}</tr></thead><tbody>{rows.map(row=>{const r=policyRecord(row);return <tr key={row.id+':'+row.revision}><PolicyRecordCells record={r} name={<><strong>{r.name}</strong>{detail&&!row.unavailable&&<details><summary>查看</summary><dl><dt>选用模板</dt><dd>{r.template.name} · v{r.template.version}</dd>{r.fields.map(p=><React.Fragment key={p.key}><dt>{p.label}</dt><dd>{String(r.parameters[p.key])}</dd></React.Fragment>)}{r.execution.reason&&<><dt>匹配后反馈</dt><dd>{r.execution.reason}</dd></>}{r.execution.coverage_warning&&<><dt>覆盖范围</dt><dd>{r.execution.coverage_warning}</dd></>}</dl></details>}</>}/>{actions&&<td>{actions(row)}</td>}</tr>;})}</tbody></table></div>;
}
