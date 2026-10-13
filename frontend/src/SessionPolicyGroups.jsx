import React from 'react';
import {PolicyRecords} from './ActPlanePolicies.jsx';
export default function SessionPolicyGroups({records=[],loading,error,type,onType,onDetail,onConfigure}){
 const local=records.filter(r=>r.scope_type==='session');
 const inherited=records.filter(r=>r.scope_type!=='session');
 return <>{loading?<p role="status">正在读取策略…</p>:error?null:<>
  <div className="flow-local-heading">本会话新增约束</div>
  {local.length?<PolicyRecords compact records={local} onDetail={onDetail}/>:<p className="task-empty">本会话没有独立新增约束。生成建议和未应用候选不计为当前保护。</p>}
  <details className="policy-inheritance"><summary>继承约束 · {inherited.length} 条 · 只读查看</summary><div>
   <label className="session-policy-filter">策略类型<select aria-label="筛选继承策略类型" value={type} onChange={e=>onType(e.target.value)}><option value="">全部继承策略</option><option value="system">系统策略</option><option value="agent">Agent 长期基线</option><option value="workspace">工作区策略</option></select></label>
   <PolicyRecords compact editLabel="前往所属配置" records={inherited.filter(r=>!type||r.scope_type===type)} onDetail={onDetail} onEdit={onConfigure} empty="没有匹配的继承策略。"/>
   <p className="experience-note">继承规则由所属配置维护；配置操作会前往归属位置，不能在本会话直接修改。</p>
  </div></details>
 </>}</>;
}
