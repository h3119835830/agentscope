export const taskNames = {};
export const displayName = task => taskNames[task?.name] || task?.name || '未命名任务';
export const phaseNames = {prepared:'待生成策略',generating:'策略生成中',bootstrapping:'策略生成中',policy_review:'待确认策略',running:'执行中',recovering:'恢复中',failed:'已暂停',ended:'已结束',completed:'已完成',approved:'已批准',stopped:'已停止'};
export const phaseName = phase => phaseNames[phase] || phase || '尚未开始';
export const timeLabel = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '—';
export const policySummary = atom => '禁止'+(atom.operations||[]).map(op=>({write:'写入',unlink:'删除'})[op]||op).join('、');
export function visibleTasks(records, query, filter) {
  const q = query.trim().toLowerCase();
  return records.filter(t => (!filter || (filter==='active' ? ['running','generating','recovering','policy_review','prepared'].includes(t.phase) : ['ended','completed','failed','stopped'].includes(t.phase))) && (!q || [displayName(t),t.id,t.source_name,t.workspace].some(x=>String(x||'').toLowerCase().includes(q))));
}
export function proposalRows(proposal) {
  const data=proposal?.proposal||{};
  return (data.draft?.atoms||data.policy_ir?.atoms||[]).map((atom,i)=>({...atom,number:i+1,dsl:(proposal?.validation?.compiler?.rules||[]).filter(r=>r.name===`bootstrap-${i+1}`).map(r=>r.source_text).filter(Boolean).filter((v,i,a)=>a.indexOf(v)===i).join('\n\n')}));
}
