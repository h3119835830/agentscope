// Loopback-only, read-only replay of saved real responses. No upstream proxy.
import http from 'node:http';
import {readFileSync,writeFileSync,existsSync} from 'node:fs';
import {resolve,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../',import.meta.url)),dist=resolve(root,'frontend/dist');
const evidence=resolve(root,'acceptance/policy-response-ui-20261026');
const original=JSON.parse(readFileSync(resolve(evidence,'live-source.json'),'utf8'));
const agent=JSON.parse(readFileSync(resolve(evidence,'agent-source.json'),'utf8'));
const data=structuredClone(original);
// Legacy display metadata is recovered only from a matching immutable revision.
// This is a replay adapter, not an edit to the frozen source or model output.
function display(g,items){
 for(const snapshot of g.configuration_snapshots||[]){
  const item=items.find(row=>row.id===snapshot.id&&row.revision===snapshot.revision);
  if(item&&!snapshot.execution)snapshot.execution=Object.fromEntries(['requested_operations','effective_operations','effect','reason','coverage_warning'].filter(k=>Object.hasOwn(item,k)).map(k=>[k,item[k]]));
 }
 return g;
}
data.generations=data.generations.map(g=>display(g,data.items));
const multi=JSON.parse(readFileSync(resolve(root,'acceptance/policy-investigation-20261026/e3/results/real-directory-gate.json'),'utf8')).result;
const multiData={...data,items:multi.items,generations:[display(structuredClone(multi),multi.items)]};
const multiAgent={id:multi.scope_id,name:'真实项目隔离验收',agent_type:'dsh',mode:'controlled',environment:'wsl',generation:null,gate:'stopped'};
let mutations=0;
const types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2'};
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1'),json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
 if(!['GET','HEAD'].includes(req.method)){mutations++;return json({detail:'隔离预览仅供查看，不生成、审批或应用配置。'},405);}
 if(url.pathname==='/__acceptance')return json({readonly:true,mutations,source_generations:original.generations.length,latest_preflight_items:original.generations.filter(g=>(g.stage||'preflight')==='preflight').at(-1).items.length,multi_items:multi.items.length});
 const replay=new URL(req.headers.referer||'http://127.0.0.1').searchParams.get('replay'),selected=replay==='multi'?multiAgent:agent;
 if(url.pathname==='/api/console/agents')return json({instances:[selected]});
 if(url.pathname==='/api/console/agents/'+selected.id)return json(selected);
 if(url.pathname==='/api/status')return json({});
 if(url.pathname==='/api/console/summary')return json({stats:{},tasks:[]});
 if(url.pathname==='/api/policy-templates')return json(replay==='multi'?multiData:data);
 if(url.pathname.startsWith('/api/'))return json({records:[]});
 const relative=url.pathname==='/'?'index.html':url.pathname.slice(1),file=resolve(dist,relative);
 if(!file.startsWith(dist+sep)||!existsSync(file))return json({detail:'Not found'},404);
 let body=readFileSync(file);
 if(relative==='index.html')body=body.toString().replace('<body>','<body><div style="padding:9px 18px;background:#edf3ff;color:#496789;font:12px sans-serif;text-align:center">隔离预览 · 重放真实保存记录 · 禁止生成、审批和应用</div>');
 res.writeHead(200,{'Content-Type':types[extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(body);
});
server.listen(18176,'127.0.0.1',()=>{
 const receipt={url:'http://127.0.0.1:18176/?view=workbench&policyScope=agent&policyAgent='+agent.id,multi_url:'http://127.0.0.1:18176/?view=workbench&policyScope=agent&replay=multi&policyAgent='+multiAgent.id,readonly:true,source:'live-source.json; E3 real-directory-gate.json',writes_forwarded:false};
 writeFileSync(resolve(evidence,'preview.json'),JSON.stringify(receipt,null,2));console.log(JSON.stringify(receipt));
});
