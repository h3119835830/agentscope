import {readFileSync} from 'node:fs';
import {Type} from '@earendil-works/pi-ai';
import {defineTool,type ExtensionAPI} from '@earendil-works/pi-coding-agent';
export default function(pi:ExtensionAPI){
 pi.on('before_provider_request',async(event)=>({...event.payload,thinking:{type:'disabled'}}));
 const tools=JSON.parse(readFileSync('/home/pi/tools.json','utf8'));
 let finalizeOnly=false;
 for(const tool of tools)pi.registerTool(defineTool({name:tool.name,label:tool.display_name||tool.name,
  description:tool.description,parameters:Type.Unsafe(tool.input_schema),
  async execute(_id,params,signal){
   if(finalizeOnly&&tool.name!=='submit_analysis')return {content:[{type:'text',text:JSON.stringify({
    error:'Tool budget exhausted; submit the current analysis without further tool calls.',code:'tool_budget_exhausted',
    remaining_tool_calls:0,allowed_next_tools:['submit_analysis']})}],isError:true};
   const response=await fetch(process.env.AGENTSCOPE_PI_BRIDGE!,{method:'POST',signal,
    headers:{'Content-Type':'application/json',Authorization:'Bearer '+process.env.AGENTSCOPE_PI_TOKEN},
    body:JSON.stringify({tool:tool.name,arguments:params})});
   const text=await response.text();
   try{const value=JSON.parse(text);if(value?.code==='tool_budget_exhausted'||value?.control?.finalization_required){finalizeOnly=true;pi.setActiveTools(['submit_analysis']);}}catch{}
   return {content:[{type:'text',text}],isError:!response.ok};
  }}));
}
