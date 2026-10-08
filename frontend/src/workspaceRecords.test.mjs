import test from 'node:test';
import assert from 'node:assert/strict';
import {workspaceTasks, workspaceSessions, policySentence, policyOutcome} from './workspaceRecords.mjs';

test('workspace association requires a saved identity, never matching names or directories', () => {
  const workspace = {id: 'native:w1', name: 'shared', path: '/repo'};
  const tasks = [
    {id: 'ours', workspace_id: 'native:w1'},
    {id: 'other-instance', workspace_id: 'managed:w1', source_name: 'shared', source_path: '/repo'},
    {id: 'path-only', source_path: '/repo'},
    {id: 'name-only', source_name: 'shared'},
  ];
  assert.deepEqual(workspaceTasks(workspace, tasks).map(row => row.id), ['ours']);
  assert.deepEqual(workspaceTasks({}, tasks), []);
});

test('duplicate task projections do not produce duplicate associations or imply native execution', () => {
  const rows = workspaceTasks({id: 'w'}, [
    {id: 't', workspace_id: 'w', updated_at: '2026-10-07', name: 'old'},
    {task_id: 't', workspace_id: 'w', updated_at: '2026-10-08', name: 'new'},
  ]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].name, 'new');
  assert.equal(rows[0].session_id, undefined);
  assert.equal(rows[0].live, undefined);
  assert.deepEqual(workspaceSessions({session_ids: ['s', 's', null, '', 12]}), ['s']);
});

test('a complete restrictive sentence preserves every exact target including glob and unicode', () => {
  const targets = ['/s/r/tests/**', '/s/r/config.toml', '/s/r/配置.json'];
  const text = policySentence({classification_origin: 'validated_atom_and_evidence_roles', effect: 'restrict', operations: ['write', 'unlink'], targets, statement: 'Protect the original files.'});
  for (const target of targets) assert.ok(text.includes(target));
  assert.ok(text.includes('写入、删除'));
  assert.equal(text.includes('/s/r/**'), false);
  assert.deepEqual(targets, ['/s/r/tests/**', '/s/r/config.toml', '/s/r/配置.json']);
});

test('guidance, expansion and unknown operations are never rewritten as a deny rule', () => {
  for (const record of [
    {effect: 'guidance', operations: ['write'], targets: ['/repo']},
    {effect: 'expand', operations: ['write'], targets: ['/repo']},
    {effect: 'restrict', operations: ['write'], targets: ['/repo/allowed']},
    {effect: 'restrict', operations: ['unknown'], targets: ['/repo']},
  ]) assert.equal(policySentence({...record, statement: 'Saved statement'}), 'Saved statement');
});

test('stored receipts, compiled candidates and guidance never become current enforcement claims', () => {
  assert.equal(policyOutcome({loaded: true, active: true, version: 42}), '已保存加载回执，当前生效未核验');
  assert.equal(policyOutcome({compilation: {status: 'compiled'}, active: true}), '已编译，未加载');
  assert.equal(policyOutcome({status: 'rejected', loaded: true}), '已拒绝，未应用');
  assert.equal(policyOutcome({effect: 'guidance', loaded: true}), '未生成执行规则');
  assert.equal(policyOutcome({review_status: 'pending', compilation: {status: 'compiled'}}), '等待确认');
});
