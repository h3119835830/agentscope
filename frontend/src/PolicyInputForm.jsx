import React,{useState} from 'react';
const levels={semantic_only:'语义规则',content:'内容规则',per_event:'单事件规则',cross_event:'跨事件规则',not_applicable:'不适用'};
const scopes={self_contained:'通用',project:'项目 / 仓库',task:'任务',not_applicable:'不适用'};
export default function PolicyInputForm({record,tasks,post,busy,action,onSaved,onCancel}){
 const initialLevel=(record?.category||'semantic').replaceAll('-','_');
 const [text,setText]=useState(record?.text||''),[zh,setZh]=useState(''),[en,setEn]=useState('');
 const [level,setLevel]=useState(initialLevel==='semantic'?'semantic_only':initialLevel),[scope,setScope]=useState((record?.context_scope||'self-contained').replaceAll('-','_'));
 const [task,setTask]=useState('');
 const save=()=>action(async()=>{
  const body={enforcement_level:level,context_requirement:scope,text_zh:zh,text_en:en};
  const result=await post(record?'/api/history/records/'+record.id+'/statement-input':'/api/history/inputs',{...body,...(!record?{text}:{}),task_id:task||null});
  await onSaved(result);
 });
 return <section className="panel history-form policy-input-form"><div className="panel-head"><div><h2>{record?(record.source_kind==='rq1_corpus'?'准备 RQ1 转换输入':'准备策略转换输入'):'输入策略语句'}</h2><p>原句是转换输入。保存为待审版本，审核通过后生成伪代码和 DSL 候选。</p></div>{onCancel&&<button className="button ghost" onClick={onCancel}>取消</button>}</div>
 <label>策略语句（自然语言）<textarea rows="4" value={text} readOnly={!!record} onChange={e=>setText(e.target.value)} placeholder="例如：禁止修改本任务的 tests 目录，但允许读取和运行测试。"/></label>
 {record&&<p className="field-note">{record.source_kind==='rq1_corpus'?<>固定来源：{record.source_repo} · {record.source_path}。提交时重新核验源文件 hash 和原文行。</>:<>以本条手工策略原句登记不可变输入快照。</>}不自动沿用目录审批。</p>}
 <div className="strategy-editor-grid"><label>执行层级<select value={level} onChange={e=>setLevel(e.target.value)}>{Object.entries(levels).map(([value,title])=><option key={value} value={value}>{title}</option>)}</select></label><label>上下文范围<select value={scope} onChange={e=>setScope(e.target.value)}>{Object.entries(scopes).map(([value,title])=><option key={value} value={value}>{title}</option>)}</select></label></div>
 {(!record||record.source_kind==='manual')&&<label>关联任务（需要具体路径时选择）<select value={task} onChange={e=>setTask(e.target.value)}><option value="">暂不关联，仅登记策略</option>{tasks.filter(t=>['prepared','policy_review','approved'].includes(t.status)).map(t=><option key={t.id} value={t.id}>{t.name} · {t.id.slice(0,12)}</option>)}</select></label>}
 <details className="input-translations"><summary>补充翻译（可选）</summary><div className="strategy-editor-grid"><label>中文译文<textarea rows="2" value={zh} onChange={e=>setZh(e.target.value)}/></label><label>英文译文<textarea rows="2" value={en} onChange={e=>setEn(e.target.value)}/></label></div></details>
 <p className="field-note">语义或内容要求保留为指导项。可执行规则还需明确操作对象、具体范围和权限，编译并批准后才会进入 ActPlane。</p>
 <button className="button primary" disabled={busy||text.trim().length<5} onClick={save}>保存待审语句版本</button>
 </section>;
}
