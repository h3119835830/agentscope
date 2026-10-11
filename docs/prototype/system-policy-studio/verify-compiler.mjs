// Read-only compiler acceptance. No broker, attach, load, or Agent execution.
import {spawnSync} from 'node:child_process';
import {writeFileSync} from 'node:fs';
import {catalog,ruleDsl} from './model.mjs';
const binary='/opt/agentscope/actplane/target/release/actplane',checks=[];
for(const template of catalog)for(const effect of ['block','notify','kill']){
 const config={...template,effect,values:template.values||'/var/lib/agentscope-ui-check/'+template.id};
 const dsl='source AGENT = exec "**/node"\n\n'+ruleDsl(config);
 const run=spawnSync(binary,['compile','--rule',dsl,'--json'],{encoding:'utf8',timeout:15000});
 let report;try{report=JSON.parse(run.stdout);}catch{throw Error(template.id+' '+effect+': '+run.stderr+' '+run.stdout);}
 if(run.status!==0||!report.ok)throw Error(template.id+' '+effect+': '+JSON.stringify(report));
 const clauses=report.backend_support?.clauses||[];
 if(!clauses.length||clauses.some(c=>!c.supported))throw Error('Unsupported static clause: '+template.id+' '+effect+' '+JSON.stringify(report.backend_support));
 checks.push({id:template.id,effect,compiler_ok:report.ok,clauses:clauses.length,static_supported:true});
}
writeFileSync('/tmp/system-policy-ui-compiler.json',JSON.stringify({compiler:binary,checks,loaded:false},null,2)+'\n');
console.log(JSON.stringify({passed:checks.length,loaded:false,report:'/tmp/system-policy-ui-compiler.json'}));
