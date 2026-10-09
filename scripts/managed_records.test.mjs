import test from 'node:test';
import assert from 'node:assert/strict';
import {readNavigation,navigationTarget,pages} from '../frontend/src/navigation.mjs';
test('retired runtime module restores the single workbench and preserves its task',()=>{
 const url='http://127.0.0.1:18003/?view=runtime&task=d5e21e674b464d16';
 assert.equal(readNavigation(url).page,'workbench');assert.ok(!pages.includes('runtime'));
 const target=navigationTarget(url,{});assert.match(target,/view=workbench/);assert.match(target,/task=d5e21e674b464d16/);
 assert.equal(readNavigation('http://127.0.0.1:18003/?view=scope-demo').task,'');
});
