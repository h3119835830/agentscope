export function flowTime(value){
 if(value===null||value===undefined||value==='')return '时间未记录';
 // Audit nanoseconds are strings to preserve u64 precision in JSON.
 const numeric=/^\d+$/.test(String(value))?Number(value):null;
 const time=new Date(numeric!==null?(numeric>1e15?numeric/1e6:numeric):value);
 return Number.isNaN(time.getTime())?'时间未记录':time.toLocaleString('zh-CN',{hour12:false});
}
export function staleSourceSelections(refs,sources){
 return refs.filter(ref=>!sources.some(s=>!s.archived&&s.id===ref.id&&s.version===ref.version));
}
