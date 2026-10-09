import React,{useState} from 'react';
import RecordBadge from './RecordBadge.jsx';
import InstanceSecurity from './InstanceSecurity.jsx';
import {tabKeys} from './consoleState.mjs';

// These are fixed controller/runner settings, not per-instance policy or live
// enforcement receipts. Keep this projection aligned with the scope RFC.
export const systemSecuritySettings=Object.freeze([
 {name:'运行隔离',value:'隔离文件系统与进程，使用非特权身份运行。'},
 {name:'控制面访问',value:'Agent 不获得 Broker 和控制 API 的访问权限。'},
 {name:'权限变更',value:'放宽权限须人工确认；变更后重新核验再执行。'},
 {name:'控制失联处理',value:'控制心跳超过 8 秒，终止对应的受控执行进程。'},
]);

export function SystemSecurityConfiguration(){
 return <section className="system-security" aria-label="系统共享配置">
  <div className="security-scope-heading"><div><h3>系统配置</h3><RecordBadge tone="purple" dot={false}>所有 Agent 共用</RecordBadge></div><span>由系统统一管理 · 只读</span></div>
  <p className="security-scope-note">所有受控 Agent 共用；仅观测的连接需接管执行后才能应用。</p>
  <div className="security-table-scroll" tabIndex={0} aria-label="系统配置记录"><table className="security-rules system-security-table"><thead><tr><th>配置项</th><th>配置内容</th></tr></thead><tbody>{systemSecuritySettings.map(setting=><tr key={setting.name}><td><strong>{setting.name}</strong></td><td><p className="security-sentence">{setting.value}</p></td></tr>)}</tbody></table></div>
 </section>;
}

export default function SecurityConfiguration({row,...props}){
 const [scope,setScope]=useState('agent');
 const tabs=[['system','系统配置','所有 Agent 共用'],['agent','当前 Agent 配置','所有工作区共用']];
 return <div className="security-configuration">
  <div className="security-scope-tabs" role="tablist" aria-label="安全配置作用范围">{tabs.map(([key,title,caption])=><button type="button" role="tab" key={key} id={'security-scope-'+key} aria-controls={'security-scope-panel-'+key} aria-selected={scope===key} tabIndex={scope===key?0:-1} onClick={()=>setScope(key)} onKeyDown={e=>tabKeys(e,tabs.map(t=>t[0]),scope,setScope)}><b>{title}</b><small>{caption}</small></button>)}</div>
  <div role="tabpanel" id={'security-scope-panel-'+scope} aria-labelledby={'security-scope-'+scope}>
   {scope==='system'?<SystemSecurityConfiguration/>:row.mode==='controlled'?<InstanceSecurity row={row} {...props}/>:<p className="task-empty">当前 Agent 尚未接管执行。添加受控连接后，可配置其所有工作区共用的规则。</p>}
  </div>
 </div>;
}
