// Local UI acceptance: serve the reviewed build and forward only named GET reads.
import http from 'node:http';
import {readFileSync,existsSync} from 'node:fs';
import {resolve,extname,sep} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=fileURLToPath(new URL('../',import.meta.url)),dist=resolve(root,'frontend/dist');
const reads=new Set(['/api/status','/api/console/agents','/api/console/summary','/api/policy-templates','/api/security/system/policy-library','/api/security/system/execution-capabilities']);
const types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2'};
let blockedWrites=0,forwardedReads=0;
const server=http.createServer(async(req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1');
 const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(value));};
 if(!['GET','HEAD'].includes(req.method)){blockedWrites++;return json({detail:'模板详情验收页仅供查看。'},405);}
 if(url.pathname==='/__acceptance')return json({readOnly:true,blockedWrites,forwardedReads,forwardedWrites:0});
 if(reads.has(url.pathname)){
  try{const upstream=await fetch('http://127.0.0.1:18003'+url.pathname+url.search,{signal:AbortSignal.timeout(10000)});forwardedReads++;res.writeHead(upstream.status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});return res.end(await upstream.text());}
  catch{return json({detail:'正式服务的只读数据暂时不可达。'},502);}
 }
 if(url.pathname.startsWith('/api/'))return json({detail:'此详情验收页未接入该接口。'},501);
 const file=resolve(dist,url.pathname==='/'?'index.html':url.pathname.slice(1));
 if(!file.startsWith(dist+sep)||!existsSync(file))return json({detail:'Not found'},404);
 let body=readFileSync(file);
 if(file===resolve(dist,'index.html'))body=body.toString().replace('<body>','<body><div style="padding:8px 18px;background:#edf3ff;color:#496789;font:12px sans-serif;text-align:center">只读模板详情验收 · 读取正式服务数据 · 禁止保存、审批和应用</div>');
 res.writeHead(200,{'Content-Type':types[extname(file)]||'application/octet-stream','Cache-Control':'no-store'});res.end(body);
});
server.listen(18177,'127.0.0.1',()=>console.log('Template details preview: http://127.0.0.1:18177/?view=strategies&systemTab=policies'));
