import {spawn} from 'node:child_process';
import {realpathSync, existsSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {FsError} from '@deepseek-ai/dsh-fs';

export const TASK_TOOLS=new Set(['bash','read','write','edit','read_image','glob','grep','ask_user_question','job_output','job_list','job_kill']);
const under=(path,root)=>path===root||path.startsWith(root+'/');
export function taskLayout(workspace) {
 const root=dirname(workspace);
 return {workspace,temporary:root+'/tmp',output:root+'/output',runtime:'/opt/task-python',home:root+'/tmp/home',root};
}
// The native host is trusted transport; model-controlled code gets a fresh root,
// PID/net namespaces and an empty environment. Never mount the host root/home/run.
export function sandboxArgv(argv,layout,{filesystem=false}={}) {
 const args=['/usr/bin/bwrap','--die-with-parent','--unshare-user','--unshare-pid','--unshare-net','--unshare-ipc','--unshare-uts','--cap-drop','ALL',
  '--ro-bind',layout.root+'/.sandbox-root','/','--ro-bind','/usr','/usr',
  '--proc','/proc','--dev','/dev','--dir','/etc','--ro-bind','/etc/ssl','/etc/ssl',
  '--bind',layout.workspace,layout.workspace,'--bind',layout.temporary,layout.temporary,'--bind',layout.output,layout.output,
  '--tmpfs',layout.workspace+'/.actplane','--chmod','000',layout.workspace+'/.actplane',
  '--ro-bind','/opt/agentscope/bin/node','/runtime/bin/node',
  '--ro-bind','/var/lib/agentscope-rq5-v1/task-python',layout.runtime,
  '--ro-bind',layout.root+'/.public-runtime/pyvenv.cfg',layout.runtime+'/pyvenv.cfg',
  '--clearenv','--setenv','PATH',layout.runtime+'/bin:/runtime/bin:/usr/local/bin:/usr/bin:/bin',
  '--setenv','HOME',layout.home,'--setenv','TMPDIR',layout.temporary,'--setenv','LANG','C.UTF-8','--setenv','PYTHONDONTWRITEBYTECODE','1'];
 if(filesystem) {
  args.push('--ro-bind','/opt/agentscope/dsh/node_modules','/opt/dsh-runtime/node_modules');
  if(existsSync('/opt/agentscope/dsh/node_modules/@agentscope'))args.push('--tmpfs','/opt/dsh-runtime/node_modules/@agentscope','--chmod','000','/opt/dsh-runtime/node_modules/@agentscope');
 }
 return [...args,'--',...argv];
}
export function admittedPath(path,layout,cwd=layout.workspace) {
 const absolute=resolve(cwd,String(path));
 const roots=[layout.workspace,layout.temporary,layout.output,'/usr',layout.runtime];
 if(!roots.some(root=>under(absolute,root))||under(absolute,layout.workspace+'/.actplane'))throw new FsError('Task sandbox: this path is outside the task execution environment.','FS_SANDBOX_DENIED');
 return absolute;
}
// Native CAS/version, text validation and atomic publication are reused in a
// separate confined process. A background symlink swap cannot expose host data.
const FS_PROGRAM=String.raw`
import {Context} from '/opt/dsh-runtime/node_modules/@deepseek-ai/cordis/lib/index.js';
import {LocalFileSystem} from '/opt/dsh-runtime/node_modules/@deepseek-ai/dsh-fs-local/lib/index.js';
import {realpath} from 'node:fs/promises';
const input=JSON.parse(await new Promise(resolve=>{let raw='';process.stdin.setEncoding('utf8');process.stdin.on('data',s=>raw+=s);process.stdin.on('end',()=>resolve(raw));}));
const fs=new LocalFileSystem(new Context(),{cwd:input.workspace,diffBasisMaxBytes:1048576});
const roots=input.roots;
function inside(p){return roots.some(root=>p===root||p.startsWith(root+'/'))&&!p.startsWith(input.workspace+'/.actplane');}
try {
 if(!['resolve','stat','lstat','readText','streamText','readBytes','readByteRange','listDir','writeText','editText'].includes(input.method))throw Error('Unsupported filesystem operation');
 let args=input.args.map(arg=>arg===null?undefined:arg);
 if(input.method==='resolve'||input.method==='lstat') {
  const t=await fs.resolve(args[0],args[1]);if(input.method==='lstat'&&!inside(String(t.targetKey))){process.stdout.write(JSON.stringify({ok:true}));process.exit(0);}
 }else {
  const t=await fs.resolve(args[0].displayPath);if(!inside(String(t.targetKey)))throw Error('Task sandbox: path is outside the task execution environment.');args[0]=t;
 }
 let result=await fs[input.method](...args);
 if(input.method==='streamText'){let text='';for await(const part of result){text+=part;if(Buffer.byteLength(text)>16777216)throw Error('Task file exceeds read limit');}result=text;}
 if(Buffer.isBuffer(result))result={buffer_base64:result.toString('base64')};
 if(input.method==='listDir')result=result.filter(item=>item.name!=='.actplane');
 process.stdout.write(JSON.stringify({ok:true,result}));
}catch(e){process.stdout.write(JSON.stringify({ok:false,error:e.message,code:e.code||'FS_SANDBOX_DENIED'}));}
`;
export function installTaskSandbox(ctx,workspace) {
 const layout=taskLayout(workspace);
 ctx.sandbox.confine=async(argv,_policy,signal)=>{signal?.throwIfAborted();return {argv:sandboxArgv(argv,layout),enforcement:'full',denialSignatures:['operation not permitted','permission denied','read-only file system'],runnerFailureRules:[{fatalSignatures:['bwrap: ']}]};};
 const spawnNative=ctx.subprocess.spawn.bind(ctx.subprocess);
 ctx.subprocess.spawn=spec=>{
  admittedPath(spec.cwd||workspace,layout);
  let argv=spec.argv;
  if(argv[0]!=='/usr/bin/bwrap') {
   // The native search seam bypasses bash. Bind the packaged public executable
   // to a neutral name rather than permitting arbitrary host executables.
   if(argv[0].includes('/@vscode/ripgrep/')&&argv[0].endsWith('/rg')) {
    const profile=sandboxArgv(['/runtime/bin/rg',...argv.slice(1)],layout);
    profile.splice(profile.indexOf('--'),0,'--ro-bind',realpathSync(argv[0]),'/runtime/bin/rg');argv=profile;
   }else argv=sandboxArgv(argv,layout);
  }
  return spawnNative({...spec,argv,env:{}});
 };
 ctx.subprocess.spawnTerminal=()=>{throw Error('Task sandbox: interactive host terminals are unavailable.');};
 async function call(method,args,signal) {
  signal?.throwIfAborted();
  if(typeof args[0]==='string')admittedPath(args[0],layout,args[1]?.cwd||workspace);
  else admittedPath(args[0].displayPath,layout);
  const command=sandboxArgv(['/runtime/bin/node','--input-type=module','-e',FS_PROGRAM],layout,{filesystem:true});
  const child=spawn(command[0],command.slice(1),{cwd:workspace,env:{PATH:'/usr/bin:/bin'},stdio:['pipe','pipe','pipe'],signal});
  let stdout='',stderr='';
  const done=new Promise((resolve,reject)=>{child.on('error',reject);child.stdout.setEncoding('utf8');child.stdout.on('data',s=>{stdout+=s;if(Buffer.byteLength(stdout)>33554432)child.kill();});child.stderr.setEncoding('utf8');child.stderr.on('data',s=>stderr=(stderr+s).slice(-2000));child.on('close',code=>code===0?resolve():reject(new FsError('Task sandbox filesystem process failed. '+stderr,'FS_IO_ERROR')));});
  const jsonArgs=args.map(a=>a===undefined?null:a);
  child.stdin.end(JSON.stringify({method,args:jsonArgs,workspace,roots:[workspace,layout.temporary,layout.output,'/usr',layout.runtime]}));
  await done;const result=JSON.parse(stdout);if(!result.ok)throw new FsError(result.error,result.code);
  return result.result?.buffer_base64?Buffer.from(result.result.buffer_base64,'base64'):result.result;
 }
 const fs=ctx.fs;
 fs.resolve=(path,opts)=>{const absolute=resolve(opts?.cwd||workspace,String(path));try{admittedPath(absolute,layout);}catch{return Promise.resolve({targetKey:absolute,displayPath:absolute});}return call('resolve',[path,{cwd:opts?.cwd||workspace}],opts?.signal);};
 fs.lstat=(path,opts,signal)=>{try{admittedPath(path,layout,opts?.cwd||workspace);}catch{return Promise.resolve(undefined);}return call('lstat',[path,{cwd:opts?.cwd||workspace}],signal);};
 fs.stat=(target,signal)=>{try{admittedPath(target.displayPath,layout);}catch{return Promise.resolve(undefined);}return call('stat',[target],signal);};
 for(const method of ['readText','listDir'])fs[method]=(target,signal)=>call(method,[target],signal);
 fs.readBytes=(target,signal,maxBytes)=>call('readBytes',[target,null,maxBytes],signal);
 fs.readByteRange=(target,range,signal)=>call('readByteRange',[target,range],signal);
 fs.streamText=async(target,signal)=>{const text=await call('streamText',[target],signal);return (async function*(){yield text;})();};
 fs.writeText=(target,content,expected,signal)=>call('writeText',[target,content,expected],signal);
 fs.editText=(target,edit,expected,signal)=>call('editText',[target,edit,expected],signal);
 const watch=fs.watch.bind(fs);fs.watch=(target,changed,signal)=>{try{admittedPath(target.displayPath,layout);}catch{return Promise.resolve(()=>{});}return watch(target,changed,signal);};
 return layout;
}
