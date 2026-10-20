export function configurationNavigation(scope,id=''){
 if(!scope)throw new Error('请选择准确的配置范围');
 return {page:'strategies',systemTab:'policies',policyScope:scope==='system'?'system':'agent',
  policyAgent:scope==='system'?'':scope,configurationId:id,policyWorkspace:'',policySession:''};
}
