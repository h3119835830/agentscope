import React,{useEffect,useState} from 'react';
import SessionSecurityPanel from './SessionSecurityPanel.jsx';

export default function AgentLoadedPolicies({id,api,onConfiguration}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true,inflight=false;setData(null);setError('');async function load(){if(inflight)return;inflight=true;try{const v=await api('/api/agent-instances/'+encodeURIComponent(id)+'/loaded-policies');if(alive){setData(v);setError('');}}catch(e){if(alive){setData(null);setError(e.message);}}finally{inflight=false;}}load();const timer=setInterval(load,3000);return()=>{alive=false;clearInterval(timer);};},[id,api,revision]);
 return <div className="agent-loaded-policies"><div className="agent-loaded-heading"><p>当前核验的内核加载快照。已加载不代表已命中或覆盖所有操作。</p><button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>刷新加载记录</button></div>{error&&<p role="alert" className="inline-notice warning">{error}</p>}<SessionSecurityPanel data={data?{loaded_policies:data}:null} loading={!data&&!error} error={error} onConfiguration={onConfiguration}/></div>;
}
