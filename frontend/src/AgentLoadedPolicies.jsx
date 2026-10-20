import React,{useEffect,useState} from 'react';
import SessionSecurityPanel from './SessionSecurityPanel.jsx';

export default function AgentLoadedPolicies({id,api}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[revision,setRevision]=useState(0);
 useEffect(()=>{let alive=true;setData(null);setError('');api('/api/agent-instances/'+encodeURIComponent(id)+'/loaded-policies').then(v=>{if(alive)setData(v);}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[id,api,revision]);
 return <div className="agent-loaded-policies"><div className="agent-loaded-heading"><p>这是运行事实，不是配置草案：只展示当前进程中已由加载快照和运行绑定共同核验的 ActPlane 策略。</p><button className="button tiny ghost" onClick={()=>setRevision(v=>v+1)}>刷新加载记录</button></div>{error&&<p role="alert" className="inline-notice warning">{error}</p>}<SessionSecurityPanel data={data?{loaded_policies:data}:null} loading={!data&&!error} error={error}/></div>;
}
