import test from 'node:test';
import assert from 'node:assert/strict';
import {sceneReadPath,sceneContextKey,sceneReadMatches,validateSceneRead,canUseSceneDraft,sceneCreateBody,sceneReadLabel,sceneErrorMessage,sceneEvidence,sceneStorageKey,sceneStoredValue,restoreSceneContext} from './workspaceScene.mjs';

const context={workspaceId:'workspace-a',agentId:'native-dsh',manifestHash:'a'.repeat(64),sourceGeneration:'instance-1',supplement:''};
const receipt=overrides=>({id:'read-1',workspace_id:context.workspaceId,manifest_hash:context.manifestHash,source_generation:context.sourceGeneration,status:'completed',read_only:true,task_id:null,draft_hash:'b'.repeat(64),draft:{state:'ready',name:'修复支付验证',goal:'修复支付验证，保留现有测试',constraints:['保留测试'],evidence:[{source_id:'s1',relative_path:'task.md',quote:'修复支付验证，保留现有测试'}]},...overrides});

test('scene reads use task-independent encoded workspace and read paths',()=>{
 assert.equal(sceneReadPath('w/1'),'/api/agent-workspaces/w%2F1/scene-reads');
 assert.equal(sceneReadPath('w/1','read/2'),'/api/agent-workspaces/w%2F1/scene-reads/read%2F2');
 assert.equal(validateSceneRead(receipt({status:'queued',draft:null,draft_hash:null}),context).task_id,null);
});
test('confirmed input uses immutable read receipt without requiring manually entered name or prompt',()=>{
 const read=validateSceneRead(receipt(),context);
 assert.equal(canUseSceneDraft(read,context,context),true);
 assert.deepEqual(sceneCreateBody(read,context,context),{read_id:'read-1',draft_hash:'b'.repeat(64),expected_manifest_hash:'a'.repeat(64)});
});
test('an earlier result cannot be used after switching workspace instance files or supplemental intent',()=>{
 for(const changed of [{workspaceId:'workspace-b'},{agentId:'managed:new'},{manifestHash:'c'.repeat(64)},{sourceGeneration:'instance-2'},{supplement:'仅总结，不修复'}]){
  const now={...context,...changed};assert.equal(sceneReadMatches(receipt(),context,now),false);assert.equal(canUseSceneDraft(receipt(),context,now),false);assert.throws(()=>sceneCreateBody(receipt(),context,now));
 }
 assert.equal(sceneContextKey({...context,supplement:'  总结  '}),sceneContextKey({...context,supplement:'总结'}));
});
test('a workspace description without a goal remains clarification instead of becoming an execution task',()=>{
 const read=receipt({draft:{state:'needs_clarification',name:'项目场景',goal:'',constraints:[],clarification:'本次希望完成什么？',evidence:[{relative_path:'README.md',quote:'A sample project.'}]}});
 assert.equal(validateSceneRead(read,context),read);assert.equal(canUseSceneDraft(read,context,context),false);assert.equal(sceneReadLabel(read),'需要补充本次目标');
 assert.throws(()=>sceneCreateBody(read,context,context));
});
test('unexpected HTML-shaped or execution-bearing responses cannot enable the read-only scene flow',()=>{
 for(const value of [{},receipt({read_only:false}),receipt({task_id:false}),receipt({status:'unknown'}),receipt({draft:null}),receipt({draft_hash:null}),receipt({draft:{state:'ready',name:'README',goal:''}})])assert.throws(()=>validateSceneRead(value,context));
 assert.throws(()=>validateSceneRead(receipt({workspace_id:'workspace-b'}),context),/工作区/);
 assert.throws(()=>validateSceneRead(receipt({manifest_hash:'f'.repeat(64)}),context),/文件版本/);
});
test('refresh restores only an existing read pointer and changed material keeps supplement but loses the pointer',()=>{
 const saved=sceneStoredValue({...context,supplement:'保留配置，仅修复解析'},'read-1');
 assert.deepEqual(restoreSceneContext(saved,context),{context:{...context,supplement:'保留配置，仅修复解析'},read_id:'read-1',stale:false});
 for(const changed of [{manifestHash:'f'.repeat(64)},{sourceGeneration:'instance-2'}]){
  const restored=restoreSceneContext(saved,{...context,...changed});assert.equal(restored.read_id,null);assert.equal(restored.stale,true);assert.equal(restored.context.supplement,'保留配置，仅修复解析');
 }
 assert.equal(restoreSceneContext(saved,{...context,workspaceId:'other'}),null);
 assert.equal(restoreSceneContext(saved,{...context,agentId:'other'}),null);
 assert.equal(restoreSceneContext('<html>fallback</html>',context),null);
 assert.notEqual(sceneStorageKey(context),sceneStorageKey({...context,workspaceId:'other'}));
});
test('editing intent clears the stored read pointer and adopted results cannot create a second task',()=>{
 const pending=restoreSceneContext(sceneStoredValue({...context,supplement:'新的目标'}),context);
 assert.equal(pending.read_id,null);assert.equal(pending.context.supplement,'新的目标');
 const adopted=validateSceneRead(receipt({task_id:'existing-task'}),context);
 assert.equal(canUseSceneDraft(adopted,context,context),false);assert.equal(sceneReadLabel(adopted),'已用于创建任务');
 assert.equal(sceneErrorMessage('scene_read_failed'),'Agent 未完成场景读取，请重新尝试。');
 assert.equal(sceneErrorMessage('scene_read_interrupted'),'场景读取已中断，请重新读取。');
});
test('pending failed and interrupted reads never provide task creation input',()=>{
 for(const status of ['queued','running','failed','interrupted'])assert.equal(canUseSceneDraft(receipt({status}),context,context),false);
 assert.equal(sceneReadLabel(receipt({status:'running'})),'Agent 正在读取场景');
});
test('user supplement citations keep their source role without duplicating the entered goal',()=>{
 const draft={evidence:[{relative_path:'README.md',quote:'Fixture.'},{relative_path:'user:supplement',quote:'仅概括README'}]};
 assert.deepEqual(sceneEvidence(draft,'仅概括README'),[{path:'README.md',quote:'Fixture.',kind:'scene_file'},{path:'本次输入',quote:'仅概括README',kind:'user_supplement'}]);
 assert.deepEqual(sceneEvidence({evidence:[]},'仅读取'),[{path:'本次输入',quote:'仅读取',kind:'user_supplement'}]);
 assert.equal(sceneEvidence({evidence:[{relative_path:'docs/user:supplement',quote:'project text'}]})[0].kind,'scene_file');
});
