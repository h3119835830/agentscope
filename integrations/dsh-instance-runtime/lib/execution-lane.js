// The root process owns one inherited kernel tag. Serialize top-level bodies;
// nested native tool calls keep the parent's identity.
export function createExecutionLane(){
 let tail=Promise.resolve();
 return async signal=>{
  let release;const prior=tail.catch(()=>{}),ticket=new Promise(resolve=>release=resolve);
  tail=prior.then(()=>ticket);
  let abort;
  const cancelled=new Promise(resolve=>{abort=()=>resolve(false);signal.addEventListener('abort',abort,{once:true});});
  try{
   if(signal.aborted){release();return null;}
   const ready=await Promise.race([prior.then(()=>true),cancelled]);
   if(!ready||signal.aborted){release();return null;}
   return release;
  }finally{signal.removeEventListener('abort',abort);}
 };
}
