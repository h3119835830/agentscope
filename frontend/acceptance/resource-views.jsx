// Isolated visual fixture: no fetch, credentials, API writes or live approvals.
import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import WritePermissionDialog from '../src/WritePermissionDialog.jsx';
import '../src/styles.css';
import '../src/prototypeTheme.css';
import '../src/actplanePolicies.css';
import '../src/policyExperience.css';
import '../src/agentPolicyWorkbench.css';
const agent={id:'isolated-mapping-fixture',name:'合成场景',agent_type:'dsh'};
const api=async()=>({instance_id:agent.id,generation:'synthetic-generation',policy_hash:'a'.repeat(64),
 limits:{write_ranges_per_resource:1,exact_path_bytes:63},effective_policy:{rules:[]},application:'隔离界面验收，不连接主服务。'});
function Fixture(){
 const [open,setOpen]=useState(false),[captured,setCaptured]=useState(null);
 return <main style={{padding:32}}><h1>短路径映射 · 隔离界面验收</h1><p>合成数据，无主服务请求；不代表真实审批或加载。</p>
  <button className="button primary" onClick={()=>setOpen(true)}>打开写权限申请</button>
  {captured&&<section aria-label="已捕获的模拟申请"><h2>已捕获的模拟申请（未提交服务）</h2><p>目标：{agent.name}</p><ul>{captured.paths.map(p=><li key={p}>可写：{p}</li>)}{captured.short_paths.map(p=><li key={p}>映射：{p}</li>)}{captured.protected_paths.map(p=><li key={p}>仍保护：{p}</li>)}</ul></section>}
  {open&&<WritePermissionDialog agent={agent} agents={[agent]} api={api} post={async(_url,body)=>{setCaptured(body);return {approval_id:'isolated-only'};}} onClose={()=>setOpen(false)} onApprovals={()=>{}}/>}
 </main>;
}
createRoot(document.getElementById('root')).render(<Fixture/>);
