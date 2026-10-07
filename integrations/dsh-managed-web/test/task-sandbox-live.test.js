import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {spawnSync} from 'node:child_process';
import {installTaskSandbox,sandboxArgv,taskLayout} from '../lib/task-sandbox.js';
if(process.getuid()===0){const groups=readFileSync('/etc/group','utf8').split('\n');const gid=Number(groups.find(line=>line.startsWith('agentscope-task:')).split(':')[2]);const users=readFileSync('/etc/passwd','utf8').split('\n');const uid=Number(users.find(line=>line.startsWith('agentscope-agent:')).split(':')[2]);process.setgroups([gid]);process.setgid(gid);process.setuid(uid);}
const root=mkdtempSync(join(process.env.AGENTSCOPE_SANDBOX_TEST_ROOT||'/s','task-sandbox-test-'));
for(const folder of ['r','tmp','tmp/home','output','.public-runtime','r/.actplane'])mkdirSync(join(root,folder),{recursive:true});
writeFileSync(join(root,'.public-runtime/pyvenv.cfg'),readFileSync('/var/lib/agentscope-rq5-v1/task-python/pyvenv.cfg','utf8').split('\n').filter(line=>!line.startsWith('command')).join('\n'));
writeFileSync(join(root,'r/.actplane/audit'), 'PRIVATE-CONTROL');
for(const d of ['usr','etc/ssl','proc','dev','runtime/bin','opt/task-python','opt/dsh-runtime/node_modules',root.slice(1)+'/r',root.slice(1)+'/tmp',root.slice(1)+'/output'])mkdirSync(join(root,'.sandbox-root',d),{recursive:true});
for(const f of ['node','rg'])writeFileSync(join(root,'.sandbox-root/runtime/bin',f),'');
const {symlinkSync}=await import('node:fs');for(const [name,target] of [['bin','usr/bin'],['lib','usr/lib'],['lib64','usr/lib64'],['tmp',root+'/tmp']])symlinkSync(target,join(root,'.sandbox-root',name));
const layout=taskLayout(join(root,'r'));
const ctx={sandbox:{},subprocess:{spawn:s=>s},fs:{watch:()=>{} }};
installTaskSandbox(ctx,layout.workspace);
test('real namespace cannot see control roots, credentials, other tasks, parent processes or network',()=>{
 const code=`import os,socket,json\npaths=['/opt/agentscope-history-v1','/var/lib/agentscope-scope-demo','/run/agentscope-scope-demo','/var/lib/agentscope-normalization-v1','/run/agentscope-normalization-v1','/n/another-task','/s/another-task','/root','${root}/.dsh','${root}/r/.actplane/audit']\nr={'hidden':[not os.path.exists(p) for p in paths], 'safe_env':not any(k.startswith(('AGENTSCOPE_','ACTPLANE_','DSH_')) for k in os.environ)}\ns=socket.socket();s.settimeout(.2)\ntry:s.connect(('127.0.0.1',18003));r['network_hidden']=False\nexcept OSError:r['network_hidden']=True\nr['pids']=len([p for p in os.listdir('/proc') if p.isdigit()]);print(json.dumps(r))`;
 const argv=sandboxArgv(['/usr/bin/python3','-c',code],layout);
 const p=spawnSync(argv[0],argv.slice(1),{encoding:'utf8',env:{...process.env,AGENTSCOPE_URL:'PRIVATE-CONTROL',AGENTSCOPE_TASK_TOKEN:'PRIVATE-TOKEN'}});
 assert.equal(p.status,0,p.stderr);const r=JSON.parse(p.stdout);assert.ok(r.hidden.every(Boolean));assert.ok(r.safe_env&&r.network_hidden);assert.ok(r.pids<=3);
});
test('native filesystem reads, CAS replacement and directory listing work inside isolated world',async()=>{
 const target=await ctx.fs.resolve('legal.txt');const made=await ctx.fs.writeText(target,'one\n',{kind:'createIfAbsent'});assert.equal(made.operation,'create');
 const read=await ctx.fs.readText(target);assert.match(JSON.stringify(read),/one/);
 await assert.rejects(ctx.fs.writeText(target,'bad',{kind:'replaceIfVersion',version:'stale'}),/changed since it was read/);
 await ctx.fs.writeText(target,'two\n',{kind:'replaceIfVersion',version:made.version});
 const listed=await ctx.fs.listDir(await ctx.fs.resolve('.'));assert.ok(listed.some(x=>x.name==='legal.txt'));assert.ok(listed.every(x=>x.name!=='.actplane'));
});
test('file service rejects host/control/symlink aliases without returning bytes',async()=>{
 for(const path of ['/opt/agentscope-history-v1/README.md',root+'/.dsh/settings.yaml',layout.workspace+'/.actplane/audit']){const target=await ctx.fs.resolve(path);assert.equal(await ctx.fs.stat(target),undefined);await assert.rejects(ctx.fs.readText(target),/outside the task execution environment/);}
 const {symlinkSync}=await import('node:fs');symlinkSync('/etc/passwd',layout.workspace+'/alias');
 await assert.rejects(ctx.fs.readText({displayPath:layout.workspace+'/alias',targetKey:layout.workspace+'/alias'}),/outside the task execution environment|not found/);
});
test('published Python dependencies remain usable',()=>{
 const argv=sandboxArgv([layout.runtime+'/bin/python','-c','import pytest; print("DEPENDENCIES_OK")'],layout);const r=spawnSync(argv[0],argv.slice(1),{encoding:'utf8'});assert.equal(r.status,0,r.stderr);assert.match(r.stdout,/DEPENDENCIES_OK/);
});
