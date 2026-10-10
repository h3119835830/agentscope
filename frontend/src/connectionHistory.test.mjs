import test from 'node:test';
import assert from 'node:assert/strict';
import {connectionStatus,connectionEvent,mergeConnectionEvents} from './connectionHistory.mjs';
import {readNavigation,navigationTarget} from './navigation.mjs';

test('retired connection history links fall back to current connections without selecting a task',()=>{
 const href='http://localhost/?view=connections&task=current';
 const history=navigationTarget(href,{connectionsPane:'history',connectionHistory:'managed:old'});
 const state=readNavigation('http://localhost'+history);
 assert.equal(state.connectionsPane,'current');assert.equal(state.connectionHistory,'');assert.equal(state.task,'current');
 const archive=navigationTarget('http://localhost'+history,{page:'history',archiveTask:'old'});
 const back=navigationTarget('http://localhost'+archive,{page:'connections'});
 assert.equal(readNavigation('http://localhost'+back).connectionHistory,'');
 assert.equal(readNavigation('http://localhost/?view=connections&connectionsPane=history&connectionHistory=old').connectionsPane,'current');
 assert.equal(new URL('http://localhost'+back).searchParams.has('connectionsPane'),false);
 assert.equal(readNavigation('http://localhost/?connectionsPane=unknown').connectionsPane,'current');
});
test('older connection event pages merge without losing a receipt or duplicating rows',()=>{
 assert.deepEqual(mergeConnectionEvents([{id:8},{id:7}],[{id:7},{id:4}]).map(e=>e.id),[8,7,4]);
});
test('unknown transport state and ended binding cannot be described as a verified live connection',()=>{
 assert.equal(connectionStatus('unknown'),'状态未知');assert.equal(connectionStatus('ended'),'任务连接结束');
 assert.equal(connectionStatus('connected'),'已核验接入');assert.equal(connectionEvent('generation_changed'),'实例重启');
});
