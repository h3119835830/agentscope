const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
const text = value => typeof value === 'string' ? value : '';
const scalar = value => typeof value === 'string' || Number.isFinite(value) ? value : null;
const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string');

export function runtimeHooksPath(task, before = null) {
  const query = new URLSearchParams({limit:'50'});
  if (before !== null && before !== '') query.set('before', before);
  return `/api/tasks/${encodeURIComponent(task)}/archive/runtime-hooks?${query}`;
}

export function readRuntimeHooksPage(value) {
  if (!object(value) || value.history_only !== true || value.live !== false ||
      !Array.isArray(value.records) || !Number.isInteger(value.total) || value.total < 0 ||
      value.next_cursor !== null && typeof value.next_cursor !== 'string') {
    throw new Error('Hook 历史记录格式不完整，请重新读取。');
  }
  const mechanism = value.mechanism;
  if (!object(mechanism) || mechanism.source !== 'current_definition' ||
      mechanism.historical_configuration !== false ||
      mechanism.configuration_status !== 'not_historical_configuration' ||
      !strings(mechanism.events) || !strings(mechanism.sequence)) {
    throw new Error('当前 Hook 接入说明未标明来源，不能作为历史配置展示。');
  }
  const records = value.records.map(record => {
    if (!object(record) || typeof record.id !== 'string' || !record.id ||
        !strings(record.evidence_refs) || !strings(record.missing_fields)) {
      throw new Error('Hook 触发记录缺少公开编号或证据字段。');
    }
    const trigger = object(record.trigger) ? record.trigger : {};
    if (trigger.observations !== undefined && !Array.isArray(trigger.observations)) {
      throw new Error('Hook 观测记录格式不完整。');
    }
    const observations = (trigger.observations || []).map(observation => {
      if (!object(observation) || !strings(observation.missing_fields)) throw new Error('Hook 观测记录格式不完整。');
      return {
        category:text(observation.category), type:text(observation.type),
        seq:scalar(observation.seq), content_hash:text(observation.content_hash),
        status:observation.status === 'recorded' ? 'recorded' : 'unrecorded',
        missing_fields:[...observation.missing_fields],
      };
    });
    return {
      id:record.id, job_id:text(record.job_id), request_id:text(record.request_id),
      time:text(record.time), generation_status:text(record.generation_status),
      trigger:{name:text(trigger.name), actor:text(trigger.actor), revision:scalar(trigger.revision),
        turn:scalar(trigger.turn), accepted_turn:scalar(trigger.accepted_turn), observations,
        observations_status:trigger.observations_status === 'recorded' ? 'recorded' : 'unrecorded'},
      evidence_refs:[...record.evidence_refs], missing_fields:[...record.missing_fields],
      status:record.status === 'recorded' ? 'recorded' : 'unrecorded',
    };
  });
  return {
    mechanism:{name:text(mechanism.name), events:[...mechanism.events], sequence:[...mechanism.sequence]},
    records, total:value.total, next_cursor:value.next_cursor, history_only:true, live:false,
  };
}

export function mergeRuntimeHookRecords(before, after) {
  return [...new Map([...before, ...after].map(record => [record.id, record])).values()];
}

export function runtimeHooksState(task = '') {
  return {task, request:0, records:[], mechanism:null, total:0, next_cursor:null, busy:false, loaded:false, error:''};
}

export function runtimeHooksReducer(state, action) {
  if (action.type === 'start') {
    const base = action.append && state.task === action.task ? state : runtimeHooksState(action.task);
    return {...base, request:action.request, busy:true, error:''};
  }
  if (state.task !== action.task || state.request !== action.request) return state;
  if (action.type === 'success') {
    return {...state, ...action.page,
      records:action.append ? mergeRuntimeHookRecords(state.records, action.page.records) : action.page.records,
      busy:false, loaded:true, error:''};
  }
  if (action.type === 'error') return {...state, busy:false, error:action.error};
  return state;
}

const labels = {
  user_message:'用户消息', user:'管理员约束', administrator:'管理员约束', agent:'Agent', controller:'控制面', pi:'Pi',
  native_context:'原生上下文变化', native_user:'真实用户消息', verified_feedback:'误拦截复核',
  control_review:'控制面复核', recovery:'原生会话恢复', DSH:'执行能力申请',
  native_hook:'原生 Hook', runtime_observation:'运行时观测', manual_reassessment:'手动重新评估',
  system:'系统上下文', developer:'开发者上下文', tool_schema:'工具定义', effective_context:'有效上下文',
  system_prompt:'系统提示词', instructions:'开发者指令', tools:'工具定义', memory:'压缩记忆', memory_prune:'记忆裁剪', context:'有效上下文',
  'system/message':'系统消息', 'developer/message':'开发者消息', 'request/header':'请求工具定义',
  'user/message':'用户消息上下文',
  'compaction/summary':'上下文压缩摘要', 'compaction/prune':'上下文裁剪', 'context/snapshot':'有效上下文快照',
  compaction:'上下文压缩记忆', kernel:'ActPlane 拒绝反馈', kernel_denial:'内核拒绝', false_positive:'误拦截核验',
  completed:'已完成', complete:'已完成', queued:'排队中', running:'生成中', failed:'失败',
  cancelled:'已取消', interrupted:'已中断', pending:'待处理',
  'trigger.name':'触发来源', 'trigger.actor':'触发方', 'trigger.revision':'上下文修订',
  'trigger.turn':'执行轮次', 'trigger.accepted_turn':'接收轮次', 'trigger.observations':'观测条目',
  trigger:'触发材料', evidence_refs:'证据引用', request_id:'关联请求', job_id:'生成作业',
  actor:'触发方', revision:'上下文修订', turn:'执行轮次', accepted_turn:'接收轮次',
  observations:'来源观测', ambiguous_request_source:'请求来源不唯一',
  category:'观测类别', type:'事件类型', seq:'观测序号', content_hash:'内容 hash',
};
export const runtimeHookLabel = value => labels[value] || text(value) || '未记录';
export const runtimeHookMissingLabel = value => value === 'context' ? '冻结上下文快照' : runtimeHookLabel(value);
export const runtimeHookStatus = record => record.status === 'recorded' && record.trigger?.name ? '触发已记录' : '触发材料未记录';
export function runtimeHookPosition(record) {
  const trigger = record.trigger || {}, parts = [];
  if (trigger.turn !== null && trigger.turn !== undefined && trigger.turn !== '') parts.push(`轮次 ${trigger.turn}`);
  if (trigger.revision !== null && trigger.revision !== undefined && trigger.revision !== '') parts.push(`修订 ${trigger.revision}`);
  return parts.join(' / ') || '未记录';
}
export function runtimeHookTime(value) {
  return value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString('zh-CN', {hour12:false}) : '时间未记录';
}

export function runtimeHookFocusState(task) {
  return {task, record:null, buttons:new Map()};
}
export function registerRuntimeHookButton(state, task, id, button) {
  if (state.task !== task) return;
  if (button) state.buttons.set(id, button);
  else state.buttons.delete(id);
}
export function restoreRuntimeHookFocus(state, task, id) {
  if (state.task !== task || state.record !== id) return false;
  const button = state.buttons.get(id);
  if (!button?.isConnected) return false;
  button.focus({preventScroll:true});
  return true;
}
