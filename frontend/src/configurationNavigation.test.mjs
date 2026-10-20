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
