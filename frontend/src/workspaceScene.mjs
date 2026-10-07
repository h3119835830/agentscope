const readStates=new Set(['queued','running','completed','failed','interrupted']);
const hash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const nonempty=value=>typeof value==='string'&&value.trim().length>0;

export function sceneReadPath(workspace,id=''){
 const base=`/api/agent-workspaces/${encodeURIComponent(workspace)}/scene-reads`;
 return id?`${base}/${encodeURIComponent(id)}`:base;
}
export function sceneContextKey(context){
 return JSON.stringify([context.workspaceId,context.agentId,context.manifestHash,context.sourceGeneration||'',(context.supplement||'').trim()]);
}
export function sceneReadMatches(read,input,current){
 return !!read&&!!input&&read.workspace_id===current.workspaceId&&read.manifest_hash===current.manifestHash&&(!current.sourceGeneration||read.source_generation===current.sourceGeneration)&&sceneContextKey(input)===sceneContextKey(current);
}
export function validateSceneRead(read,context){
 if(!read||!nonempty(read.id)||!readStates.has(read.status)||read.read_only!==true||(read.task_id!==null&&!nonempty(read.task_id)))
  throw new Error('场景读取返回内容不完整，请重新检查读取状态。');
 if(read.workspace_id!==context.workspaceId||read.manifest_hash!==context.manifestHash||(context.sourceGeneration&&read.source_generation!==context.sourceGeneration))
  throw new Error('工作区或文件版本已变化，请重新读取场景。');
 if(read.status==='completed'&&(!read.draft||!['ready','needs_clarification'].includes(read.draft.state)))
  throw new Error('Agent 未返回明确的任务识别结果，请重新读取场景。');
 if(read.status==='completed'&&read.draft.state==='ready'&&(!nonempty(read.draft.name)||!nonempty(read.draft.goal)||!hash(read.draft_hash)))
  throw new Error('Agent 返回的任务目标或结果凭据不完整，请重新读取场景。');
 return read;
}
export function canUseSceneDraft(read,input,current){
 return sceneReadMatches(read,input,current)&&read.read_only===true&&read.task_id===null&&read.status==='completed'&&read.draft?.state==='ready'&&nonempty(read.draft.name)&&nonempty(read.draft.goal)&&hash(read.draft_hash);
}
export function sceneCreateBody(read,input,current){
 if(!canUseSceneDraft(read,input,current))throw new Error('请先读取当前工作区并明确本次目标。');
 return {read_id:read.id,draft_hash:read.draft_hash,expected_manifest_hash:current.manifestHash};
}
export function sceneReadLabel(read){
 if(read?.task_id)return '已用于创建任务';
 if(read?.status==='completed')return read.draft?.state==='ready'?'已识别任务目标':'需要补充本次目标';
 return ({queued:'等待读取场景',running:'Agent 正在读取场景',failed:'场景读取失败',interrupted:'场景读取已中断'})[read?.status]||'';
}
export function sceneErrorMessage(value){
 return ({scene_read_failed:'Agent 未完成场景读取，请重新尝试。',scene_read_interrupted:'场景读取已中断，请重新读取。',scene_manifest_changed:'工作区文件已变化，请刷新文件清单并重新读取。',scene_source_generation_changed:'Agent 连接实例已变化，请刷新工作区并重新读取。',scene_read_already_adopted:'此读取结果已用于创建任务，请打开已有任务。'})[value]||(typeof value==='string'?value:'场景读取暂不可用，请重新尝试。');
}
export function sceneEvidence(draft,supplement=''){
 const evidence=(Array.isArray(draft?.evidence)?draft.evidence:[]).map(item=>({path:item.relative_path==='user:supplement'?'本次输入':item.relative_path,quote:item.quote,kind:item.relative_path==='user:supplement'?'user_supplement':'scene_file'}));
 if(supplement&&!evidence.some(item=>item.kind==='user_supplement'))evidence.push({path:'本次输入',quote:supplement,kind:'user_supplement'});
 return evidence;
}
export function sceneStorageKey(context){return `agentscope.scene-read.v1:${encodeURIComponent(context.agentId)}:${encodeURIComponent(context.workspaceId)}`;}
export function sceneStoredValue(context,readId=null){
 return JSON.stringify({version:1,workspaceId:context.workspaceId,agentId:context.agentId,manifestHash:context.manifestHash,sourceGeneration:context.sourceGeneration||'',supplement:(context.supplement||'').trim(),read_id:readId});
}
export function restoreSceneContext(raw,current){
 try{
  const value=JSON.parse(raw);
  if(value?.version!==1||value.workspaceId!==current.workspaceId||value.agentId!==current.agentId||!hash(value.manifestHash)||typeof value.supplement!=='string'||value.supplement.length>8000||(value.read_id!==null&&(!nonempty(value.read_id)||value.read_id.length>200)))return null;
  const stale=value.manifestHash!==current.manifestHash||!!current.sourceGeneration&&value.sourceGeneration!==current.sourceGeneration;
  return {context:{...current,supplement:value.supplement},read_id:stale?null:value.read_id,stale};
 }catch{return null;}
}
