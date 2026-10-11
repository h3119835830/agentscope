import test from 'node:test';
import assert from 'node:assert/strict';
import {matches,validate,ruleDsl,patterns} from './systemPolicyLibrary.mjs';
const base={id:'x',name:'凭据保护',mode:'suffix',values:'.env',ops:['open'],effect:'block',reason:'使用脱敏配置'};
test('literal suffix, filename and directory have distinct boundaries',()=>{
 assert.deepEqual(['/.env','/deep/production.env','/deep/.env.local','/deep/production.ENV'].map(p=>matches(base,p)),[true,true,false,false]);
 assert.equal(matches({...base,mode:'filename'},'/deep/production.env'),false);
 assert.equal(matches({...base,mode:'filename'},'/deep/.env'),true);
 const dir={...base,mode:'directory',values:'/project'};
 assert.deepEqual(['/project','/project/a','/project-other/a'].map(p=>matches(dir,p)),[true,true,false]);
 assert.deepEqual(patterns(dir),['/project','/project/**']);
 assert.equal(matches(base,'/project/../.env'),null);
});
test('63-byte suffix limit and all effects preserve the generated conditions',()=>{
 assert.equal(validate({...base,values:'.'+'a'.repeat(62)}),'');
 assert.match(validate({...base,values:'.'+'a'.repeat(63)}),/63/);
 assert.match(validate({...base,values:'.环境'.repeat(16)}),/63/);
 for(const effect of ['block','notify','kill']){
  const text=ruleDsl({...base,mode:'flow',ops:['connect'],effect});
  assert.match(text,/source SENSITIVE = file "\*\*\/\*\.env"/);
  assert.ok(text.includes(effect+' connect endpoint "*" if AGENT and SENSITIVE'));
 }
 assert.match(validate({...base,ops:['connect']}),/触发操作/);
});
