import assert from 'node:assert/strict';
import {test} from 'node:test';
import {visibleTasks,proposalRows,phaseName,policySummary} from './taskPresentation.mjs';

test('record search and phase filters keep review separate from historical completion',()=>{
  const records=[{id:'a',name:'Build',source_name:'Project A',phase:'policy_review'},{id:'b',name:'Archive',phase:'ended'},{id:'c',name:'Pause',phase:'failed'}];
  assert.deepEqual(visibleTasks(records,'project a','active').map(t=>t.id),['a']);
  assert.deepEqual(visibleTasks(records,'','history').map(t=>t.id),['b','c']);
  assert.equal(phaseName('policy_review'),'待确认策略');
});

test('each policy record shows its own compiler rules, without a full-document dump',()=>{
  const proposal={proposal:{draft:{atoms:[{statement:'Keep tests',paths:['/task/tests/test.py']},{statement:'Keep config',paths:['/task/config.json']}]}},validation:{compiler:{rules:[{name:'bootstrap-1',source_text:'tests rule'},{name:'bootstrap-1',source_text:'tests rule'},{name:'bootstrap-2',source_text:'config rule'},{name:'platform-base',source_text:'platform rule'}]}}};
  const rows=proposalRows(proposal);
  assert.equal(rows[0].dsl,'tests rule');
  assert.equal(rows[1].dsl,'config rule');
  assert.equal(rows[1].number,2);
  assert.deepEqual(proposalRows(null),[]);
  assert.equal(policySummary({operations:['write','unlink']}),'禁止写入、删除');
});
