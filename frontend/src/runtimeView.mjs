// Only a fresh, task-bound Broker observation can describe a live DSH.
export function connectionView(data, {now=Date.now(), failed=false}={}) {
  const phase=data?.state?.phase;
  const checked=Date.parse(data?.execution?.checked_at || '');
  const fresh=!failed && Number.isFinite(checked) && now-checked>=-5000 && now-checked<10000;
  if (phase==='ended') return {label:'已结束',tone:'neutral',live:false,fresh};
  if (!fresh) return {label:'状态待更新',tone:'warning',live:false,fresh:false};
  if (phase==='failed') return {label:'已暂停',tone:'warning',live:false,fresh};
  if (['prepared','generating','recovering'].includes(phase)) return {label:phase==='prepared'?'尚未启动':phase==='generating'?'策略生成中':'恢复中',tone:'neutral',live:false,fresh};
  const e=data.execution, executor=e.executor || {};
  const live=e.verified===true && e.status==='running' && e.domain_verified===true
    && e.cgroup_verified===true && executor.state==='running' && Number.isInteger(executor.pid) && executor.pid>0;
  return {label:live?(data.state.gate==='open'?'进程已核验':'工具执行暂停'):'绑定未确认',tone:live?'good':'warning',live,fresh};
}

export function relativeTarget(target,workspace) {
  if (!target) return '未记录对象';
  return workspace && target.startsWith(workspace+'/') ? target.slice(workspace.length+1) : target;
}
