import test from 'node:test';
import assert from 'node:assert/strict';
import {agentPolicySource,policySources,sourceDeclarations,bindGeneratedSource} from './policySources.mjs';
const dsh={id:'dsh-one',agent_type:'dsh',mode:'controlled',connected:true,runtime:{executable:'/opt/agentscope/dsh/node_modules/@deepseek-ai/dsh/lib/bin.js'}};
const hermes={id:'hermes-one',agent_type:'hermes',mode:'controlled'};
test('DSH uses its controlled Node launcher, Hermes uses its Python launcher, and generic executors are never silently substituted',()=>{
 assert.equal(agentPolicySource(dsh).pattern,'**/node');assert.equal(agentPolicySource(dsh).entry,dsh.runtime.executable);assert.equal(agentPolicySource(hermes).pattern,'**/python');
 assert.throws(()=>agentPolicySource({...dsh,mode:'observed'}));assert.throws(()=>agentPolicySource({id:'other',mode:'controlled',agent_type:'other'}));
});
test('system declarations cover the registered controlled products and deduplicate identical executors',()=>{
 const sources=policySources({scope_type:'system'},null,[dsh,hermes,{...dsh,id:'dsh-two'},{...dsh,id:'observed',mode:'observed'}]);
 assert.equal(sources.length,3);const dsl=sourceDeclarations(sources);assert.equal(dsl.split('\n').length,2);assert.ok(dsl.includes('**/node'));assert.ok(dsl.includes('**/python'));assert.throws(()=>policySources({scope_type:'system'},null,[]));
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
