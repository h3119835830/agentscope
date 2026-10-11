import test from 'node:test';
import assert from 'node:assert/strict';
import {sceneBusy,sceneUsable,sceneInput,sceneForInput} from './policyScene.mjs';
import {assistantInput} from './policyAssistant.mjs';
const context={ready:true,session_id:'session-a',context_hash:'a'.repeat(64)},target={id:'agent-a',mode:'controlled'};
const scene={id:'b'.repeat(32),instance_id:target.id,session_id:context.session_id,status:'completed',current:true,read_only:true};
test('scene selection only sends the server-owned context credential',()=>{
 assert.deepEqual(sceneInput(context,'read-key'),{session_id:'session-a',context_hash:'a'.repeat(64),request_key:'read-key'});
 assert.throws(()=>sceneInput({...context,ready:false},'key'));
});
test('pending, stale and other-target scene evidence cannot enter a generation',()=>{
 for(const status of ['queued','running','failed','interrupted'])assert.throws(()=>sceneForInput({...scene,status},target,context));
 assert.throws(()=>sceneForInput({...scene,current:false},target,context));
 assert.throws(()=>sceneForInput({...scene,instance_id:'other'},target,context));
 assert.throws(()=>sceneForInput({...scene,session_id:'other'},target,context));
 assert.equal(sceneForInput(null,target,context),null);assert.equal(sceneForInput(scene,target,context),scene.id);
 assert.ok(sceneBusy({status:'queued'}));assert.ok(!sceneUsable({status:'completed'}));
});
test('adopted scene adds a reference without smuggling files or granting application authority',()=>{
 const payload=assistantInput('禁止读取 .env 文件',target,[],context,sceneForInput(scene,target,context));
 assert.equal(payload.agent_context.scene_id,scene.id);
 assert.deepEqual(Object.keys(payload.agent_context).sort(),['context_hash','instance_id','scene_id','session_id']);
 assert.equal(payload.text,'禁止读取 .env 文件');assert.equal(payload.context_requirement,'project');
});
test('rereading the scene does not carry the previous scenario requirements forward',()=>{
 const turns=[{text:'OLD_SCENE_REQUIREMENT',sceneId:'old'},{text:'CURRENT_SCENE_REQUIREMENT',sceneId:scene.id}];
 const payload=assistantInput('禁止读取 .env 文件',target,turns,context,scene.id);
 assert.doesNotMatch(payload.text,/OLD_SCENE/);assert.match(payload.text,/CURRENT_SCENE/);
 assert.doesNotMatch(assistantInput('保护新的项目文档',target,turns,context).text,/SCENE_REQUIREMENT/);
});
