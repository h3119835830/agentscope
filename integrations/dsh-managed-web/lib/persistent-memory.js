import {createHash} from 'node:crypto';

// Observe only the configured memory provider's resolved contribution. No other
// system section, tool schema, compaction or private session stream is exported.
export function persistentMemoryObservation(assembly,{sessionId,provider,seq}) {
 if(!sessionId||!provider)return null;
 const sections=(assembly.sections||[]).filter(section=>section.name==='memory');
 if(sections.length!==1)return null;
 const section=sections[0];
 const marker='<summary_snapshot>',end='</summary_snapshot>';
 const start=section.text.indexOf(marker),finish=section.text.lastIndexOf(end);
 if(start<0||finish<start)return null;
 if(section.interpolate!==false)throw Error('Memory observation requires literal provider text.');
 const content=section.text.slice(start+marker.length,finish).trim();
 if(Buffer.byteLength(content)>16384)throw Error('Persistent memory exceeds the observation budget.');
 const content_hash=createHash('sha256').update(content).digest('hex');
 return {kind:'persistent_memory_loaded',session_id:sessionId,event_key:'memory:'+sessionId+':'+content_hash,
  provider,source_ref:'summary.md',category:'persistent_memory',type:'memory/loaded',seq,content,content_hash};
}
