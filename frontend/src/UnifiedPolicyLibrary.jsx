import React,{useEffect,useRef,useState} from 'react';
import {Editor as ExistingEditor} from './SystemPolicyLibrary.jsx';
import TemplateConfigurationDialog from './TemplateConfigurationDialog.jsx';
import TemplateDefinitionDialog from './TemplateDefinitionDialog.jsx';
import PolicyLifecycleDialog from './PolicyLifecycleDialog.jsx';
import {PolicyDetail} from './ActPlanePolicies.jsx';
import {visibleAgentInstances} from './agentInstancePresentation.mjs';
import {effectLabel,operationLabel} from './policyRecordPresentation.mjs';
import {configurationAgentLabel,configurationRecordSummary,configurationRecordActions,configurationDisableSnapshot} from './policyConfigurationPresentation.mjs';
import './systemPolicyLibrary.css';
import './unifiedPolicyLibrary.css';

const CATALOG_COLUMNS=[
 {label:'策略模板',key:'name',width:200,min:160,max:600},
 {label:'说明',key:'description',width:300,min:180,max:1200},
 {label:'默认动作',key:'effect',width:108,min:108,max:320},
 {label:'子配置',key:'count',width:76,min:72,max:240},
 {label:'操作',key:'actions',width:152,min:152,max:500},
];

function Picker({catalog,onChoose,onClose}){
 const ref=useRef(null),[id,setId]=useState(catalog[0]?.id||'');
 useEffect(()=>{ref.current?.showModal();return()=>ref.current?.close();},[]);
 return <dialog ref={ref} className="spl-dialog upl-picker" aria-label="选择策略模板" onCancel={onClose}><header className="spl-editor-head"><h2>选择策略模板</h2><button aria-label="关闭" onClick={onClose}>×</button></header><div className="spl-editor-body"><label>策略模板<select aria-label="策略模板" value={id} onChange={e=>setId(e.target.value)}>{catalog.map(t=><option value={t.id} key={t.id}>{t.name}</option>)}</select></label><p className="spl-note">{catalog.find(t=>t.id===id)?.description||catalog.find(t=>t.id===id)?.summary}</p></div><footer className="spl-editor-footer"><button className="button ghost" onClick={onClose}>取消</button><button className="button primary" disabled={!id} onClick={()=>onChoose(catalog.find(t=>t.id===id))}>配置参数</button></footer></dialog>;
}

export default function UnifiedPolicyLibrary({api,post,agents=[],targetId='',onApprovals}){
 const [data,setData]=useState(null),[library,setLibrary]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [filter,setFilter]=useState('all'),[q,setQ]=useState(''),[category,setCategory]=useState(''),[scope,setScope]=useState(targetId||'all'),[collapsed,setCollapsed]=useState({}),[selected,setSelected]=useState(new Set());
 const [editing,setEditing]=useState(null),[legacyEditing,setLegacyEditing]=useState(null),[picker,setPicker]=useState(false),[action,setAction]=useState(null),[record,setRecord]=useState(null);
 const alive=useRef(false),seq=useRef(0),[coverageAck,setCoverageAck]=useState(false);
 const needsCoverage=!!action&&action.operation!=='archive'&&action.rows.some(i=>i.coverage_warning||i.config?.ops?.some(op=>['write','unlink'].includes(op)));
 const [capability,setCapability]=useState(null);
 const [columnWidths,setColumnWidths]=useState(()=>CATALOG_COLUMNS.map(c=>c.width)),[resizingColumn,setResizingColumn]=useState(null),columnDrag=useRef(null);
 const [templateEditing,setTemplateEditing]=useState(null);
 const resizeColumn=(index,width)=>setColumnWidths(previous=>previous.map((value,i)=>i===index?Math.max(CATALOG_COLUMNS[i].min,Math.min(CATALOG_COLUMNS[i].max,width)):value));
 function startColumnResize(e,index){
  if(e.button!==0)return;e.preventDefault();e.stopPropagation();e.currentTarget.focus();e.currentTarget.setPointerCapture(e.pointerId);
  columnDrag.current={pointerId:e.pointerId,index,startX:e.clientX,startWidth:columnWidths[index]};setResizingColumn(index);
 }
 function moveColumnResize(e,index){const drag=columnDrag.current;if(drag?.pointerId===e.pointerId&&drag.index===index)resizeColumn(index,drag.startWidth+e.clientX-drag.startX);}
 function endColumnResize(e){if(columnDrag.current?.pointerId!==e.pointerId)return;columnDrag.current=null;setResizingColumn(null);if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId);}
 function keyColumnResize(e,index){if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();resizeColumn(index,columnWidths[index]+(e.key==='ArrowRight'?1:-1)*(e.shiftKey?40:10));}
 const decorate=t=>({...t,description:data?.catalog.find(p=>p.id===t.id&&p.version===t.version)?.description||t.summary,requires_suffix:['suffix','filename','tail','flow'].includes(library?.catalog.find(p=>'SYS-'+p.id===t.id)?.mode)});
 async function refresh(){const n=++seq.current;try{const [d,l]=await Promise.all([api('/api/policy-templates'),api('/api/security/system/policy-library')]);if(alive.current&&n===seq.current){setData(d);setLibrary(l);setError('');setSelected(new Set());}}catch(e){if(alive.current&&n===seq.current){setError(e.message);setData(null);setLibrary(null);}}}
 useEffect(()=>{alive.current=true;refresh();api('/api/security/system/execution-capabilities').then(v=>{if(alive.current)setCapability(v);}).catch(()=>{});return()=>{alive.current=false;seq.current++;};},[api]);
 useEffect(()=>{setScope(targetId||'all');setSelected(new Set());},[targetId]);
 const catalog=data?.catalog||[],instances=visibleAgentInstances(agents).filter(a=>a.mode==='controlled');
 const scopeName=row=>row.scope==='workspace'?'历史局部配置（暂不支持）':row.scope_id==='system'?'所有 Agent':configurationAgentLabel(agents.find(a=>a.id===row.scope_id)||{id:row.scope_id,agent_type:row.agent_type},agents);
 const legacy=(library?.items||[]).filter(i=>!(data?.items||[]).some(c=>!c.legacy_system&&c.id===i.id)).map(i=>({...i,legacy:true,scope_id:'system',scope:'system',template_id:catalog.some(t=>t.id==='SYS-'+i.config?.template_id)?'SYS-'+i.config.template_id:'custom',can_submit:!i.validation_error,has_applied_document:!!i.applied,applied:!!i.applied&&!i.has_changes}));
 const items=[...legacy,...(data?.items||[]).filter(i=>!i.legacy_system)];
 const groups=[...catalog.filter(t=>!t.retired||items.some(i=>i.template_id===t.id)).sort((a,b)=>Number(b.id.startsWith('SYS-'))-Number(a.id.startsWith('SYS-'))),...(legacy.some(i=>i.template_id==='custom')?[{id:'custom',name:'自定义策略与导入 DSL',category:'自定义策略',summary:'保留原始文档和既有审批记录。',description:'查看已有自定义策略与导入的完整 DSL 文档。这些记录不属于供助手填参的已发布模板，编辑与提交仍保留原审批流程。',parameters:[],operation:'',effect:'',custom:true}]:[])];
 const query=q.trim().toLowerCase();
 const templateMatches=t=>!!query&&JSON.stringify([t.name,t.description||t.summary,t.category,t.parameters.map(p=>p.label)]).toLowerCase().includes(query);
 const rows=groups.map(t=>({template:t,children:items.filter(i=>i.template_id===t.id&&(scope==='all'||i.scope_id===scope)&&(!query||templateMatches(t)||JSON.stringify([i.name,i.parameters,i.config]).toLowerCase().includes(query)))})).filter(({template:t,children})=>(!category||t.category===category)&&(filter==='all'||children.length)&&(!query||children.length||templateMatches(t)));
 const eligible=rows.flatMap(r=>r.children).filter(i=>configurationRecordActions(i).canSubmit);
 const toggle=id=>setSelected(prev=>{const n=new Set(prev);n.has(id)?n.delete(id):n.add(id);return n;});
 function edit(row){setNotice('');if(row.legacy)setLegacyEditing({item:row,preset:library.catalog.find(p=>p.id===row.config?.template_id)});else{const t=row.template_definition||catalog.find(t=>t.id===row.template_id);setEditing({template:decorate(t),item:row});}}
 function create(t){setPicker(false);setEditing({template:decorate(t)});}
 function request(rows,operation='apply'){setError('');if(!rows.length)return;const target=rows[0].scope_id;if(rows.some(r=>r.scope_id!==target||r.scope==='workspace')){setError('请选择同一个 Agent 或所有 Agent 的配置分批提交；不会扩大范围。');return;}if(operation!=='archive'&&rows.some(r=>!configurationRecordActions(r)[operation==='disable'?'canDisable':'canSubmit'])){setError('配置状态已经变化，请刷新或查看现有审批后再操作。');return;}setCoverageAck(false);setAction({rows,operation,key:crypto.randomUUID()});}
 async function confirmAction(){if(busy||!action||(needsCoverage&&!coverageAck))return;setBusy(true);setError('');try{
  const {rows,operation,key}=action;
  if(operation==='archive'){const row=rows[0];await post(row.legacy?'/api/security/system/policy-library/'+row.id+'/archive':'/api/policy-template-configurations/'+row.id+'/archive',{revision:row.revision});setNotice('已归档配置，历史审批和应用记录保留。');}
  else{const target=rows[0].scope_id;const base=await api(target==='system'?'/api/security/system/dsl':'/api/agent-instances/'+encodeURIComponent(target)+'/dsl');const proposal=await post('/api/policy-template-configurations/proposals',{scope_id:target,selections:rows.map(r=>({id:r.id,revision:r.revision})),operation,acknowledge_coverage:coverageAck,base_hash:base.document_hash,base_revision:base.revision,request_key:key});if(proposal.state!=='pending')throw Error(proposal.result?.error||'校验未通过，当前运行策略保持不变。');setAction(null);await refresh();onApprovals(proposal.id);return;}
  setAction(null);await refresh();
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 async function saveLegacy(item,body){setBusy(true);try{await post('/api/security/system/policy-library'+(item?'/'+item.id+'/versions':''),{...body,base_revision:item?.revision||0});await refresh();setLegacyEditing(null);setNotice('已保存草案。提交审批并批准后，还需单独应用。');}finally{setBusy(false);}}
 return <div className="system-policy-library unified-policy-library">
  <div className="spl-intro"><span className="spl-root">◇</span><div><strong>策略配置与模板</strong><p>这里统一管理模板、草案和期望配置；提交审批并单独应用、取得当前加载回执后，才会出现在 Agent 的加载记录中。</p></div><button className="button tiny ghost" disabled={busy} onClick={()=>{setColumnWidths(CATALOG_COLUMNS.map(c=>c.width));refresh();}}>刷新</button></div>
  <div className="spl-toolbar"><div className="spl-filter-tabs" role="tablist" aria-label="系统策略筛选">{[['all','全部策略',groups.length],['configured','已配置',items.length]].map(([key,title,count])=><button key={key} role="tab" aria-selected={filter===key} onClick={()=>setFilter(key)}>{title}<span>{count}</span></button>)}</div><div><button className="button ghost" onClick={()=>setLegacyEditing({kind:'dsl'})}>导入 DSL</button><button className="button primary" disabled={!data} onClick={()=>setPicker(true)}>＋ 新建策略</button></div></div>
  <div className="spl-filters"><input type="search" aria-label="搜索系统策略" placeholder="搜索模板、说明、子配置名称…" value={q} onChange={e=>setQ(e.target.value)}/><select aria-label="策略分类" value={category} onChange={e=>setCategory(e.target.value)}><option value="">全部类型</option>{[...new Set(groups.map(t=>t.category))].map(c=><option key={c}>{c}</option>)}</select><select aria-label="配置范围" value={scope} onChange={e=>{setScope(e.target.value);setSelected(new Set());}}><option value="all">全部范围</option><option value="system">所有 Agent</option>{instances.map(a=><option value={a.id} key={a.id}>{configurationAgentLabel(a,agents)}</option>)}</select><span>{rows.length} 个模板</span></div>
  {error&&<p role="alert" className="spl-error">{error} <button className="button tiny ghost" onClick={refresh}>重试</button></p>}{notice&&<p role="status" className="spl-success">{notice}</p>}
  <div className="spl-records upl-template-library" tabIndex={0} role="region" aria-label="策略模板表格"><table aria-label="策略模板目录" style={{width:columnWidths.reduce((sum,width)=>sum+width,0)}} className={resizingColumn!==null?'is-resizing-columns':undefined}>
   <colgroup>{CATALOG_COLUMNS.map((column,index)=><col key={column.key} className={'upl-catalog-'+column.key} style={{width:columnWidths[index]}}/>)}</colgroup>
   <thead><tr>{CATALOG_COLUMNS.map((column,index)=><th key={column.key} scope="col">{column.label}<span className="upl-column-resizer" role="separator" aria-label={'调整'+column.label+'列宽'} aria-orientation="vertical" aria-valuemin={column.min} aria-valuemax={column.max} aria-valuenow={columnWidths[index]} tabIndex={0} title="拖动调整列宽，方向键微调；刷新页面恢复默认宽度" onPointerDown={e=>startColumnResize(e,index)} onPointerMove={e=>moveColumnResize(e,index)} onPointerUp={endColumnResize} onPointerCancel={endColumnResize} onLostPointerCapture={endColumnResize} onKeyDown={e=>keyColumnResize(e,index)}/></th>)}</tr></thead>
   {rows.map(({template:t,children})=>{const open=collapsed[t.id]===false,selectable=children.filter(i=>configurationRecordActions(i).canSubmit),description=t.description||t.summary,detailId='template-detail-'+t.id;return <tbody key={t.id}>
    <tr className={'upl-catalog-row'+(open?' is-open':'')}>
     <td><div className="upl-catalog-heading"><button className="upl-catalog-disclosure" aria-label={t.name+'：子配置'} title={open?'收起子配置':'展开子配置'} aria-expanded={open} aria-controls={detailId} onClick={()=>setCollapsed(old=>({...old,[t.id]:open}))}><span className="upl-catalog-chevron" aria-hidden="true">{open?'▾':'▸'}</span></button><span className="upl-catalog-name">{t.name}</span></div><small className="upl-catalog-category">{t.category}{t.retired?' · 历史模板':t.execution_support?.applicable===false?' · 暂不支持':''}</small></td>
     <td><p className="upl-catalog-description" title={description}>{description}</p></td>
     <td>{t.effect&&<span className={'spl-effect '+t.effect} title={t.effect}>{effectLabel(t.effect)}</span>}</td>
     <td><span className={'upl-catalog-count'+(!children.length?' is-empty':'')}>{children.length} 项</span></td>
     <td><div className="upl-catalog-actions"><button className="upl-row-action" aria-label={t.name+'：详情'} disabled={busy||t.custom} title={t.custom?'导入 DSL 没有独立模板，请编辑子配置':'查看和编辑模板'} onClick={()=>setTemplateEditing(t)}>详情</button>{!t.custom&&<button className="upl-row-action upl-submit" aria-label={t.name+'：新增子配置'} disabled={busy||t.retired} onClick={()=>create(t)}>新增子配置</button>}</div></td>
    </tr>
    {open&&<tr className="upl-template-detail-row"><td colSpan={5}><section id={detailId} aria-label={t.name+' 的子配置记录区'} className="upl-template-detail">
     <div className="upl-configurations-head"><strong>子配置记录 <span>{children.length} 项</span></strong>{!t.custom&&<button className="button tiny ghost" aria-label={t.name+'：新增子配置记录'} disabled={busy||t.retired} onClick={()=>create(t)}>＋ 新增子配置</button>}</div>
     <div className="upl-configuration-records" tabIndex={0} role="region" aria-label={t.name+' 的子配置记录'}><table aria-label={t.name+' 的子配置'}><colgroup><col className="upl-col-check"/><col className="upl-col-name"/><col className="upl-col-scope"/><col className="upl-col-target"/><col className="upl-col-effect"/><col className="upl-col-state"/><col className="upl-col-actions"/></colgroup>
      <thead><tr><th className="spl-check"><input type="checkbox" aria-label={'选择 '+t.name+' 的子配置'} disabled={busy||!selectable.length} checked={!!selectable.length&&selectable.every(i=>selected.has(i.id))} onChange={e=>setSelected(prev=>{const n=new Set(prev);selectable.forEach(i=>e.target.checked?n.add(i.id):n.delete(i.id));return n;})}/></th><th>实际策略名称</th><th>范围</th><th>保护对象 / 操作</th><th>动作</th><th>状态</th><th>操作</th></tr></thead><tbody>
      {children.map(i=>{const summary=configurationRecordSummary(i,t),controls=configurationRecordActions(i);return <tr className={'upl-policy-row'+(selected.has(i.id)?' chosen':'')} key={i.id}>
     <td><input type="checkbox" aria-label={'选择 '+i.name} disabled={busy||!controls.canSubmit} checked={selected.has(i.id)} onChange={()=>toggle(i.id)}/></td>
     <td><button className="spl-record-name upl-child-name" onClick={()=>edit(i)}>{i.name}</button></td>
     <td><span className="upl-child-scope" title={scopeName(i)}>{scopeName(i)}</span></td>
     <td><span className="upl-child-target" title={summary.targetTitle}>{summary.target}</span><small>{summary.operation}</small></td>
     <td>{summary.effects.length?<div className="spl-effect-list">{summary.effects.map(effect=><span key={effect} className={'spl-effect '+effect} title={effect+' · '+effectLabel(effect)}>{effectLabel(effect)}</span>)}</div>:<span className="upl-child-muted">查看详情</span>}</td>
     <td><span className={'upl-child-state '+summary.stateTone}>{summary.status}</span>{summary.note&&<small className="upl-child-state-note">{summary.note}</small>}</td>
     <td><div className="upl-child-actions" role="group" aria-label={i.name+'的操作'}>
      <button className="upl-row-action" aria-label={i.name+'的详情'} disabled={busy} onClick={()=>edit(i)}>详情</button>
      <button className="upl-row-action upl-submit" aria-label={i.name+'：提交审批'} disabled={busy||!controls.canSubmit} title={controls.submitReason||'核对此配置后提交审批'} onClick={()=>request([i])}>提交审批</button>
      <button className="upl-row-action" aria-label={i.name+'：查看审批'} disabled={busy||!controls.canView} title={controls.viewTitle} onClick={()=>onApprovals(i.approval_id)}>查看审批</button>
      <button className="upl-row-action upl-disable" aria-label={i.name+'：停用'} disabled={busy||!controls.canDisable} title={controls.disableReason||'提交停用审批，批准后再单独应用'} onClick={()=>request([i],'disable')}>停用</button>
     </div></td>
    </tr>;})}
      {!children.length&&<tr><td colSpan={7} className="upl-configurations-empty">暂无子配置，新增后可在此查看、提交审批或停用。</td></tr>}
     </tbody></table></div>
    </section></td></tr>}
   </tbody>;})}
  </table>{!data&&!error&&<p role="status" className="spl-empty">正在读取模板与子配置…</p>}{data&&!rows.length&&<p className="spl-empty">没有符合条件的模板。</p>}<footer><span>{rows.length} 个模板 · {items.length} 项已保存配置</span><span>保存和勾选均不会改变运行策略</span></footer></div>
  {selected.size>0&&<div className="spl-selection" role="region" aria-label="已选策略"><strong>已选 {selected.size} 项</strong><span>保留其他已应用配置</span><button onClick={()=>setSelected(new Set())}>清空</button><button className="button primary" disabled={busy} onClick={()=>request(items.filter(i=>selected.has(i.id)))}>校验并提交审批 →</button></div>}
  {editing&&<TemplateConfigurationDialog {...editing} api={api} capability={capability} agents={agents} targetId={scope!=='all'&&scope!=='system'?scope:targetId} initialTarget={scope==='system'?'system':undefined} post={post} onClose={()=>setEditing(null)} onSaved={async saved=>{setEditing(null);await refresh();setNotice(saved.execution_support?.applicable===false?'已保存参数草案；ActPlane 暂不支持此语义，不能提交审批或应用。':'已保存草案，尚未批准或应用。');}} onSubmit={i=>{setEditing(null);request([i]);}} onDisable={i=>{setEditing(null);request([i],'disable');}} onApprovals={onApprovals}/>}
  {legacyEditing&&<ExistingEditor entry={legacyEditing} capability={capability} busy={busy} onClose={()=>setLegacyEditing(null)} onSave={saveLegacy} onRecord={setRecord} onArchive={i=>{setLegacyEditing(null);request([{...i,scope_id:'system',legacy:true}],'archive');}} onDisable={i=>{setLegacyEditing(null);request([{...i,scope_id:'system',legacy:true}],'disable');}}/>}
  {templateEditing&&<TemplateDefinitionDialog template={templateEditing} post={post} onClose={()=>setTemplateEditing(null)} onSaved={async()=>{setTemplateEditing(null);await refresh();setNotice('已保存模板新版本；已有子配置和运行策略保持原版本。');}}/>}
  {record&&<PolicyDetail record={record} onClose={()=>setRecord(null)}/>}
  {picker&&<Picker catalog={catalog.filter(t=>!t.retired)} onChoose={create} onClose={()=>setPicker(false)}/>}
  {action&&<PolicyLifecycleDialog title={action.operation==='archive'?'归档配置':action.operation==='disable'?'提交停用审批':'核对并提交审批'} confirmLabel={action.operation==='archive'?'归档配置':'提交审批'} busy={busy} confirmDisabled={needsCoverage&&!coverageAck} onClose={()=>setAction(null)} onConfirm={confirmAction}><p>{action.rows.map(i=>i.name).join('、')}</p><p>范围：{scopeName(action.rows[0])}</p>{action.operation==='disable'&&action.rows.map(row=>{const snapshot=configurationDisableSnapshot(row),summary=configurationRecordSummary(snapshot,catalog.find(t=>t.id===row.template_id));return <div className="upl-disable-preview" key={row.id}><p>停用{row.applied_revision?'已应用版本 v'+row.applied_revision:'当前已应用配置'}{row.applied_revision&&row.applied_revision!==row.revision?'；未应用的新版本草案保留。':'。'}</p><dl><dt>保护对象 / 操作</dt><dd>{summary.targetTitle}<small>{summary.operation}</small></dd><dt>当前动作</dt><dd>{summary.effects.map(effectLabel).join('、')||'见原始 DSL'}</dd></dl></div>;})}{needsCoverage&&<label className="spl-note spl-attention"><input type="checkbox" aria-label="接受修改与删除的共同覆盖" checked={coverageAck} disabled={busy} onChange={e=>setCoverageAck(e.target.checked)}/> 我已了解：修改和删除共用访问组，实际影响两者。</label>}<p>{action.operation==='archive'?'仅归档未应用配置，保留历史。':action.operation==='disable'?'停用只提交审批，当前策略继续保留。由你批准后再单独应用，其他配置保留。':'此操作只提交候选，不加载策略。批准后还需单独应用。'}</p>{error&&<p role="alert" className="spl-error">{error}</p>}</PolicyLifecycleDialog>}
 </div>;
}
