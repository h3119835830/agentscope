import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {dirname,join} from 'node:path';
import {build} from 'esbuild';
import React from 'react';
const require=createRequire(import.meta.url),Module=require('node:module'),base=dirname(fileURLToPath(import.meta.url));
function elements(tree){if(!tree||typeof tree!=='object')return [];return [tree,...[tree.props?.children].flat(Infinity).flatMap(elements)];}
async function harness(){
 const built=await build({entryPoints:[join(base,'AgentPolicyScene.jsx')],bundle:true,platform:'node',format:'cjs',external:['react'],write:false});
 const states=[],refs=[];let index=0,refIndex=0;
 const react={...React,useState:init=>{const i=index++;if(!(i in states))states[i]=typeof init==='function'?init():init;return [states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];},useRef:init=>{const i=refIndex++;return refs[i]||={current:init};},useEffect:()=>{}};
 const mod=new Module(join(base,'.scene-test.cjs'));mod.paths=Module._nodeModulePaths(base);const original=mod.require.bind(mod);mod.require=id=>id==='react'?react:original(id);mod._compile(built.outputFiles[0].text,join(base,'.scene-test.cjs'));
 return props=>{index=0;refIndex=0;return mod.exports.default(props);};
}
const context={ready:true,session_id:'session-a',context_hash:'a'.repeat(64)},target={id:'agent-a'};
const suggestion={id:'1',title:'保护配置',policy:'禁止读取 .env 文件。',evidence:[{relative_path:'task.md',quote:'Do not read .env'}]};
const scene={id:'b'.repeat(32),instance_id:'agent-a',session_id:'session-a',status:'completed',current:true,read_only:true,summary:'测试任务',recommendations:[suggestion],sources:[{relative_path:'task.md'}],file_count:1};
test('reading starts only on an explicit click and cannot save or approve a policy',async()=>{
 const render=await harness(),writes=[];let saved;
 const props={target,context,api:async()=>({}),post:async(path,body)=>{writes.push({path,body});return {...scene,status:'queued'};},onScene:value=>saved=value};
 let tree=render(props);assert.equal(writes.length,0);
 await elements(tree).find(e=>e.type==='button'&&e.props.children==='读取场景').props.onClick();
 assert.equal(writes.length,1);assert.equal(writes[0].path,'/api/agent-instances/agent-a/policy-scenes');
 assert.equal(writes[0].body.session_id,'session-a');assert.equal(saved.status,'queued');
});
test('adoption checks fresh evidence and only fills the composer',async()=>{
 const render=await harness();let adopted='',writes=0,fresh=scene;
 const props={target,context,scene,api:async()=>fresh,post:async()=>writes++,onScene:()=>{},onAdopt:value=>adopted=value};
 let tree=render(props);elements(tree).find(e=>e.props['aria-expanded']===false).props.onClick();tree=render(props);
 fresh={...scene,current:false};await elements(tree).find(e=>e.props.children==='采用建议').props.onClick();assert.equal(adopted,'');
 fresh=scene;tree=render(props);await elements(tree).find(e=>e.props.children==='采用建议').props.onClick();assert.equal(adopted,suggestion.policy);assert.equal(writes,0);
});
test('empty, loading, stale and failed states remain readable and cannot be adopted',async()=>{
 for(const value of [null,{...scene,status:'running'}, {...scene,current:false,message:'请重新读取'}, {...scene,status:'failed',recommendations:[]}]){
  const render=await harness(),props={target,context,scene:value,onScene:()=>{},onAdopt:()=>{},api:async()=>({}),post:async()=>({})};
  let tree=render(props);const toggle=elements(tree).find(e=>e.props['aria-expanded']===false);if(toggle)toggle.props.onClick();tree=render(props);
  const adopt=elements(tree).find(e=>e.props.children==='采用建议');if(adopt)assert.equal(adopt.props.disabled,true);
 }
});
