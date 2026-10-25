import {readFileSync} from 'node:fs';
import {Type} from '@earendil-works/pi-ai';
import {defineTool,type ExtensionAPI} from '@earendil-works/pi-coding-agent';
export default function(pi:ExtensionAPI){
 pi.on('before_provider_request',async(event)=>({...event.payload,thinking:{type:'disabled'}}));
 const tools=JSON.parse(readFileSync('/home/pi/tools.json','utf8'));
 for(const tool of tools)pi.registerTool(defineTool({name:tool.name,label:tool.display_name||tool.name,
  description:tool.description,parameters:Type.Unsafe(tool.input_schema),
  async execute(_id,params,signal){
   const response=await fetch(process.env.AGENTSCOPE_PI_BRIDGE!,{method:'POST',signal,
    headers:{'Content-Type':'application/json',Authorization:'Bearer '+process.env.AGENTSCOPE_PI_TOKEN},
    body:JSON.stringify({tool:tool.name,arguments:params})});
   return {content:[{type:'text',text:await response.text()}],isError:!response.ok};
  }}));
}
