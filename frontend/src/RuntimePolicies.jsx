import React,{useEffect,useRef,useState} from 'react';
import './runtimePolicies.css';

export function runtimePolicyName(record,workspace=''){
 if(typeof record.name==='string'&&record.name.trim())return record.name;
 const targets=(record.targets||[]).map(path=>workspace?path.replace(workspace+'/',''):path);
 if(targets.length&&record.effect==='restrict')return '保护 '+targets[0]+(targets.length>1?' 等对象':'');
 return record.statement||'运行时策略';
}
export function runtimePolicyTrigger(record){
 return ({native_user:'用户消息',administrator:'管理员消息',persistent_memory:'跨会话记忆'})[record.trigger?.actor]||'未记录来源';
}
export function generatedRuntimePolicies(records){
 return records.filter(record=>record.stage==='runtime'&&record.effect==='restrict'&&record.policy_type!=='semantic_only'&&record.targets?.length);
}
function PolicyDetails({record,workspace}){
 const templates=record.template_reference;
 return <div className="runtime-policy-details">
  <dl><dt>具体约束</dt><dd>{record.statement}</dd>
   <dt>作用对象</dt><dd>{(record.targets||[]).map(path=>workspace?path.replace(workspace+'/',''):path).join('、')}</dd>
   <dt>参考模板</dt><dd>{templates?.items?.length?templates.items.map(item=>item.name).join('、'):templates?.searched?'已检索已审核模板，未引用具体模板':'未记录模板引用'}</dd>
   {record.trigger?.text&&<><dt>触发原文</dt><dd>{record.trigger.text}</dd></>}
  </dl>
  {record.compilation?.dsl&&<details className="runtime-policy-dsl"><summary>查看 DSL</summary><pre>{record.compilation.dsl}</pre></details>}
 </div>;
}
export default function RuntimePolicies({task,records=[],workspace='',api,loading=false,error=''}){
 const [selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[detailError,setDetailError]=useState('');
 const selection=useRef(0);
 useEffect(()=>{selection.current++;setSelected(null);setDetail(null);setDetailError('');},[task]);
 async function open(record){
  const request=++selection.current;setDetail(null);setDetailError('');
  if(selected===record.id){setSelected(null);return;}
  setSelected(record.id);
  try{const result=await api(`/api/managed/tasks/${encodeURIComponent(task)}/strategy-records/${encodeURIComponent(record.id)}`);if(request===selection.current)setDetail(result);}
  catch(error){if(request===selection.current)setDetailError('暂时无法读取策略详情，请收起后重试。');}
 }
 const shown=generatedRuntimePolicies(records);
 return <section className="runtime-policies" aria-label="运行时策略">
  {error&&<p role="alert" className="runtime-policy-notice">暂时无法刷新，正在重试。</p>}
  <table><thead><tr><th scope="col">策略名称</th><th scope="col">由谁触发</th></tr></thead>
   <tbody>{shown.map(record=><React.Fragment key={record.id}><tr>
    <td><button className="runtime-policy-name" aria-expanded={selected===record.id} onClick={()=>open(record)}>{runtimePolicyName(record,workspace)}<span aria-hidden="true">{selected===record.id?'⌃':'⌄'}</span></button></td>
    <td>{runtimePolicyTrigger(record)}</td>
   </tr>{selected===record.id&&<tr className="runtime-policy-expanded"><td colSpan="2">{detailError?<p role="alert">{detailError}</p>:detail?<PolicyDetails record={detail} workspace={workspace}/>:<p role="status">正在读取详情…</p>}</td></tr>}</React.Fragment>)}</tbody>
  </table>
  {!shown.length&&<p className="runtime-policy-empty">{loading?'正在读取策略…':'暂未生成新的运行时策略。'}</p>}
 </section>;
}
