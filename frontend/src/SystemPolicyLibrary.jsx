import React,{useEffect,useRef,useState} from 'react';
import {DslCode} from './DslCode.jsx';
import {ApprovalDetail} from './PolicyApprovals.jsx';
import {PolicyDetail} from './ActPlanePolicies.jsx';
import {effects,modes,operations,validate,ruleDsl,matches,lines} from './systemPolicyLibrary.mjs';
import './systemPolicyLibrary.css';

const base='/api/security/system/policy-library';
const blank={name:'',mode:'suffix',values:'',ops:['open'],effect:'block',reason:'',template_id:''};
const scopeText='勾选并确认后，统一载入所有受控 Agent；Agent 策略继续继承这些约束。';
const configuredStatus=(item,phase,targets=[])=>{
 if(!item)return '未配置';if(!item.applied)return '已保存';if(phase!=='ready')return '加载未完成';if(item.has_changes)return '有更新待应用';
 const records=item.records||[];if(records.length&&records.every(r=>r.active))return '已应用';
 const counts=records.map(r=>r.coverage?.verified_count||0),total=records[0]?.coverage?.total_count||0,verified=counts.length?Math.min(...counts):0;
 return verified?'已应用 '+verified+'/'+total:targets.some(t=>t.pid)?'待核验':'启动时加载';
};
function Badge({effect}){return <span className={'spl-effect '+effect}>{effect}<small>{effects[effect]?.name}</small></span>;}
function Modal({children,onClose,label,className=''}) {
 const ref=useRef(null),origin=useRef(document.activeElement);
 useEffect(()=>{ref.current?.showModal();return()=>{ref.current?.close();origin.current?.isConnected&&origin.current.focus();};},[]);
 return <dialog ref={ref} className={'spl-dialog '+className} aria-label={label} onCancel={e=>{e.preventDefault();onClose();}}>{children}</dialog>;
}
function Editor({entry,capability,onClose,onSave,onArchive,onDisable,onRecord,busy}){
 const item=entry.item,preset=entry.preset,kind=item?.kind||entry.kind||'structured';
 const [config,setConfig]=useState(()=>({...blank,...(item?.config||preset||{}),template_id:item?.config?.template_id||preset?.id||''})),
 [name,setName]=useState(item?.name||''),[text,setText]=useState(item?.document?.original_dsl||''),[tab,setTab]=useState('configuration'),
 [example,setExample]=useState('/project/production.env'),[error,setError]=useState(''),[copied,setCopied]=useState(false);
 const change=(key,value)=>setConfig(c=>({...c,[key]:value}));
 const validation=kind==='structured'?validate(config):!name.trim()?'请填写文档名称。':!text.trim()?'请填写完整 DSL 文档。':'';
 let preview=text;
 if(kind==='structured'){try{preview=ruleDsl({...config,id:item?.id||'draft'});}catch{preview='';}}
 const source=preset||item;
 const allowed=['exec','remote'].includes(config.mode)?['exec']:['endpoint','flow'].includes(config.mode)?['connect']:['open','write','unlink'];
 const match=['suffix','filename','tail','directory','exact','flow'].includes(config.mode)?matches(config,example):null;
 async function save(){setError('');if(validation){setError(validation);return;}try{
  await onSave(item,kind==='structured'?{kind,config:Object.fromEntries(Object.keys(blank).map(k=>[k,config[k]]))}:{kind,document:{...(item?.document||{}),id:item?.id||'new',name,original_dsl:text}});
 }catch(e){setError(e.message);}}
 async function copy(){try{await navigator.clipboard.writeText(preview);setCopied(true);}catch{setError('无法访问剪贴板，请选中 DSL 文本复制。');}}
 return <Modal label="配置系统策略" onClose={()=>!busy&&onClose()}>
  <header className="spl-editor-head"><span className="spl-symbol">◇</span><div><small>系统策略 · 所有受控 Agent</small><h2>{item?.name||preset?.name||(kind==='dsl'?'导入 DSL':'新建策略')}</h2></div><button aria-label="关闭配置" disabled={busy} onClick={onClose}>×</button></header>
  <div className="spl-editor-tabs" role="tablist" aria-label="策略配置详情">{[['configuration','配置策略'],['dsl','原始 DSL'],...(item?.records?.length?[['evidence','应用详情']]:[])].map(([k,t])=><button key={k} role="tab" aria-selected={tab===k} onClick={()=>setTab(k)}>{t}</button>)}</div>
  <div className="spl-editor-body">
  {error&&<p className="spl-error" role="alert">{error}</p>}
  {tab==='configuration'&&<div className="spl-editor-grid"><div className="spl-form">
   {kind==='dsl'?<><label>文档名称<input value={name} onChange={e=>setName(e.target.value)} maxLength={120}/></label><p className="spl-note">保留完整文档中的来源、标签、条件和全部规则。应用时以整个文档为单位。</p><label>选择 .dsl 文件<input type="file" accept=".dsl,text/plain" onChange={async e=>{const f=e.target.files?.[0];if(!f)return;if(f.size>50000){setError('DSL 文档不能超过 50000 字节。');return;}setText(await f.text());if(!name)setName(f.name);}}/></label><label>原始 DSL<textarea className="spl-dsl-input" value={text} onChange={e=>setText(e.target.value)} rows={18} spellCheck={false}/></label>{item?.validation_error&&<p className="spl-note">上次保存校验：{item.validation_error}</p>}</>:<>
   <label>策略名称<input value={config.name} onChange={e=>change('name',e.target.value)} maxLength={120}/></label>
   <section><h3>保护对象</h3><div className="spl-match-fields"><label>匹配方式<select value={config.mode} onChange={e=>{const mode=e.target.value;setConfig(c=>({...c,mode,ops:['exec','remote'].includes(mode)?['exec']:['endpoint','flow'].includes(mode)?['connect']:['open']}));}}>{Object.entries(modes).map(([k,t])=><option key={k} value={k}>{t}</option>)}</select></label><label>匹配内容<textarea value={config.values} onChange={e=>change('values',e.target.value)} rows={Math.min(5,Math.max(2,lines(config.values).length))} placeholder={preset?.placeholder||(['suffix','flow'].includes(config.mode)?'.env':'每行一个匹配对象')} spellCheck={false}/></label></div>
   <p className="spl-note">{['suffix','flow'].includes(config.mode)?'.env 匹配 .env 和 production.env，不匹配 .env.local。字面匹配，区分大小写。':config.mode==='filename'?'仅匹配同名文件，所在目录不限。':config.mode==='directory'?'匹配指定目录本身及其全部内容。填写实际目录。':config.mode==='endpoint'?'支持 IPv4 地址、地址前缀（如 10.0.0.）或 *。':config.mode==='remote'?'网络来源标签传播后匹配程序执行；并不等同于脚本签名校验。':['exec','remote'].includes(config.mode)?'按实际执行文件的名称匹配；符号链接以解析后的执行文件为准。':'使用实际路径。符号链接按内核解析后的目标匹配。'}</p>
   {['suffix','filename','tail','flow'].includes(config.mode)&&capability&&!capability.file_suffix&&<p className="spl-note spl-attention">可保存配置；当前执行环境需完成后缀能力核验后才能加载。</p>}
   <fieldset><legend>触发操作</legend><div className="spl-checks">{allowed.map(op=><label key={op}><input type="checkbox" checked={config.ops.includes(op)} onChange={e=>change('ops',e.target.checked?[...config.ops,op]:config.ops.filter(x=>x!==op))}/>{operations[op]}</label>)}</div></fieldset>
   </section><section><h3>匹配后的动作</h3><div className="spl-actions">{Object.entries(effects).map(([key,value])=><label className={config.effect===key?'selected':''} key={key}><input type="radio" name="policy-effect" value={key} checked={config.effect===key} onChange={()=>change('effect',key)}/><strong>{key}</strong><span>{value.name}</span></label>)}</div><p className="spl-note">{effects[config.effect]?.detail}</p><label>反馈说明<textarea value={config.reason} onChange={e=>change('reason',e.target.value)} rows={3} maxLength={600}/></label><p className="spl-note">用于解释策略命中；实际送达状态以反馈回执为准。</p></section>
   </>}
   {source?.origin&&<details className="spl-source"><summary>适用条件与来源</summary><p>{source.note||source.description}</p><p>{source.origin}</p>{source.source&&<a href={source.source} target="_blank" rel="noreferrer">查看来源 ↗</a>}</details>}
  </div><aside className="spl-config-aside"><h3>配置摘要</h3>{kind==='structured'?<><Badge effect={config.effect}/><p>{effects[config.effect]?.detail}</p><dl><dt>保护对象</dt><dd>{config.values||'填写后展示'}</dd><dt>触发操作</dt><dd>{config.ops.map(o=>operations[o]).join('、')}</dd><dt>适用范围</dt><dd>所有受控 Agent 及其工作区、会话</dd></dl>{['suffix','filename','tail','directory','exact','flow'].includes(config.mode)&&<label>匹配示例<input value={example} onChange={e=>setExample(e.target.value)} spellCheck={false}/><span className={'spl-match-result '+(match?'yes':'')}>{match===null?'输入绝对路径检查匹配':match?'匹配此对象':'不匹配此对象'}</span></label>}</>:<p>文档中的每条规则分别展示，来源和跨事件依赖随整个文档一起应用。</p>}<div className="spl-inherit"><b>系统策略</b><span>↓ 所有 Agent 继承</span><b>Agent 专属策略</b><span>追加约束，保留系统保护</span></div></aside></div>}
  {tab==='dsl'&&<div className="spl-dsl-pane"><div className="spl-section-head"><h3>原始策略文档</h3><button className="button tiny ghost" disabled={!preview} onClick={copy}>{copied?'已复制':'复制 DSL'}</button></div>{kind==='structured'&&<p className="spl-note">AGENT 来源由后端根据受控启动身份补全。逐 Agent 的加载文档与映射可在应用详情查看。</p>}{preview?<DslCode text={preview}/>:<p className="spl-note">{validation}</p>}</div>}
  {tab==='evidence'&&<div className="spl-dsl-pane"><h3>规则与加载记录</h3>{item.records.map(record=><button className="spl-evidence-row" key={record.id} onClick={()=>onRecord(record)}><span>{record.rule_name}<small>{record.statement}</small></span><span>查看原文与加载回执 ↗</span></button>)}</div>}
  </div><footer className="spl-editor-footer"><span>{item?.applied?'保存新版本后，当前策略继续执行，直到再次确认应用。':'保存到配置库后，可勾选并校验应用。'}</span>{item?.applied?<button className="spl-danger" disabled={busy} onClick={()=>onDisable(item)}>停用策略…</button>:item&&<button className="spl-danger" disabled={busy} onClick={()=>onArchive(item)}>归档</button>}<button className="button ghost" disabled={busy} onClick={onClose}>取消</button><button className="button primary" disabled={busy} onClick={save}>{busy?'正在保存…':'保存配置'}</button></footer>
 </Modal>;
}

export default function SystemPolicyLibrary({api,post,onChanged}){
 const [data,setData]=useState(null),[capability,setCapability]=useState(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),
 [filter,setFilter]=useState('all'),[q,setQ]=useState(''),[category,setCategory]=useState('全部类型'),[selected,setSelected]=useState(new Set()),[editor,setEditor]=useState(null),[review,setReview]=useState(null),[record,setRecord]=useState(null),[removal,setRemoval]=useState(null);
 const mounted=useRef(false),request=useRef(0);
 async function refresh(){const seq=++request.current;try{const value=await api(base);if(mounted.current&&seq===request.current){setData(value);setError('');}}catch(e){if(mounted.current)setError(e.message);}}
 useEffect(()=>{mounted.current=true;refresh();api('/api/security/system/execution-capabilities').then(v=>{if(mounted.current)setCapability(v);}).catch(()=>{});return()=>{mounted.current=false;request.current++;};},[api]);
 const rows=data?[...data.items.map(item=>({id:item.id,item,preset:data.catalog.find(p=>p.id===item.config?.template_id)})),...data.catalog.filter(p=>!data.items.some(i=>i.config?.template_id===p.id)).map(preset=>({id:'preset-'+preset.id,preset}))]:[];
 const visible=rows.filter(r=>(filter==='all'||r.item)&&(category==='全部类型'||(r.preset?.category||r.item?.category)===category)&&JSON.stringify([r.item?.name||r.preset?.name,r.item?.config||r.preset,r.item?.document?.original_dsl]).toLowerCase().includes(q.toLowerCase()));
 const selectable=visible.filter(r=>r.item&&!r.item.validation_error);
 const toggle=id=>setSelected(old=>{const next=new Set(old);next.has(id)?next.delete(id):next.add(id);return next;});
 async function save(item,body){setBusy(true);try{await post(base+(item?'/'+encodeURIComponent(item.id)+'/versions':''),{...body,base_revision:item?.revision||0});await refresh();setEditor(null);setNotice('已保存到配置库。勾选并确认后才会应用。');onChanged?.();}finally{setBusy(false);}}
 async function archive(item){setBusy(true);setError('');try{await post(base+'/'+encodeURIComponent(item.id)+'/archive',{revision:item.revision});setSelected(s=>new Set([...s].filter(x=>x!==item.id)));await refresh();setEditor(null);setNotice('配置已归档。');}catch(e){setError(e.message);}finally{setBusy(false);}}
 async function propose(removals=[]){setBusy(true);setError('');setNotice('');try{
  const selections=removals.length?[]:data.items.filter(i=>selected.has(i.id)).map(i=>({id:i.id,revision:i.revision}));
  const proposal=await post(base+'/proposals',{selections,removals,base_hash:data.base_hash,base_revision:data.base_revision,request_key:crypto.randomUUID()});
  if(proposal.state!=='pending'){setError(proposal.result?.error||'策略未通过校验，请调整配置后重试。');return;}
  const result=await api('/api/console/approvals/'+proposal.id);setReview(result);setRemoval(null);
 }catch(e){setError(e.message);}finally{setBusy(false);}}
 async function decide(p,decision){setBusy(true);try{const result=await post('/api/security/system/dsl/proposals/'+p.id+'/'+decision,{proposal_hash:p.proposal_hash});await refresh();setReview(null);setSelected(new Set());setNotice(decision==='confirm'?'确认已处理：'+(result.resumed_count||0)+' 个运行中 Agent 已加载，其余受控 Agent 将在启动时加载。':'此次候选已拒绝，运行策略保持原状。');onChanged?.();}finally{setBusy(false);}}
 return <div className="system-policy-library">
  <div className="spl-intro"><span className="spl-root">◇</span><div><strong>所有受控 Agent 共同遵守</strong><p>{scopeText}</p></div><button className="button tiny ghost" disabled={busy} onClick={refresh}>刷新</button></div>
  <div className="spl-toolbar"><div className="spl-filter-tabs" role="tablist" aria-label="系统策略筛选">{[['all','全部策略',rows.length],['configured','已配置',data?.items.length||0]].map(([k,t,n])=><button role="tab" aria-selected={filter===k} key={k} onClick={()=>setFilter(k)}>{t}<span>{n}</span></button>)}</div><div><button className="button ghost" onClick={()=>setEditor({kind:'dsl'})}>导入 DSL</button><button className="button primary" onClick={()=>setEditor({kind:'structured'})}>＋ 新建策略</button></div></div>
  <div className="spl-filters"><input type="search" aria-label="搜索系统策略" placeholder="搜索策略名称、保护对象、动作…" value={q} onChange={e=>setQ(e.target.value)}/><select aria-label="策略分类" value={category} onChange={e=>setCategory(e.target.value)}>{['全部类型',...new Set(rows.map(r=>r.preset?.category||r.item?.category))].map(c=><option key={c}>{c}</option>)}</select><span>共 {visible.length} 个配置</span></div>
  {error&&<p className="spl-error" role="alert">{error}</p>}{notice&&<p className="spl-success" role="status">{notice}</p>}
  <div className="spl-records"><table aria-label="系统策略配置库"><thead><tr><th className="spl-check"><input type="checkbox" aria-label="选择当前可应用配置" checked={!!selectable.length&&selectable.every(r=>selected.has(r.id))} onChange={e=>setSelected(s=>{const next=new Set(s);selectable.forEach(r=>e.target.checked?next.add(r.id):next.delete(r.id));return next;})}/></th><th>策略名称</th><th>保护对象 / 操作</th><th>动作</th><th>状态</th><th>操作</th></tr></thead><tbody>
  {visible.flatMap(row=>{
   const item=row.item,cfg=item?.config||row.preset,rules=item?.kind==='dsl'&&item.rules?.length?item.rules:[null];
   return rules.map((rule,index)=><tr key={row.id+':'+index} className={selected.has(row.id)?'chosen':''}>
    <td><input type="checkbox" aria-label={'选择 '+(rule?.rule_name||item?.name||cfg?.name)} checked={selected.has(row.id)} disabled={!item||!!item.validation_error} onChange={()=>toggle(row.id)}/></td>
    <td><button className="spl-record-name" onClick={()=>setEditor(row)}>{rule?.rule_name||item?.name||cfg?.name}</button><span className="spl-mobile-status">{configuredStatus(item,data.phase,data.targets)}</span><small>{rule?item.name+' · 完整文档一起应用':item?.config?item.category:row.preset?.description||item?.category}</small></td>
    <td>{cfg?<><code>{lines(cfg.values).slice(0,2).join('、')||'待填写实际目录'}{lines(cfg.values).length>2?' …':''}</code><small>{modes[cfg.mode]} · {cfg.ops.map(o=>operations[o]).join('、')}</small></>:rule?<><code>{rule.clauses.map(c=>c.target).join('、')}</code><small>{rule.clauses.map(c=>operations[c.operation]||c.operation).join('、')}</small></>:<small>完整 DSL 文档</small>}</td>
    <td><div className="spl-effect-list">{(cfg?[cfg.effect]:rule?.effects||[]).map(effect=><Badge key={effect} effect={effect}/>)}</div></td>
    <td><span className={'spl-state '+(item?.has_changes?'changed':item?.applied?'applied':item?'saved':'')}>{item?.validation_error?'需校验':configuredStatus(item,data.phase,data.targets)}</span></td>
    <td><button className="spl-open" onClick={()=>setEditor(row)}>{item?'详情 / 编辑':'配置'} ↗</button></td></tr>);
  })}
  </tbody></table>{!visible.length&&<div className="spl-empty">{data?'没有符合条件的策略。':'正在读取系统配置库…'}</div>}<footer><span>{data?.items.length||0} 项已保存配置</span><span>保存和勾选均不会改变运行策略</span></footer></div>
  {selected.size>0&&<div className="spl-selection" role="region" aria-label="已选策略"><strong>已选 {selected.size} 项</strong><span>新增或更新所选配置，保留其他已应用策略</span><button onClick={()=>setSelected(new Set())}>清空</button><button className="button primary" disabled={busy} onClick={()=>propose()}>{busy?'正在校验…':'校验并预览 →'}</button></div>}
  {editor&&<Editor entry={editor} capability={capability} busy={busy} onClose={()=>setEditor(null)} onSave={save} onArchive={archive} onDisable={item=>{setEditor(null);setRemoval(item);}} onRecord={setRecord}/>}
  {record&&<PolicyDetail record={record} onClose={()=>setRecord(null)} onEdit={()=>setRecord(null)}/>}
  {review&&<ApprovalDetail data={review} busy={busy} onClose={()=>setReview(null)} onDecision={decide}/>}
  {removal&&<Modal label="停用系统策略" className="spl-small-dialog" onClose={()=>!busy&&setRemoval(null)}><header><h2>停用 {removal.name}</h2></header><p>将从所有受控 Agent 的系统策略中移除这个完整文档。配置保留在库中；其他系统策略和 Agent 策略继续保留。</p>{error&&<p role="alert" className="spl-error">{error}</p>}<p>下一步查看移除差异与全部受影响 Agent，再人工确认。</p><footer><button className="button ghost" disabled={busy} onClick={()=>setRemoval(null)}>取消</button><button className="button primary" disabled={busy} onClick={()=>propose([removal.id])}>校验停用影响 →</button></footer></Modal>}
 </div>;
}
