export const originLabel = row => row.origin_state === 'unavailable' ? '会话关联暂不可用' : row.scope_type === 'system' ? '系统配置' : '未关联会话';
export const processLabel = agent => agent.pid ? `PID ${agent.pid}` : agent.process_state === 'offline' ? '未运行' : '当前 PID 待核验';
export const sessionReference = session => session.session_id.replace(/^session-/, '').slice(0, 8);
export const sessionTarget = session => ({page:'sessions',sessionInstance:session.instance_id,sessionId:session.session_id,sessionTab:'policies',approvalId:''});
export const agentTarget = agent => ({page:'connections',connectionInstance:agent.id,connectionTab:'policy',approvalId:''});
export function matchesApproval(row, query) {
 const words=[row.name,row.target_name,...(row.agents||[]).flatMap(a=>[a.name,a.pid?`PID ${a.pid}`:'',a.submitted_pid?`PID ${a.submitted_pid}`:'']),...(row.origin_sessions||[]).flatMap(s=>[s.name,s.session_id,s.generation_pid?`PID ${s.generation_pid}`:''])];
 return words.join(' ').toLowerCase().includes(query.trim().toLowerCase());
}
