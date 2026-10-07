import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
async function loadComponent(file) {
 const result=await build({entryPoints:[join(base,file)],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
 const module=new Module(join(base,'.archive-domain-test.cjs'));module.paths=Module._nodeModulePaths(base);module._compile(result.outputFiles[0].text,join(base,'.archive-domain-test.cjs'));
 return module.exports;
}
const {default:DomainGraph}=await loadComponent('DomainGraph.jsx');
const {default:ArchiveDomains,archiveDomainPath}=await loadComponent('ArchiveDomains.jsx');
const graph={task_id:'t',version:4,versions:[{version:4}],live:false,nodes:[
 {key:'v4:task',kind:'domain',role:'task',domain_id:44,title:'任务域',labels:['source'],live:true},
 {key:'v4:runner:123',kind:'process',role:'runner',pid:123,title:'历史 runner 123',live:true},
 {key:'unrecorded',kind:'process',role:'watch',pid:null,title:'未记录进程'}
],edges:[{from:'v4:task',to:'v4:runner:123',kind:'binding',label:'绑定'}]};
const render=props=>renderToStaticMarkup(React.createElement(DomainGraph,{graph,files:{records:[]},fresh:true,...props}));
test('archive graph renders recorded historical PID without live verification or invented PID',()=>{
 const html=render({historical:true,graph:{...graph,live:true}});
 assert.match(html,/历史 PID/);assert.match(html,/123/);assert.doesNotMatch(html,/未记录进程|绑定已核验|class="live"|域已核验/);assert.match(html,/不代表当前在线/);
});
test('default live graph keeps excluding processes when graph is not live or observation is stale',()=>{
 assert.doesNotMatch(render({}),/历史 runner 123/);
 assert.doesNotMatch(render({graph:{...graph,live:true},fresh:false}),/历史 runner 123/);
 assert.match(render({graph:{...graph,live:true}}),/历史 runner 123/);
 assert.match(render({graph:{...graph,live:true}}),/绑定已核验/);
});
test('archive request paths remain task scoped and encoded',()=>{
 assert.equal(archiveDomainPath('task/1',null),'/api/tasks/task%2F1/archive/domains');
 assert.equal(archiveDomainPath('task/1',4),'/api/tasks/task%2F1/archive/domains?version=4');
 assert.equal(archiveDomainPath('task/1',null,'v4:task'),'/api/tasks/task%2F1/archive/domains/v4%3Atask');
});
test('archive graph starts folded with no rendered evidence or API call',()=>{
 let calls=0;const html=renderToStaticMarkup(React.createElement(ArchiveDomains,{task:'t',api:()=>{calls++;}}));
 assert.match(html,/历史域、进程与 DSL/);assert.doesNotMatch(html,/graph-canvas|record-code|<details[^>]*open/);assert.equal(calls,0);
});
