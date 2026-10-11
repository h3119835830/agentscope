import test from 'node:test';
import assert from 'node:assert/strict';
import {agentPolicySource,policySources,sourceDeclarations,bindGeneratedSource} from './policySources.mjs';
const identity={generation:'gen-a',pid:55,start_ticks:'100',domain_id:99,host_id:'host',boot_id:'boot'};
const verifiedTarget=(id,type='dsh',executable='/opt/agentscope/bin/node')=>({id,mode:'controlled',agent_type:type,connected:true,...identity,policy_source:{ready:true,instance_id:id,...identity,pattern:'**/'+executable.split('/').at(-1),entry:'/opt/agent/launcher',executable,basis:'verified-process-executable'}});
const dsh=verifiedTarget('dsh-one'),hermes=verifiedTarget('hermes-one','hermes','/opt/hermes/venv/bin/python3.12');
test('source uses server verified executor rather than a product-name launcher guess',()=>{
 assert.equal(agentPolicySource(dsh).pattern,'**/node');assert.equal(agentPolicySource(hermes).pattern,'**/python3.12');
 assert.equal(agentPolicySource({...dsh,agent_type:'hermes'}).pattern,'**/node');
 for(const row of [{...dsh,mode:'observed'},{...dsh,connected:false},{...dsh,policy_source:null},{...dsh,pid:999},{...dsh,policy_source:{...dsh.policy_source,instance_id:'other'}},{...dsh,policy_source:{...dsh.policy_source,pattern:'**'}}])assert.throws(()=>agentPolicySource(row));
});
test('system declarations cover the registered controlled products and deduplicate identical executors',()=>{
 const sources=policySources({scope_type:'system'},null,[dsh,hermes,verifiedTarget('dsh-two'),{...dsh,id:'observed',mode:'observed'}]);
 assert.equal(sources.length,3);const dsl=sourceDeclarations(sources);assert.equal(dsl.split('\n').length,2);assert.ok(dsl.includes('**/node'));assert.ok(dsl.includes('**/python3.12'));assert.throws(()=>policySources({scope_type:'system'},null,[]));
});
test('generated Agent exec identity is rebound to the exact destination without erasing other source labels',()=>{
 const dsl='source AGENT = exec "**"\nsource SECRET = file "/workspace/secret"\nrule protect:\n  block read file "/workspace/data" if AGENT\n  because "Protect"';
 const bound=bindGeneratedSource(dsl,dsh);assert.match(bound,/source AGENT = exec "\*\*\/node"/);assert.match(bound,/source SECRET/);assert.doesNotMatch(bound,/exec "\*\*"/);
 assert.throws(()=>bindGeneratedSource('source AGENT = file "/workspace/data"',dsh));
});

test('missing and broad executor source declarations cannot silently recreate a generic Agent source',()=>{
 for(const pattern of ['**','*','**/*','**/node"','**/node\nsource OTHER','**/node*'])assert.throws(()=>sourceDeclarations([{pattern}]));
 assert.throws(()=>sourceDeclarations([]));
});
