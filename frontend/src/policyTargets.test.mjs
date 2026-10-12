import test from 'node:test';
import assert from 'node:assert/strict';
import {submitCandidate,generatedScope,approvalLabel} from './policyExperience.mjs';
import {appendHandoff} from './agentPolicyHandoff.mjs';
import {generatedHandoff} from './policyAssistant.mjs';

for(const scope of ['workspace','session'])test(scope+' candidate uses only the local approval route with its frozen hash',async()=>{
 const c={id:'generated-one',scopeType:scope,targetId:'agent/a',target:{scope,instance_id:'agent/a',workspace_id:'w1',session_id:scope==='session'?'s1':null},candidate_hash:'a'.repeat(64),document:{generation_binding:{artifact_id:'b'.repeat(32)}}};
 const calls=[];
 const p=await submitCandidate(c,()=>assert.fail('local candidate read instance DSL'),async(url,body)=>{calls.push({url,body});return {id:'local:one',state:'blocked'};});
 assert.equal(p.state,'blocked');assert.equal(calls.length,1);
 assert.match(calls[0].url,/agent-instances\/agent%2Fa\/policy-candidates\/b+\/proposals$/);
 assert.deepEqual(calls[0].body,{candidate_hash:c.candidate_hash,request_key:c.id});
 assert.throws(()=>appendHandoff({scope_id:'agent/a',documents:[]},c,'agent/a'),/范围不一致/);
 await assert.rejects(()=>submitCandidate({...c,target:{...c.target,scope:'agent'}},()=>{},()=>{}),/范围不一致/);
});

test('generated scope uses frozen target rather than an Agent-wide label or material path',()=>{
 const ctx={policy_target:{scope:'workspace',workspace_id:'w1'},environment_binding:{values:{workspace:{native_workspace_id:'w1',name:'示例仓库',host:'/srv/repo'}}}};
 assert.equal(generatedScope({record:{resolved_context:ctx}}),'工作区：示例仓库');
 assert.equal(generatedScope({record:{resolved_context:{...ctx,policy_target:{scope:'session'},session_name:'当前任务'}}}),'当前任务及其子进程');
 assert.equal(generatedScope({record:{resolved_context:{kind:'agent'}}}),'旧候选范围待重新确认');
 assert.equal(approvalLabel('blocked'),'暂不能应用');
 assert.throws(()=>generatedHandoff({record:{resolved_context:{kind:'agent'}}},{id:'a',mode:'controlled'}),/服务端固定/);
});
