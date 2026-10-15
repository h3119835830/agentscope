import {agentName,visibleAgentInstances} from './agentInstancePresentation.mjs';
export function configurationAgentLabel(agent,agents=[]){
 const label=agentName(agent);
 const peers=visibleAgentInstances(agents).filter(a=>a.mode==='controlled'&&agentName(a)===label);
 return peers.length>1?label+' · '+String(agent.id).slice(-6):label;
}
