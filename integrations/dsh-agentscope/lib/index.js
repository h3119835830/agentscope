import { defineTool } from '@deepseek-ai/dsh-tools'
import z from '@deepseek-ai/schemastery'
import { randomUUID } from 'node:crypto'

export const name = 'agentscope-policy-tools'
export const inject = ['tools']

export const Config = z.object({
  baseUrl: z.string().default('http://127.0.0.1:8000'),
})

function connection(config) {
  const baseUrl = (process.env.AGENTSCOPE_URL || config.baseUrl).replace(/\/$/, '')
  const taskId = process.env.AGENTSCOPE_TASK_ID || ''
  const token = process.env.AGENTSCOPE_TASK_TOKEN || ''
  if (!taskId || !token) throw new Error('当前 DSH 会话不是由 AgentScope 受管启动；缺少任务凭据。')
  return { baseUrl, taskId, token }
}

async function request(config, path, options = {}, namespace = 'plugin') {
  const { baseUrl, taskId, token } = connection(config)
  const response = await fetch(`${baseUrl}/api/${namespace}/tasks/${encodeURIComponent(taskId)}${path}`, {
    ...options,
    headers: {
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      ...(options.headers || {}),
    },
    signal: AbortSignal.timeout(8000),
    redirect: 'error',
  })
  const value = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(value.detail || `AgentScope 请求失败 (${response.status})`)
  return value
}

const textOutput = {
  schema: { type: 'string' },
  render: (_args, value) => [{ type: 'text', text: value }],
}

export function apply(ctx, config) {
  ctx.tools.register(defineTool({
    name: 'agentscope_get_current_scope',
    description: '读取当前任务经人工批准的策略版本、历史策略参考和运行时限制。此工具只读。',
    parameters: {},
    output: textOutput,
    async execute() {
      const value = await request(config, '/scope')
      const bridge = await request(config, '/context', {}, 'agent')
      return JSON.stringify({ ...value, agent_bridge: bridge }, null, 2)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'agentscope_request_scope_change',
    description: '为当前任务提交 Scope 变更申请。申请只进入人工审核队列，不会直接改变权限。restrict 需要指定仓库内已存在的允许写入目录；expand 申请受控任务输出目录写权限。',
    parameters: {
      kind: { type: 'string', required: true, description: '变更类型：restrict 或 expand' },
      path: { type: 'string', required: true, description: 'restrict 时填写仓库内已存在的允许写入目录；expand 时填写空字符串' },
      justification: { type: 'string', required: true, description: '解释当前任务为何需要这项变更，至少 4 个字符' },
      request_key: { type: 'string', description: '可选的幂等键；重试同一申请保持键和内容不变' },
    },
    output: textOutput,
    async execute(args) {
      if (!['restrict', 'expand'].includes(args.kind)) throw new Error('kind 只能为 restrict 或 expand')
      if (args.justification.trim().length < 4) throw new Error('请提供至少 4 个字符的变更理由')
      const context = await request(config, '/context', {}, 'agent')
      const value = await request(config, '/scope-requests', {
        method: 'POST',
        body: JSON.stringify({ kind: args.kind, path: args.path || null, justification: args.justification,
          expected_snapshot_hash: context.snapshot_hash, request_key: args.request_key || randomUUID() }),
      }, 'agent')
      return `Scope 申请 ${value.id} 已提交，状态：${value.status}。权限在审核批准前不会变化。`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'agentscope_read_messages',
    description: '读取当前任务的用户消息和 Scope 审核结果。读取不等于处理；按消息 ID 去重，处理后使用确认工具。',
    parameters: { after: { type: 'string', description: '可选的已完成消息序号，默认 0。整批处理完成前不要推进游标。' } },
    output: textOutput,
    async execute(args) {
      const after = Number(args.after || 0)
      if (!Number.isSafeInteger(after) || after < 0) throw new Error('消息序号必须是非负整数')
      return JSON.stringify(await request(config, `/messages?after=${after}`, {}, 'agent'), null, 2)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'agentscope_acknowledge_message',
    description: '确认消息已接收 received 或已处理 handled。实际更新任务上下文或完成处理后才报告 handled；回执不证明内核策略生效。',
    parameters: {
      message_id: { type: 'string', required: true, description: '消息 ID' },
      status: { type: 'string', required: true, description: 'received 或 handled' },
    },
    output: textOutput,
    async execute(args) {
      if (!['received', 'handled'].includes(args.status)) throw new Error('状态只能为 received 或 handled')
      return JSON.stringify(await request(config, `/messages/${encodeURIComponent(args.message_id)}/ack`, {
        method: 'POST', body: JSON.stringify({ status: args.status }),
      }, 'agent'), null, 2)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'agentscope_report_feedback',
    description: '上报简短任务进展、工具反馈或 Scope 阻断。Agent 自报不作为内核证据；不要包含凭据、原始敏感日志或私有推理。',
    parameters: {
      kind: { type: 'string', required: true, description: 'tool_feedback、scope_blocked、progress 或 result' },
      summary: { type: 'string', required: true, description: '事实摘要，最多 2000 字符' },
      operation: { type: 'string', description: '操作名称' },
      target: { type: 'string', description: '操作对象，避免敏感内容' },
      request_key: { type: 'string', description: '可选的幂等键；重试同一反馈保持不变' },
    },
    output: textOutput,
    async execute(args) {
      const context = await request(config, '/context', {}, 'agent')
      return JSON.stringify(await request(config, '/feedback', { method: 'POST', body: JSON.stringify({
        kind: args.kind, summary: args.summary, operation: args.operation || '', target: args.target || '',
        request_key: args.request_key || randomUUID(), expected_snapshot_hash: context.snapshot_hash,
      }) }, 'agent'), null, 2)
    },
  }))
}
