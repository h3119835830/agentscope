// Select exact frozen documents belonging to this approval, never today's draft
// or another policy retained in the candidate's complete scope document set.
export function approvalDslDocuments(data,plan){
 if(plan)return (plan.comparisons||[]).filter(c=>c.after_dsl||c.before_dsl).map((c,i)=>({
  id:String(i),name:c.name,text:c.removal?c.before_dsl:c.after_dsl,removal:!!c.removal}));
 const unit=data.approval_unit;
 if(unit){
  const frozen=data.configuration_records?.find(r=>r.id===unit.configuration_id&&r.revision===unit.revision)?.document;
  const document=frozen||(unit.operation==='disable'?data.previous_documents:data.documents)?.find(d=>d.id===unit.configuration_id);
  return document?.original_dsl?[{id:document.id,name:document.name,text:document.original_dsl,removal:unit.operation==='disable'}]:[];
 }
 const previous=data.previous_documents;
 const changed=(data.documents||[]).filter(d=>!previous?.some(p=>p.id===d.id&&p.original_dsl===d.original_dsl));
 const removed=(previous||[]).filter(d=>!(data.documents||[]).some(p=>p.id===d.id));
 return [...changed.map(d=>({...d,removal:false})),...removed.map(d=>({...d,removal:true}))]
  .filter(d=>d.original_dsl).map(d=>({id:d.id,name:d.name,text:d.original_dsl,removal:d.removal}));
}
