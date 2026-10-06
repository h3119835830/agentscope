import assert from 'node:assert/strict';
import {test} from 'node:test';
import {restorePublicSession,publicQuestionAnswer} from '../lib/public-session.js';
test('domain replacement restores public turns without private streams or hidden context',()=>{
 const events=[{type:'turn/start',seq:0,data:{turn:12}},
 {type:'assistant/attempt',seq:1,data:{stream:['private attempt']}},
 {type:'assistant/message',seq:2,data:{turn:12,message:{content:[{type:'thinking',text:'private thought'},{type:'text',text:'public result'}]},stream:['private stream']}},
 {type:'user/message',seq:3,data:{source:{kind:'context'},content:[{type:'text',text:'hidden context'}]}},
 {type:'user/message',seq:4,data:{source:{kind:'user'},content:[{type:'text',text:'real user'}]}},
 {type:'turn/end',seq:5,data:{turn:12,reason:'complete'}}];
 const result=restorePublicSession({id:'same-session',snapshotEvents:()=>events});
 assert.equal(result.turn,12);assert.equal(result.events.length,4);
 assert.equal(result.events[1].text,'public result');
 for(const forbidden of ['private thought','private stream','private attempt','hidden context'])assert.ok(!JSON.stringify(result).includes(forbidden));
});

test('native question answers enter public context; pending/timeouts do not invent answers',()=>{
 const call={type:'tool/call',data:{callId:'q1',name:'ask_user_question',arguments:JSON.stringify({questions:[{id:'target',question:'Which file?'}]})}};
 const session={snapshotEvents:()=>[call,{type:'assistant/attempt',data:{stream:['private']}}]};
 const event={type:'tool/result',data:{message:{role:'tool',toolCallId:'q1',content:[{type:'text',text:JSON.stringify({answers:[{id:'target',selected:['registered.py']}]})}]}}};
 const result=publicQuestionAnswer(session,event);assert.equal(result.call_id,'q1');assert.ok(result.text.includes('registered.py'));assert.ok(!result.text.includes('private'));
 event.data.message.content[0].text=JSON.stringify({pending:true,callId:'q1'});assert.equal(publicQuestionAnswer(session,event),null);
});

test('admitted queue messages cross the seam before turn dispatch',async()=>{
 const {acceptedUserMessages}=await import('../lib/public-session.js');
 const session={id:'bound'};
 const human={source:{kind:'user',rpcId:'real-request'},content:[{type:'text',text:'clarify the necessary boundary'}]};
 assert.equal(acceptedUserMessages(session,{type:'agent/inbox/spliced',data:{inserted:[human]}})[0].event_key,'accepted:bound:real-request');
 assert.deepEqual(acceptedUserMessages(session,{type:'agent/inbox/spliced',data:{inserted:[{...human,source:{kind:'context'}}]}}),[]);
 assert.deepEqual(acceptedUserMessages(session,{type:'agent/inbox/spliced',data:{inserted:[human],outcome:'canceled'}}),[]);
});


import {receivedOperationFeedback} from '../lib/public-session.js';
test('feedback offers count only after actual native context admission',()=>{
 const s={id:'native'},m={source:{kind:'context'},content:[{type:'text',text:'[ActPlane operation feedback] denied'}]};
 assert.equal(receivedOperationFeedback(s,{type:'tool/result',seq:1,data:{message:m}}).length,0);
 assert.equal(receivedOperationFeedback(s,{type:'agent/inbox/spliced',seq:2,data:{inserted:[m],outcome:'canceled'}}).length,0);
 assert.equal(receivedOperationFeedback(s,{type:'agent/inbox/spliced',seq:3,data:{inserted:[m],outcome:'accepted'}}).length,1);
 assert.equal(receivedOperationFeedback(s,{type:'user/message',seq:4,data:{...m,source:{kind:'user'}}}).length,0);
});

test('several feedback contexts in one native event keep distinct receipt identities',()=>{
 const message=text=>({source:{kind:'context'},content:[{type:'text',text:'[ActPlane operation feedback] '+text}]});
 const receipts=receivedOperationFeedback({id:'native'},{type:'agent/inbox/spliced',seq:3,data:{inserted:[message('one'),message('two')]}});
 assert.equal(receipts.length,2);assert.notEqual(receipts[0].event_key,receipts[1].event_key);
});
