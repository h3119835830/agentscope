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
