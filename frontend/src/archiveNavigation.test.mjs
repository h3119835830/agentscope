import test from 'node:test';
import assert from 'node:assert/strict';
import {readNavigation,navigationTarget} from './navigation.mjs';
test('historical policy and audit pane survives refresh without changing current task',()=>{
 const url='http://localhost/?view=workbench&task=current&agent=native-dsh';
 const target=navigationTarget(url,{page:'history',archiveTask:'old',archivePane:'audit'});
 const state=readNavigation('http://localhost'+target);
 assert.equal(state.task,'current');assert.equal(state.archiveTask,'old');assert.equal(state.archivePane,'audit');
 assert.equal(readNavigation('http://localhost'+navigationTarget('http://localhost'+target,{page:'workbench'})).task,'current');
});
test('old archive links open startup policies and unknown panes cannot select arbitrary content',()=>{
 assert.equal(readNavigation('http://localhost/?view=history&archive=old').archivePane,'startup');
 assert.equal(readNavigation('http://localhost/?archivePane=invalid').archivePane,'startup');
});

test('replay domain pane restores task identity and list context without selecting an active workbench task',()=>{
 const original='http://localhost/?view=history&archive=old-rq5&archivePane=startup&task=live&filter=all&q=RQ5&listPage=2&agent=native-dsh';
 const graph=navigationTarget(original,{archivePane:'domains'}),state=readNavigation('http://localhost'+graph);
 assert.equal(state.archivePane,'domains');assert.equal(state.archiveTask,'old-rq5');assert.equal(state.task,'live');assert.equal(state.listPage,2);assert.equal(state.query,'RQ5');assert.equal(state.filter,'all');
 const closed=readNavigation('http://localhost'+navigationTarget('http://localhost'+graph,{archiveTask:''}));assert.equal(closed.archiveTask,'');assert.equal(closed.page,'history');assert.equal(closed.listPage,2);assert.equal(readNavigation(original).archivePane,'startup');
});
test('history route without a replay task remains the list even with a domains pane',()=>{const state=readNavigation('http://localhost/?view=history&archivePane=domains');assert.equal(state.page,'history');assert.equal(state.archiveTask,'');assert.equal(state.archivePane,'domains');});
