import test from 'node:test';
import assert from 'node:assert/strict';
import {configurationNavigation} from './configurationNavigation.mjs';
import {navigationTarget,readNavigation} from './navigation.mjs';
test('configuration links retain exact scope instance and immutable configuration identity',()=>{
 const patch=configurationNavigation('instance-b','tc-b');
 const url=navigationTarget('http://localhost/?view=workbench&policyAgent=instance-a',patch);
 const result=readNavigation('http://localhost'+url);
 assert.equal(result.page,'strategies');
 assert.equal(result.policyAgent,'instance-b');
 assert.equal(result.configurationId,'tc-b');
 assert.equal(result.policyScope,'agent');
 assert.throws(()=>configurationNavigation(''),/准确/);
});
test('old Agent and connection editors redirect to System without widening or erasing historical scope',()=>{
 for(const query of ['view=workbench&agentPolicyTab=policies&policyAgent=a','view=connections&connectionTab=policy&connectionInstance=a']){
  const result=readNavigation('http://localhost/?'+query+'&section=generate');
  assert.equal(result.page,'strategies');assert.equal(result.policyAgent,'a');
  assert.equal(result.systemTab,'policies');
 }
 const history=readNavigation('http://localhost/?view=workbench&agentPolicyTab=policies&policyScope=workspace&policyAgent=a&policyWorkspace=w');
 assert.equal(history.page,'workbench');assert.equal(history.policyScope,'workspace');assert.equal(history.policyWorkspace,'w');
});
test('old session evidence links keep their evidence class without inventing a workspace policy',()=>{
 const kernel=readNavigation('http://localhost/?view=sessions&sessionTab=syscalls');
 const tools=readNavigation('http://localhost/?view=sessions&sessionTab=traces');
 assert.equal(kernel.sessionTab,'events');assert.equal(kernel.sessionEventKind,'kernel');
 assert.equal(tools.sessionTab,'events');assert.equal(tools.sessionEventKind,'tools');
 assert.equal(readNavigation('http://localhost/?view=sessions&sessionTab=domains').sessionTab,'policies');
});
test('old Agent load links select the exact instance directory and discard stale session selections',()=>{
 for(const view of ['workbench','agent']){
  const result=readNavigation('http://localhost/?view='+view+'&agentPolicyTab=loaded&policyScope=agent&policyAgent=agent-a&sessionFilterInstance=agent-b&sessionInstance=agent-b&sessionId=other-session&sessionAgent=hermes&sessionQuery=old&sessionWorkspace=old&sessionCursor=30&sessionTab=flow');
  assert.equal(result.page,'sessions');assert.equal(result.sessionFilterInstance,'agent-a');
  for(const key of ['sessionInstance','sessionId','sessionAgent','sessionQuery','sessionWorkspace'])assert.equal(result[key],'');
  assert.equal(result.sessionCursor,0);assert.equal(result.sessionTab,'policies');
  const canonical='http://localhost'+navigationTarget('http://localhost/',result);
  assert.deepEqual(readNavigation(canonical),result);
 }
});
test('missing or historical load-link targets never expand to every Agent or change historical scope',()=>{
 for(const query of ['policyScope=agent','policyScope=system&policyAgent=agent-a','policyScope=workspace&policyAgent=agent-a&policyWorkspace=original-workspace']){
  const result=readNavigation('http://localhost/?view=workbench&agentPolicyTab=loaded&'+query);
  assert.equal(result.page,'workbench');assert.equal(result.agentPolicyTab,'assistant');
  assert.equal(result.sessionFilterInstance,'');
  if(result.policyScope==='workspace')assert.equal(result.policyWorkspace,'original-workspace');
 }
});
test('stale loaded query on other modules does not redirect or replace selected session evidence',()=>{
 const result=readNavigation('http://localhost/?view=sessions&agentPolicyTab=loaded&policyAgent=agent-a&sessionInstance=agent-b&sessionId=selected&sessionTab=events');
 assert.equal(result.page,'sessions');assert.equal(result.sessionInstance,'agent-b');assert.equal(result.sessionId,'selected');assert.equal(result.sessionTab,'events');
 const missing=readNavigation('http://localhost/?view=workbench&agentPolicyTab=loaded&policyScope=agent&policyAgent=deleted-agent');
 assert.equal(missing.sessionFilterInstance,'deleted-agent');assert.equal(missing.sessionInstance,'');assert.equal(missing.sessionId,'');
});
