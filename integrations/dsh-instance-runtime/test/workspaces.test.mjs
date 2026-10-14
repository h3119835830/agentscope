import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {projectWorkspace,filesForWorkspace} from '../lib/workspaces.js';
test('native workspace projection includes a workspace before its first session',()=>{assert.deepEqual(projectWorkspace({workspaceId:'w',path:'/project/a',title:'A',sessionIds:[]}),{id:'w',path:'/project/a',name:'A',session_ids:[]});});
test('workspace inventory follows native ownership and preserves policy and symlink boundaries',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'as-native-files-'));
 try{
  await fs.mkdir(path.join(root,'input'));await fs.writeFile(path.join(root,'input','orders.csv'),'fake');await fs.mkdir(path.join(root,'vault'));await fs.writeFile(path.join(root,'vault','token.txt'),'fake');await fs.symlink('/etc',path.join(root,'alias'));
  const workspaces=[{workspaceId:'w',path:root,title:'A',sessionIds:[]}];
  const inventory=await filesForWorkspace(workspaces,'w','',[root],[path.join(root,'vault')]);
  assert.equal(inventory.files.find(f=>f.name==='input').kind,'directory');assert.equal(inventory.files.find(f=>f.name==='vault').blocked,true);
  assert.equal((await filesForWorkspace(workspaces,'w','input',[root])).files[0].name,'orders.csv');
  for(const [id,relative,roots] of [['other','',[root]],['w','..',[root]],['w','alias',[root]],['w','',['/unrelated']]])await assert.rejects(filesForWorkspace(workspaces,id,relative,roots));
  await assert.rejects(filesForWorkspace(workspaces,'w','vault',[root],[path.join(root,'vault')]));
 }finally{await fs.rm(root,{recursive:true,force:true})}
});
