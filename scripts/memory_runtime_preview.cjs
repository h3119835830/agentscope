// Read-only acceptance entry for the existing ManagedWorkbench component.
// Uses live isolated API responses; does not alter the product navigation.
const path=require('node:path'),fs=require('node:fs'),http=require('node:http');
const root=path.resolve(__dirname,'../frontend');
const esbuild=require(path.join(root,'node_modules/esbuild'));
const out='/tmp/agentscope-memory-preview-20261026';fs.mkdirSync(out,{recursive:true});
async function main(){
 await esbuild.build({stdin:{contents:`import React from 'react';import{createRoot}from'react-dom/client';
 import './src/styles.css';import './src/prototypeTheme.css';import './src/recordVisuals.css';
 import ManagedWorkbench from './src/ManagedWorkbench.jsx';
 const task=new URLSearchParams(location.search).get('task');
 const api=async p=>{const r=await fetch(p);const j=await r.json();if(!r.ok)throw Error(j.detail||r.status);return j};
 function App(){const[section,setSection]=React.useState('runtime');return <ManagedWorkbench api={api} post={()=>Promise.reject(Error('验收预览只读'))} notify={console.log} task={task} section={section} onSection={setSection} onSelectTask={()=>{}} onCreateTask={()=>{}}/>};createRoot(document.getElementById('root')).render(<App/>);`,resolveDir:root,loader:'jsx'},bundle:true,outfile:out+'/view.js',loader:{'.woff2':'file','.svg':'file'},define:{'process.env.NODE_ENV':'"production"'}});
 if(process.argv.includes('--build-only'))return;
 const html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AgentScope 运行时策略预览</title><link rel="stylesheet" href="/view.css"><div id="root"></div><script src="/view.js"></script></html>';
 http.createServer((req,res)=>{
  if(req.method!=='GET'){res.writeHead(405);res.end();return;}
  if(req.url.startsWith('/api/')){const proxy=http.get('http://127.0.0.1:18005'+req.url,r=>{res.writeHead(r.statusCode,{'content-type':r.headers['content-type']||'application/json'});r.pipe(res)});proxy.on('error',()=>{res.writeHead(502);res.end()});return;}
  const asset=req.url.split('?')[0];if(asset==='/view.js'||asset==='/view.css'){res.setHeader('content-type',asset.endsWith('.css')?'text/css':'text/javascript');fs.createReadStream(out+asset).pipe(res);return;}
  res.setHeader('content-type','text/html;charset=utf-8');res.end(html);
 }).listen(18006,'127.0.0.1',()=>console.log('Read-only live API preview: http://127.0.0.1:18006'));
}
main().catch(e=>{console.error(e);process.exitCode=1});
