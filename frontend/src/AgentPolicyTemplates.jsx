import React,{useState} from 'react';
import catalogue from './rq1-agent-templates.json';
import PolicyTemplateDetail from './PolicyTemplateDetail.jsx';
import {operationLabel,effectLabel} from './policyRecordPresentation.mjs';
export default function AgentPolicyTemplates({agents=[],targetId='',onHandoff}){
 const [query,setQuery]=useState(''),[category,setCategory]=useState(''),[selected,setSelected]=useState(null);
 const rows=catalogue.templates.filter(t=>(!category||t.category===category)&&(t.name+' '+t.summary).toLowerCase().includes(query.toLowerCase()));
 return <section className="policy-template-records" aria-label="策略与模板记录"><div className="policy-record-toolbar"><label className="policy-search"><span>搜索</span><input type="search" aria-label="搜索策略模板" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索策略名称或用途"/></label><label>分类<select aria-label="筛选模板分类" value={category} onChange={e=>setCategory(e.target.value)}><option value="">全部分类</option>{[...new Set(catalogue.templates.map(t=>t.category))].map(c=><option key={c}>{c}</option>)}</select></label><span className="record-count">{rows.length} 条记录</span></div>
 <div className="policy-table-shell"><div className="table-scroll"><table className="policy-structured-table" aria-label="策略模板记录"><thead><tr><th>策略名称</th><th>分类</th><th>匹配对象 / 操作</th><th>处置方式</th><th>适用范围</th><th>操作</th></tr></thead><tbody>{rows.map(t=><tr key={t.id}><td><button className="policy-record-title" onClick={()=>setSelected(t)}>{t.name}</button><p>{t.summary}</p></td><td>{t.category}</td><td><span>{t.kind==='file'?'指定文件':t.kind==='workflow'?'文件变更 → Git 提交':'Git 命令参数'}</span><small>{operationLabel(t.operation)}</small></td><td><span className={'effect-pill effect-'+t.effect}>{effectLabel(t.effect)}</span></td><td><span className="policy-scope-dot">Agent 专属</span><small>{t.runtime_note?'待运行时适配':'使用前配置参数'}</small></td><td><button className="button tiny ghost" aria-label={'配置 '+t.name} onClick={()=>setSelected(t)}>详情 / 配置</button></td></tr>)}{!rows.length&&<tr><td colSpan={6} className="task-empty">没有匹配的模板，请调整筛选条件。</td></tr>}</tbody></table></div><div className="policy-table-footer">共 {rows.length} 条 · 模板尚未配置到 Agent</div></div>
 {selected&&<PolicyTemplateDetail key={selected.id} template={selected} agents={agents} targetId={targetId} onClose={()=>setSelected(null)} onHandoff={onHandoff}/>}
 </section>;
}
