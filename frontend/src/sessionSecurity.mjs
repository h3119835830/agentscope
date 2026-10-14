export const scopeNames={system:'系统继承',agent:'Agent 继承',workspace:'工作区继承',session:'本会话'};
export const actionNames={read:'文件读取',write:'文件写入与删除',tool:'工具使用',network:'网络连接',behavior:'行为指导'};
export const effectNames={allow:'允许',deny:'禁止',confirm:'确认后允许',block:'阻止',notify:'记录并提醒',kill:'终止进程'};
export function impact(scope){return scope==='system'?'全部受控 Agent 及其工作区与会话':'此 Agent 的全部工作区、会话和子进程';}
export function changeRequest(view,draft,input,requestKey){
 if(!view?.can_propose||view.basis_hash!==draft.basisHash)throw Error('策略或运行环境已变化，请刷新后重新配置。');
 const scope=draft.control?.scope||input.scope;
 if(!['system','agent'].includes(scope))throw Error(view.session_local_reason||'当前不支持局部应用。');
 if(!input.ack)throw Error('请先核对所属层和全部影响范围。');
 const operation=draft.operation||'add',selected=draft.control;
 if(selected&&!view.controls.some(c=>c.id===selected.id&&c.scope===scope))throw Error('约束已变化，请重新读取。');
 if(operation==='disable'&&!selected?.can_disable)throw Error(selected?.reason||'此约束不能停用。');
 if(operation==='replace'&&!selected?.can_configure)throw Error(selected?.reason||'此约束不能通过表单修改。');
 const body={scope,operation,basis_hash:draft.basisHash,constraint_id:selected?.id||null,request_key:requestKey,acknowledge_scope:true};
 if(operation==='disable')return body;
 if(selected?.kind==='network_mode')return {...body,network:input.network};
 const {action,effect,target='',text=''}=input;
 if(!actionNames[action]||action==='behavior'&&!text.trim()||action!=='behavior'&&!target.trim())throw Error(action==='behavior'?'请填写行为约定。':'请选择操作并填写保护对象。');
 return {...body,rule:{action,effect:action==='behavior'?'deny':effect,target:action==='behavior'?'':target.trim(),text:text.trim()}};
}
export function visibleControls(view,{scope='',kind=''}={}){return (view?.controls||[]).filter(c=>(!scope||c.scope===scope)&&(!kind||c.kind===kind));}
