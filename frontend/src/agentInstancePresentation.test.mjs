import test from 'node:test';
import assert from 'node:assert/strict';
import {groupAgentInstances,canOpen,canStart,processLabel,entryAction,entryLabel,observedProcesses} from './agentInstancePresentation.mjs';

test('four connection records appear as two products without discarding instance policies',()=>{
 const rows=[
  {id:'controlled-dsh',agent_type:'dsh',mode:'controlled',policy_hash:'a'},
  {id:'controlled-hermes',agent_type:'hermes',mode:'controlled',policy_hash:'b'},
  {id:'native-dsh',agent_type:'dsh',mode:'observed',status:'unknown'},
  {id:'hermes-install',agent_type:'hermes',status:'installed'},
 ];
 const groups=groupAgentInstances(rows);
 assert.deepEqual(groups.map(g=>g.name),['DeepSeek Harness','Hermes']);
 assert.equal(groups[0].members.length,2);
 assert.equal(groups[1].members.length,2);
 assert.equal(groups[0].preferred,rows[0]);
 assert.equal(groups[1].preferred,rows[1]);
 assert.deepEqual(groups.flatMap(g=>g.members).map(r=>r.id).sort(),rows.map(r=>r.id).sort());
 assert.equal(rows[0].policy_hash,'a');
});

test('an already openable observed instance wins over an inactive controlled instance',()=>{
 const stopped={id:'stopped',agent_type:'dsh',mode:'controlled',gate:'paused'};
 const running={id:'running',agent_type:'dsh',mode:'observed',status:'running',connected:true,pid:456,entry:{kind:'web'}};
 const group=groupAgentInstances([stopped,running])[0];
 assert.equal(group.preferred,running);
 assert.equal(canOpen(group.preferred),true);
 assert.equal(canStart(group.preferred),false);
 assert.equal(processLabel(group.preferred),456);
 assert.equal(group.members[0],stopped);
});

test('verified active and openable controlled instance is preferred without aggregating other coverage',()=>{
 const observed={id:'observed',agent_type:'hermes',connected:true,status:'running',security:'仅观测',entry:{kind:'web'}};
 const controlled={id:'controlled',agent_type:'hermes',connected:true,active:true,mode:'controlled',status:'running',security:'执行受控'};
 const group=groupAgentInstances([observed,controlled])[0];
 assert.equal(group.preferred,controlled);
 assert.equal(group.members[0].security,'仅观测');
 assert.equal(group.members[1].security,'执行受控');
});

test('stale or unknown records cannot provide an open action or a historical PID',()=>{
 for(const status of ['stale','unknown','installed','offline']){
  const row={id:status,agent_type:'dsh',mode:'observed',status,pid:321,connected:false,can_open:status==='stale'||status==='unknown'};
  assert.equal(canOpen(row),false);
  assert.equal(processLabel(row),'—');
 }
});

test('same-name manually registered unknown products retain separate connection identities',()=>{
 const rows=[{id:'a',agent_type:'other',name:'Agent'},{id:'b',agent_type:'other',name:'Agent'}];
 assert.equal(groupAgentInstances(rows).length,2);
});

test('CLI installation is labelled and offers terminal instructions, never a Web open',()=>{
 const row={agent_type:'hermes',status:'installed',entry:{kind:'cli_install'},can_open:true};
 assert.equal(entryLabel(row),'CLI 安装入口');
 assert.equal(canOpen(row),false);
 assert.equal(canStart(row),false);
 assert.deepEqual(entryAction(row),{label:'CLI 启动方式',action:'instructions'});
 assert.deepEqual(observedProcesses(row),[]);
});

test('same product selects the usable Web entry while preserving the CLI entry',()=>{
 const cli={id:'install',agent_type:'hermes',status:'installed',entry:{kind:'cli_install'}};
 const web={id:'dashboard',agent_type:'hermes',mode:'controlled',status:'running',connected:true,pid:123};
 const group=groupAgentInstances([cli,web])[0];
 assert.equal(group.members.length,2);
 assert.equal(group.preferred,web);
 assert.deepEqual(entryAction(web),{label:'打开网页',action:'open'});
 assert.deepEqual(entryAction({...web,connected:false,status:'offline'}),{label:'启动网页',action:'start'});
});

test('OS process observation does not imply a Web or CLI entry and expires without historical PID',()=>{
 const row={agent_type:'codex',status:'discovered',pid:987,connected:true,can_open:true};
 assert.equal(entryLabel(row),'进程观测');
 assert.equal(canOpen(row),false);
 assert.deepEqual(entryAction(row),{label:'查看进程',action:'processes'});
 assert.equal(observedProcesses(row)[0].pid,987);
 assert.equal(observedProcesses(row)[0].domain_verified,false);
 assert.deepEqual(observedProcesses({...row,status:'stale'}),[]);
});
