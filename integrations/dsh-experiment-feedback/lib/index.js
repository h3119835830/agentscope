import fs from 'node:fs/promises';
import {createUserMessage} from '@deepseek-ai/dsh-llm';
export const name='experiment-kernel-feedback';
// One disposable ActPlane run/domain per Agent. The outer root runner filters
// the journal by domain. A host PID cursor cannot be resolved in our PID namespace.
export function apply(ctx) {
  const file=process.env.ACTPLANE_FEEDBACK_FILE;
  let offset=0, pending=Promise.resolve();
  ctx.on('tools/post-execute',async(exec,result,next)=>{
    const downstream=await next();
    if(exec.parent || !file)return downstream;
    let release;
    const previous=pending;pending=new Promise(resolve=>{release=resolve;});
    await previous;
    try {
      await new Promise(resolve=>setTimeout(resolve,250));
      const raw=await fs.readFile(file,'utf8');
      const addition=raw.slice(offset);offset=raw.length;
      if(!addition.trim())return downstream;
      return {...downstream,additionalContexts:[createUserMessage({
        content:[{type:'text',text:'[ActPlane 内核反馈]\n'+addition}],
        source:{kind:'context'}
      }),...(downstream.additionalContexts||[])]};
    } finally {release();}
  });
}
