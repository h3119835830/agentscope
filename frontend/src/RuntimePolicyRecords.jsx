import React,{useEffect,useRef,useState} from 'react';
import RuntimePolicies from './RuntimePolicies.jsx';

// Both routes read the same generated records. No workspace/name fallback.
export default function RuntimePolicyRecords({task,target,api}){
 const scope=task?'task:'+task:'instance:'+target.id+':'+(target.generation||'');
 const base=task?'/api/runtime-tasks/'+encodeURIComponent(task)+'/policies':'/api/agent-instances/'+encodeURIComponent(target.id)+'/runtime-policies';
 const query=task?'':'generation='+encodeURIComponent(target.generation||'');
 const [saved,setSaved]=useState(null),[error,setError]=useState(''),[loading,setLoading]=useState(true),[before,setBefore]=useState(null),sequence=useRef(0);
 useEffect(()=>{setBefore(null);setSaved(null);},[scope]);
 useEffect(()=>{
  const request=++sequence.current;let alive=true,inflight=false;setLoading(true);setError('');
  async function load(){if(inflight)return;inflight=true;try{
   if(!task&&!target.generation){if(alive)setSaved({scope,records:[]});return;}
   const params=[query,before?'before='+encodeURIComponent(before):''].filter(Boolean).join('&');
   const result=await api(base+(params?'?'+params:''));
   if(alive&&request===sequence.current){setSaved({...result,scope});setError('');}
  }catch{if(alive&&request===sequence.current)setError('读取失败');}finally{inflight=false;if(alive)setLoading(false);}}
  load();const timer=setInterval(load,7000);return()=>{alive=false;sequence.current++;clearInterval(timer);};
 },[api,scope,base,query,before]);
 const data=saved?.scope===scope?saved:null;
 const readDetail=record=>api(base+'/'+encodeURIComponent(record.id)+(query?'?'+query:''));
 return <div className="runtime-policy-records">
  <RuntimePolicies key={scope} task={scope} records={data?.records||[]} workspace={data?.workspace} api={api} readDetail={readDetail} loading={loading} error={error}/>
  {data?.next_cursor&&<button className="button ghost tiny" onClick={()=>setBefore(data.next_cursor)}>更早策略</button>}
  {before&&<button className="button ghost tiny" onClick={()=>setBefore(null)}>返回最新</button>}
 </div>;
}
