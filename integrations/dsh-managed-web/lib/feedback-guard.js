// A denial invalidates tools already planned in the same parallel batch. Bodies
// must finish/cancel so the SDK can reach post hooks and admit the new context.
export function createFeedbackGuard(){
 let generation=0;const pending=new Set();
 return {
  ticket:()=>generation,
  check(ticket){if(ticket!==generation||pending.size)throw Error('操作反馈尚未进入上下文，或本批次计划已失效。请依据 because 重新规划下一步。');},
  block(events){let changed=false;for(const event of events)if(!pending.has(event.feedback_id)){pending.add(event.feedback_id);changed=true;}if(changed)generation++;},
  admit(feedback){
   const prefix='[ActPlane operation feedback] ';
   if(!feedback.startsWith(prefix))return;
   let events;try{events=JSON.parse(feedback.slice(prefix.length).split('\n')[0]);}catch{return;}
   for(const event of Array.isArray(events)?events:[events])pending.delete(event.feedback_id);
  },
  pending:()=>[...pending],
 };
}
