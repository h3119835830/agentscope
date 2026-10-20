import React,{useEffect,useState} from 'react';

export default function PolicyReferenceWorkspaceSelect({agentId,value,onChange,api}){
 const [data,setData]=useState(null),[error,setError]=useState('');
 useEffect(()=>{let alive=true;setData(null);setError('');if(!agentId)return()=>{alive=false;};api('/api/agent-instances/'+encodeURIComponent(agentId)+'/policy-reference-workspaces').then(v=>{if(alive)setData(v);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[agentId,api]);
 const workspaces=data?.workspaces||[],selected=workspaces.find(w=>w.id===value);
 return <div className="policy-reference-select"><label>参考工作区<select aria-label="运行前参考工作区" value={selected?.id||''} onChange={e=>onChange(e.target.value)} disabled={!data||!!error}><option value="">由助手按需选择</option>{workspaces.map(w=><option value={w.id} key={w.id}>{w.name}</option>)}</select></label><span>{error?'工作区暂不可读取：'+error:selected?'只缩小本轮可读资料，不改变策略作用范围。':'助手可在此 Agent 已登记且有权限的工作区中选择相关资料。'}</span></div>;
}
