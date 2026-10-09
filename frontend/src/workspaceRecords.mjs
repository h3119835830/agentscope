import {uniqueTasks} from './consoleState.mjs';

// A saved source-workspace ID is an association; a matching name/path is not.
export function workspaceTasks(workspace, tasks = []) {
  if (!workspace?.id) return [];
  return uniqueTasks(tasks).filter(task => task.workspace_id === workspace.id)
    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
}

export function workspaceSessions(workspace) {
  return [...new Set((workspace?.session_ids || []).filter(id => typeof id === 'string' && id))];
}

const operationNames = {write: '写入', unlink: '删除', read: '读取', execute: '执行', rename: '重命名', mkdir: '创建目录', rmdir: '删除目录'};

export function policySentence(record) {
  const targets = (record.targets || []).filter(target => typeof target === 'string' && target);
  const operations = record.operations || [];
  // A general restrictive delta may also reduce an allow-list. Only validated
  // deny-atoms have enough evidence to render operations as a prohibition.
  if (record.classification_origin === 'validated_atom_and_evidence_roles' && ['restrict', 'block'].includes(record.effect) && targets.length && operations.length && operations.every(op => operationNames[op])) {
    return `禁止对 ${targets.join('、')} 执行${operations.map(op => operationNames[op]).join('、')}操作。`;
  }
  return record.statement || '此记录没有保存策略语句。';
}

export function policyOutcome(record) {
  if (record.status === 'rejected' || record.review_status === 'rejected') return '已拒绝，未应用';
  if (record.status === 'expired') return '已过期，未应用';
  if (['guidance', 'guidance_only'].includes(record.effect)) return '未生成执行规则';
  if (record.loaded === true || record.loading?.loaded === true || ['loaded', 'partially_loaded'].includes(record.status)) return '已保存加载回执，当前生效未核验';
  if (['pending', 'pending_confirmation'].includes(record.review_status) || record.status === 'pending_confirmation') return '等待确认';
  if (record.compilation?.status === 'compiled' || record.compile_status === 'compiled') return '已编译，未加载';
  if (record.effect === 'no_change') return '保持原权限';
  return ({validated: '已校验，未加载', approved: '已确认，未加载', failed: '生成失败', invalid: '校验未通过'})[record.status] || '尚无加载回执';
}
