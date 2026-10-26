import { Type } from '@earendil-works/pi-ai';
import { defineTool, type ExtensionAPI } from '@earendil-works/pi-coding-agent';
export default function (pi: ExtensionAPI) {
  pi.on('before_provider_request', async event => ({...(event.payload as Record<string, unknown>),thinking:{type:'disabled'}}));
  const schemas={
    get_task_context:Type.Object({}),list_policy_sources:Type.Object({}),
    read_policy_source:Type.Object({source_id:Type.String()}),
    search_historical_policies:Type.Object({query:Type.String({minLength:1,maxLength:2000})}),
    get_enforcement_capabilities:Type.Object({}),validate_policy_draft:Type.Object({draft:Type.Unknown()}),
    submit_runtime_policy_proposal:Type.Object({proposal_hash:Type.String()}),
  };
  for(const [name,parameters] of Object.entries(schemas)){
    pi.registerTool(defineTool({name,label:name,description:`Read evidence or prepare a restricted runtime candidate using ${name}. Every source and result is bound to this job; tools do not grant permission.`,parameters,
      async execute(_id,args,signal){
        const response=await fetch(process.env.AGENTSCOPE_SCOPE_URL+'/api/generator/tasks/'+process.env.AGENTSCOPE_SCOPE_TASK+'/managed-jobs/'+process.env.AGENTSCOPE_SCOPE_JOB+'/tools/'+name,
          {method:'POST',signal,redirect:'error',headers:{'content-type':'application/json',authorization:'Bearer '+process.env.AGENTSCOPE_SCOPE_TOKEN},body:JSON.stringify({args})});
        return {content:[{type:'text',text:await response.text()}],details:{status:response.status},isError:!response.ok};
      }}));
  }
}
