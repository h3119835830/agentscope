import {createHash} from 'node:crypto';
const publicText=parts=>(parts||[]).filter(part=>part.type==='text').map(part=>part.text).join('\n');
export function runtimeObservation(session,event) {
 const type=event.type,data=event.data||{};let content,category;
 const current=role=>session.deriveMessages?.().filter(message=>message.role===role).map(message=>({text:publicText(message.content),source:message.source?.kind}));
 if(type==='system/message'){category='system_prompt';content=JSON.stringify(current('system')??[{text:publicText(data.message?.content)}]);}
 else if(type==='developer/message'){category='instructions';content=JSON.stringify(current('developer')??[{text:publicText(data.message?.content)}]);}
 else if(type==='request/header'){category='tools';content=JSON.stringify((data.header?.tools||[]).map(tool=>({name:tool.name,parameters:tool.parameters})));}
 else if(type==='compaction/summary'){category='memory';content=publicText(data.summary);}
 else if(type==='compaction/prune'){category='memory_prune';content=JSON.stringify({shadowedSeqs:data.shadowedSeqs});}
 else if(type==='user/message'&&!['user','user-question-reply'].includes(data.source?.kind)) {
  category='context';content=publicText(data.content);
  // Trusted denial delivery is already evaluated from the independent kernel
  // record; echoing it into the context must not create another Pi loop.
  if(content.startsWith('[ActPlane operation feedback]')||content.startsWith('[Execution resumed]'))return null;
  const effective=current('user');if(effective)content=JSON.stringify(effective.filter(item=>!['user','user-question-reply'].includes(item.source)&&!item.text.startsWith('[ActPlane operation feedback]')&&!item.text.startsWith('[Execution resumed]')));
 }else return null;
 if(!content)return null;
 if(Buffer.byteLength(content)>131072)throw Error('Runtime observation exceeds the admitted public-context limit.');
 const hash=createHash('sha256').update(content).digest('hex');
 return {kind:'runtime_observation',session_id:session.id,event_key:'observation:'+session.id+':'+event.seq,category,type,seq:event.seq,content,content_hash:hash};
}
