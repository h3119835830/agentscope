import test from 'node:test';
import assert from 'node:assert/strict';
import {sessionProcessRow} from './sessionProcesses.mjs';
import {visibleAgentInstances} from './agentInstancePresentation.mjs';
test('saved sessions retain identity and never borrow the instance PID',()=>{
 const row=sessionProcessRow({id:'stored',name:'结算检查',status:'stored',process_ids:[]});
 assert.equal(row.name,'结算检查');assert.equal(row.id,'stored');assert.deepEqual(row.pids,[]);assert.equal(row.label,'已保存');
});
test('two sessions may share one executor and retain separate names and IDs',()=>{
 const rows=['a','b'].map(id=>sessionProcessRow({id,name:id,status:'idle',process_ids:[42,42,-1,'43']}));
 assert.deepEqual(rows.map(r=>r.pids),[[42],[42]]);assert.notEqual(rows[0].id,rows[1].id);
 assert.equal(sessionProcessRow({id:'untitled',status:'future'}).name,'未命名会话');
 assert.equal(sessionProcessRow({id:'untitled',status:'future'}).tone,'warn');
});
test('all controlled connections remain configurable without a secondary picker',()=>{
 const a={id:'a',agent_type:'dsh',mode:'controlled'},b={id:'b',agent_type:'dsh',mode:'controlled'};
 assert.deepEqual(visibleAgentInstances([a,b,{id:'observed',agent_type:'dsh',mode:'observed'}]),[a,b]);
});
test('an observed product keeps its preferred entry when no controlled connection exists',()=>{
 const cli={id:'cli',agent_type:'hermes',status:'installed'},web={id:'web',agent_type:'hermes',connected:true,entry:{kind:'web'}};
 assert.deepEqual(visibleAgentInstances([cli,web]),[web]);
});
