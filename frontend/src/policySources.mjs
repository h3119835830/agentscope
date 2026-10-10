// Mirrors the allowlisted native launch contract in backend/broker/instance_runner.py.
// ActPlane lower_exec matches the executable basename (comm), not a script's path.
export function agentPolicySource(target){
 if(!target?.id||target.mode!=='controlled')throw Error('请选择受控 Agent。');
 const entry=target.runtime?.executable||target.executable||'';
 const type=target.agent_type||target.product;
 let pattern;
 if(type==='dsh')pattern='**/node';
 else if(type==='hermes')pattern='**/python';
 else {const base=entry.split('/').at(-1);if(!entry.startsWith('/')||!base||/[\u0000-\u001f"\\*]/.test(entry))throw Error('尚未取得此 Agent 的启动程序，请检查连接。');pattern='**/'+base;}
 return {id:target.id,name:type==='dsh'?'DeepSeek Harness':type==='hermes'?'Hermes':target.name||'Agent',pattern,entry, basis:type==='dsh'||type==='hermes'?'controlled-launch-profile':'registered-entry',connected:!!target.connected};
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
