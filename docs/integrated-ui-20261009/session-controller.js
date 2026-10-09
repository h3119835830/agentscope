// Open the Agent's native UI; never render chat or substitute an Agent home page.
function createNativeSessionLauncher({adapter,browser}){
  const inFlight=new Map();
  function open(ref){
    if(!ref?.instanceId||!ref?.sessionId)return Promise.reject(new Error('尚未绑定真实 Agent 会话。'));
    const key=ref.instanceId+'\n'+ref.sessionId;
    if(inFlight.has(key))return inFlight.get(key);
    const target=browser.open('about:blank','_blank');
    if(!target)return Promise.reject(new Error('浏览器阻止打开原生页面；未启动执行端。'));
    target.opener=null;
    const operation=Promise.resolve().then(async()=>{
      const state=await adapter.inspect(ref);
      if(state.instanceId!==ref.instanceId||state.sessionId!==ref.sessionId)throw new Error('原生会话身份不一致。');
      if(state.sessionNavigation!==true)throw new Error('当前 Agent 仅支持实例入口，尚不支持定位指定会话。');
      let kind='reused';
      if(state.executor==='stopped'){
        if(state.resumeAllowed!==true)throw new Error('恢复前需完成安全检查或审批。');
        await adapter.resume(ref,state.revision);kind='resumed';
      }else if(['idle','running'].includes(state.executor)){
        if(state.connection==='disconnected'){await adapter.reconnect(ref);kind='reconnected';}
        else if(state.connection!=='connected')throw new Error('连接状态尚未确认，暂不重复启动。');
      }else throw new Error('执行端状态尚未确认，暂不重复启动。');
      const entry=await adapter.resolveSessionEntry(ref);
      if(entry.instanceId!==ref.instanceId||entry.sessionId!==ref.sessionId||entry.scope!=='session')throw new Error('原生入口未定位到请求的会话。');
      const url=new URL(entry.url);
      if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.username||url.password)throw new Error('原生入口未通过本机校验。');
      if(target.closed)throw new Error('原生标签已关闭，请重新打开。');
      target.location.replace(url.href);
      return {instanceId:ref.instanceId,sessionId:ref.sessionId,kind};
    }).catch(error=>{target.close();throw error;}).finally(()=>inFlight.delete(key));
    inFlight.set(key,operation);return operation;
  }
  return {open};
}
if(typeof module!=='undefined'&&module.exports)module.exports={createNativeSessionLauncher};
