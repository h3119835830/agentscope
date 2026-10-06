// Only public content crosses the managed control/evidence seam.
export function publicEvent(sessionId,event,currentTurn=0) {
 const type=event.type,data=event.data||{};
 if(!['turn/start','turn/end','user/message','assistant/message'].includes(type))return null;
 if(type==='user/message' && !['user','user-question-reply'].includes(data.source?.kind))return null;
 const message=type==='assistant/message'?data.message:type==='user/message'?data:null;
 const text=(message?.content||[]).filter(x=>x.type==='text').map(x=>x.text).join('\n');
 return {type,seq:event.seq,turn:data.turn??currentTurn,text};
}
export function restorePublicSession(session) {
 let turn=0;const events=[];
 for(const event of session.snapshotEvents()) {
  if(event.type==='turn/start')turn=event.data.turn;
  const item=publicEvent(session.id,event,turn);if(item)events.push(item);
 }
 return {turn,events:events.slice(-300)};
}

export function publicQuestionAnswer(session,event) {
 if(event.type!=='tool/result' || !event.data?.message || event.data.message.isError)return null;
 const callId=event.data.message.toolCallId;
 const call=session.snapshotEvents().find(x=>x.type==='tool/call' && x.data.callId===callId && x.data.name==='ask_user_question');
 if(!call)return null;
 let answer;try{answer=JSON.parse((event.data.message.content||[]).filter(x=>x.type==='text').map(x=>x.text).join('\n'));}catch{return null;}
 if(!Array.isArray(answer.answers))return null;
 let args;try{args=JSON.parse(call.data.arguments);}catch{return null;}
 return {call_id:String(callId),text:JSON.stringify({source:'native_user_question',questions:args.questions,answers:answer.answers})};
}

export function acceptedUserMessages(session,event) {
 if(event.type!=='agent/inbox/spliced'||event.data?.outcome==='canceled')return [];
 return (event.data?.inserted||[]).filter(message=>message.source?.kind==='user'&&typeof message.source.rpcId==='string'&&message.source.rpcId).map(message=>({
  kind:'user_message_accepted',session_id:session.id,request_id:message.source.rpcId,
  event_key:'accepted:'+session.id+':'+message.source.rpcId,
  text:(message.content||[]).filter(part=>part.type==='text').map(part=>part.text).join('\n')
 }));
}
