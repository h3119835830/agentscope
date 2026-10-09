export const actionLabels={read:'读取',write:'修改与删除',tool:'使用工具',network:'连接 IPv4',behavior:'行为约定'};
const effectLabels={allow:'允许',deny:'禁止',confirm:'须经确认'};
export const networkSentence=value=>value==='disabled'?'禁止模型和外部网络连接，保留本机控制端。':'允许本机控制端、DNS 和启动层解析的模型 IPv4 连接。';
export function displayTarget(target,resources=[]){
 const base=resources.find(p=>target===p||target.startsWith(p+'/'));
 if(!base)return target;
 const name=base.split('/').filter(Boolean).at(-1)||base;
 const unique=resources.filter(p=>p.split('/').filter(Boolean).at(-1)===name).length===1;
 return (unique?name:base)+target.slice(base.length);
}
export function ruleSentence(rule,resources=null,includeNote=true){
 if(rule.action==='behavior')return rule.text;
 const target=resources?displayTarget(rule.target,resources):rule.target;
 return (effectLabels[rule.effect]||rule.effect)+(actionLabels[rule.action]||rule.action)+'「'+target+'」'+(includeNote&&rule.text?'；'+rule.text:'。');
}
export function replaceRule(policy,index,rule){
 const candidate=structuredClone(policy);
 if(index===null){candidate.rules.push(structuredClone(rule));return candidate;}
 if(!Number.isInteger(index)||index<0||index>=candidate.rules.length)throw Error('规则已经变化，请重新选择');
 candidate.rules[index]=structuredClone(rule);return candidate;
}
export function removeRule(policy,index){
 if(!Number.isInteger(index)||index<0||index>=policy.rules.length)throw Error('规则已经变化，请重新选择');
 return {...structuredClone(policy),rules:policy.rules.filter((_,i)=>i!==index).map(r=>({...r}))};
}
export function policyChanges(before,after){
 const key=r=>JSON.stringify([r.action,r.target,r.effect,r.text||'']);
 const subtract=(left,right)=>{const rest=right.map(key);return left.filter(rule=>{const i=rest.indexOf(key(rule));if(i<0)return true;rest.splice(i,1);return false;});};
 return [
  ...subtract(before.rules,after.rules).map(rule=>({operation:'删除',sentence:ruleSentence(rule)})),
  ...subtract(after.rules,before.rules).map(rule=>({operation:'新增',sentence:ruleSentence(rule)})),
  ...(before.network!==after.network?[{operation:'网络调整',sentence:networkSentence(after.network)}]:[]),
 ];
}
export const sameBaseline=(row,draft)=>row.generation===draft.generation&&row.policy_hash===draft.base_hash;
export function proposalDraft(row,policy){
 return {policy:structuredClone(policy),generation:row.generation,base_hash:row.policy_hash};
}
