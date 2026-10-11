// Server-owned facts from the exact connected runtime; never infer executors from product names.
export function agentPolicySource(target){
 if(!target?.id||target.mode!=='controlled')throw Error('请选择受控 Agent。');
 const fact=target.policy_source;
 if(!fact?.ready||fact.instance_id!==target.id||!target.connected)throw Error(fact?.message||'请连接并核验当前 Agent 后再读取启动来源。');
 if(fact.basis!=='verified-process-executable'||!fact.executable?.startsWith('/')||fact.pattern!=='**/'+fact.executable.split('/').at(-1))throw Error('当前 Agent 的执行程序尚未核验，请刷新连接。');
 if(['generation','pid','start_ticks','domain_id','host_id','boot_id'].some(k=>!fact[k]||target[k]!==fact[k]))throw Error('当前 Agent 的运行身份已变化，请刷新连接。');
 return {...fact,id:target.id,name:target.agent_type==='dsh'?'DeepSeek Harness':target.agent_type==='hermes'?'Hermes':target.name||'Agent',connected:true};
}
export function policySources(template,target,agents=[]){
 const rows=template.scope_type==='system'?agents.filter(a=>a.mode==='controlled'):[target];
 if(!rows.length)throw Error('尚无受控 Agent，请先添加连接。');
 return rows.map(agentPolicySource);
}
export function sourceDeclarations(sources){
 if(!sources?.length)throw Error('请先选择策略适用的 Agent。');
 if(sources.some(s=>typeof s.pattern!=='string'||!/^\*\*\/[a-zA-Z0-9_.-]{1,15}$/.test(s.pattern)))throw Error('启动程序匹配不明确，请检查 Agent 连接。');
 return [...new Set(sources.map(s=>s.pattern))].map(p=>'source AGENT = exec '+JSON.stringify(p)).join('\n');
}
export function bindGeneratedSource(dsl,target){
 const source=agentPolicySource(target),line=sourceDeclarations([source]);
 // Replace only the generated AGENT exec declaration; other provenance labels remain untouched.
 const original=/^\s*source\s+AGENT\s*=/m.test(dsl);
 if(original&&!/^\s*source\s+AGENT\s*=\s*exec\s+"[^"\r\n]+"\s*$/m.test(dsl))throw Error('生成结果的 Agent 身份声明需要检查，请在编辑器中核对。');
 const stripped=dsl.replace(/^\s*source\s+AGENT\s*=\s*exec\s+"[^"\r\n]+"\s*$/gm,'').trim();
 return line+'\n\n'+stripped;
}
