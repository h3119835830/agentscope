// Product explanations use saved public results and read receipts, never model reasoning.
export function analysisParts(text=''){
 const value=String(text??'').trim();
 if(value.length<=220)return {lead:value,rest:''};
 const end=value.slice(0,220).lastIndexOf('。');
 const cut=end>=40?end+1:220;
 return {lead:value.slice(0,cut),rest:value.slice(cut)};
}
export function referenceFiles(usage={}){
 usage=usage||{};
 const files=[],seen=new Set();
 for(const source of usage.sources||[])for(const path of source.paths||[]){
  const key=JSON.stringify([source.workspace,path]);
  if(!seen.has(key)){seen.add(key);files.push({workspace:source.workspace,path,kind:'workspace'});}
 }
 for(const source of usage.provided_files||[]){
  const key=JSON.stringify(['provided',source.name]);
  if(!seen.has(key)){seen.add(key);files.push({path:source.name,kind:'provided'});}
 }
 return files;
}
export function activitySummary(event){
 const tool=event.tool||'',failed=['denied','rejected','unavailable','failed'].includes(event.status);
 const label=({list_directory:'查看目录',read_files:'读取正文',search_project:'搜索项目',inspect_resource:'核对资源',preview_policy_matches:'验证策略匹配',search_policy_templates:'查找模板'})[tool]||(tool.startsWith('draft_')?'填写模板参数':'工具记录');
 const status=event.status==='unavailable'?'暂不可用':failed?'未完成':tool==='preview_policy_matches'?(event.coverage_checks_passed===true?'样本通过':event.coverage_checks_passed===false?'样本未通过':'已检查'):tool==='read_files'?(event.reused?'已复用已读资料':'已读取'):'已完成';
 return {label,status,location:[event.workspace,event.path,...(event.paths||[])].filter(Boolean).join(' / ')};
}
export function generationOutcome(g){
 if(g.generation_state==='failed')return '本次分析未完成';
 if(g.items?.length)return '本轮生成 '+g.items.length+' 项策略配置';
 if(g.questions?.length)return '需要补充信息';
 if(g.gaps?.length)return '本轮未生成配置，有待解决事项';
 return g.summary?'分析完成，本轮未生成配置':'尚未生成配置';
}
export function responseSentence(g){
 const usage=g.context_usage||{},files=referenceFiles(usage);
 const legacy=g.reference_read?.paths||[];
 const paths=files.length?files.map(f=>f.path):legacy;
 const shown=paths.slice(0,3).map(path=>path.replace(/^\/w\/\d+\//,''));
 const prefix=shown.length?'已读取 '+shown.join('、')+(paths.length>3?' 等 '+paths.length+' 个文件':''):'未读取文件正文，仅依据本轮需求';
 if(g.generation_state==='failed')return prefix+'；本次分析未完成，尚未生成策略。';
 if(g.items?.length)return prefix+'，拟定以下 '+g.items.length+' 项策略：';
 return prefix+(g.questions?.length?'，还需补充信息，暂未生成策略。':'，本轮未生成策略。');
}
export function compactPolicyText(row){
 if(row.unavailable)return '此项配置记录暂不可用。';
 const params=row.parameters||{},fields=row.template.parameters.filter(p=>Object.hasOwn(params,p.key));
 const subjects=fields.filter(p=>['path','endpoint'].includes(p.type));
 const targets=(subjects.length?subjects:fields.filter(p=>['program','lines'].includes(p.type))).map(p=>Array.isArray(params[p.key])?params[p.key].join('、'):String(params[p.key]));
 const execution=row.execution||{},ops=execution.effective_operations||params.operations||[];
 const actions=(Array.isArray(ops)?ops:String(ops).split(',')).map(op=>({open:'读取',read:'读取',write:'修改',unlink:'删除',exec:'执行',connect:'连接'})[op]||op).join('、');
 const effect=execution.effect||params.effect,verb=({block:'禁止',notify:'记录并提醒',kill:'终止命中进程'})[effect];
 const simple=fields.every(p=>['path','endpoint','program','lines','operations','effect'].includes(p.type))&&fields.filter(p=>!['operations','effect'].includes(p.type)).length===1&&!row.template.fixed_fields;
 // Conditional templates retain their name and a condition marker; never
 // flatten a cross-event/lineage check into an unconditional ban.
 const conditions=fields.filter(p=>!['path','endpoint','operations','effect'].includes(p.type)).map(p=>p.label+' '+String(params[p.key]));
 const detail=simple&&verb&&actions?verb+(effect==='kill'?'，涉及':'')+actions+(targets.length?' '+targets.join('、'):''):'按模板条件约束 '+(row.template.fixed_fields?Object.values(row.template.fixed_fields).join(' ')+'；':'')+targets.join('、')+(conditions.length?'（'+conditions.join('；')+'）':'')+(verb?'；'+verb:'');
 return row.name+'：'+detail+'。';
}
