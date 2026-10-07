import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {canonicalDirectory,dispatchWorkspaceRequest,generation} from '../lib/index.js';

const root=await fs.mkdtemp('/tmp/atf/bridge-');
const inside=path.join(root,'project');await fs.mkdir(inside);
const outside=path.join(root,'outside');await fs.mkdir(outside);
const calls=[];
const ctx={
 workspaceRegistry:{list:()=>[{id:'native-one',path:inside,title:'Project',sessionIds:['cold-session'],privateReasoning:'must not export'},
                             {id:'outside',path:outside,title:'Outside',sessionIds:[]}]},
 workspaceController:{create:async request=>{calls.push(['create',request]);return {created:true,workspace:{workspaceId:'native-one',...request}};}},
 directoryPickerController:{list:async(target,signal)=>{calls.push(['list',target,signal]);return {path:target,entries:[],crumbs:[]};}},
};
const config={instanceId:'native-dsh'};
const state={config,currentGeneration:'generation-one',roots:[inside],ready:true,revision:4};
const request=operation=>({version:1,nonce:'a'.repeat(48),instance_id:'native-dsh',generation:'generation-one',operation,path:inside});

test('native observer reads registered workspaces and never exports messages or private fields',async()=>{
 const result=await dispatchWorkspaceRequest(ctx,request('observe'),state);
 assert.equal(result.sync_revision,4);
 assert.deepEqual(result.workspaces.map(x=>x.workspaceId),['native-one']);
 assert.equal(result.workspaces[0].privateReasoning,undefined);
 assert.deepEqual(result.workspaces[0].sessionIds,['cold-session']);
 assert.equal(calls.length,0);
});

test('workspace create uses the public workspaceController, no Session or Agent activation',async()=>{
 const result=await dispatchWorkspaceRequest(ctx,request('workspace-create'),state);
 assert.equal(result.created,true);
 assert.deepEqual(calls.at(-1),['create',{path:inside}]);
 assert.equal('sessionController' in ctx,false);
});

test('directory browsing uses native directoryPickerController with cancellation',async()=>{
 const result=await dispatchWorkspaceRequest(ctx,request('directory-list'),state);
 assert.equal(result.path,inside);
 assert.equal(calls.at(-1)[0],'list');
 assert.ok(calls.at(-1)[2] instanceof AbortSignal);
});

test('missing reconnect baseline refuses every operation',async()=>{
 for(const operation of ['observe','workspace-create','directory-list']){
  await assert.rejects(dispatchWorkspaceRequest(ctx,request(operation),{...state,ready:false}),/baseline/);
 }
});

test('unknown operations and altered handshake are refused',async()=>{
 for(const operation of ['shell','prompt','policy-load','session-create']){
  await assert.rejects(dispatchWorkspaceRequest(ctx,request(operation),state),/unavailable/);
 }
 for(const [key,value] of Object.entries({version:0,nonce:'x',instance_id:'other',generation:'old'})){
  await assert.rejects(dispatchWorkspaceRequest(ctx,{...request('observe'),[key]:value},state),/Handshake/);
 }
});

test('path policy rejects traversal, symlink and outside roots',async()=>{
 const alias=path.join(root,'alias');await fs.symlink(inside,alias);
 for(const target of [outside,alias,inside+'/../project','relative']){
  await assert.rejects(canonicalDirectory(target,[inside]));
 }
 assert.equal(await canonicalDirectory(inside,[inside]),inside);
});

test('process start identity changes its generation',()=>{
 assert.notEqual(generation('n',1,'22'),generation('n',1,'23'));
 assert.notEqual(generation('n',1,'22'),generation('n2',1,'22'));
});
