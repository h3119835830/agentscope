export const sceneBusy=scene=>['queued','running'].includes(scene?.status);
export const sceneUsable=scene=>Boolean(scene?.status==='completed'&&scene.current&&scene.read_only);
export function sceneInput(context,key){
 if(!context?.ready||!context.session_id||!context.context_hash)throw Error('请选择已核验的 Agent 会话。');
 return {session_id:context.session_id,context_hash:context.context_hash,request_key:key};
}
export function sceneForInput(scene,target,context){
 if(!scene)return null;
 if(!sceneUsable(scene))throw Error('请等待场景读取完成；若文件已变化，请重新读取。');
 if(scene.instance_id!==target.id||scene.session_id!==context.session_id)throw Error('场景不属于当前 Agent 和会话，请重新读取。');
 return scene.id;
}
