// Only presentation reads use the product projection. Original APIs and records
// stay intact for the separate operations client.
export function productReadUrl(url,method='GET'){
 if(method!=='GET')return url;
 return url.replace(/^\/api\/agent-instances(?=\/|\?|$)/,'/api/console/agents')
   .replace(/^\/api\/security\/system\/dsl(?=\?|$)/,'/api/console/security/system/dsl')
   .replace(/^\/api\/sessions(?=\?|$)/,'/api/console/sessions')
   .replace(/^\/api\/history\/records(?=\?|$)/,'/api/console/history/records')
   .replace(/^\/api\/history\/generations\/page(?=\?|$)/,'/api/console/history/generations/page')
   .replace(/^\/api\/task-archives(?=\?|$)/,'/api/console/task-archives');
}
export const hasValue=value=>value!==null&&value!==undefined&&value!=='';
export const userPolicies=records=>(records||[]).filter(r=>r.source_kind!=='legacy_generated');
export const unknownAgentSummary=summary=>summary?{...summary,stats:{...summary.stats,verified_agents:0},agents:summary.agents.map(a=>({...a,connected:false,active:false,pid:null,can_open:false,status:'unknown'}))}:null;
