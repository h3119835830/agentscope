// Open the native Agent instance home page; no session navigation or creation.
function createAgentHomeLauncher({adapter,browser}){
  const inFlight=new Map();
  function open(ref){
    if(!ref?.instanceId)return Promise.reject(new Error('尚未绑定真实 Agent 实例首页。'));
    const instanceRef={instanceId:ref.instanceId},key=ref.instanceId;
    if(inFlight.has(key))return inFlight.get(key);
    const target=browser.open('about:blank','_blank');
    if(!target)return Promise.reject(new Error('浏览器阻止打开原生页面；未启动执行端。'));
    target.opener=null;
    const operation=Promise.resolve().then(async()=>{
      const state=await adapter.inspect(instanceRef);
      if(state.instanceId!==ref.instanceId)throw new Error('Agent 实例身份不一致。');
      let kind='reused';
      if(state.executor==='stopped'){
        if(state.startAllowed!==true)throw new Error('启动前需完成安全检查或审批。');
        await adapter.start(instanceRef,state.revision);kind='started';
      }else if(['idle','running'].includes(state.executor)){
        if(state.connection==='disconnected'){await adapter.reconnect(instanceRef);kind='reconnected';}
        else if(state.connection!=='connected')throw new Error('连接状态尚未确认，暂不重复启动。');
      }else throw new Error('执行端状态尚未确认，暂不重复启动。');
      const entry=await adapter.resolveHomeEntry(instanceRef);
      if(entry.instanceId!==ref.instanceId||entry.scope!=='instance')throw new Error('首页入口与请求的 Agent 实例不一致。');
      const url=new URL(entry.url);
      if(url.protocol!=='http:'||url.hostname!=='127.0.0.1'||url.username||url.password)throw new Error('原生入口未通过本机校验。');
      if(target.closed)throw new Error('原生标签已关闭，请重新打开。');
      target.location.replace(url.href);
      return {instanceId:ref.instanceId,scope:'instance',kind};
    }).catch(error=>{target.close();throw error;}).finally(()=>inFlight.delete(key));
    inFlight.set(key,operation);return operation;
  }
  return {open};
}
if(typeof module!=='undefined'&&module.exports)module.exports={createAgentHomeLauncher};
