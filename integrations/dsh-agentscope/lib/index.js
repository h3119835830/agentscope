import { defineTool } from '@deepseek-ai/dsh-tools'
import z from '@deepseek-ai/schemastery'

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

async function request(config, path, options = {}) {
  const { baseUrl, taskId, token } = connection(config)
  const response = await fetch(`${baseUrl}/api/plugin/tasks/${encodeURIComponent(taskId)}${path}`, {
    ...options,
    headers: {
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      ...(options.headers || {}),
    },
    signal: AbortSignal.timeout(8000),
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
      return JSON.stringify(value, null, 2)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'agentscope_request_scope_change',
    description: '为当前任务提交 Scope 变更申请。申请只进入人工审核队列，不会直接改变权限。restrict 需要指定仓库内已存在的允许写入目录；expand 申请受控任务输出目录写权限。',
    parameters: {
      kind: { type: 'string', required: true, description: '变更类型：restrict 或 expand' },
      path: { type: 'string', required: true, description: 'restrict 时填写仓库内已存在的允许写入目录；expand 时填写空字符串' },
      justification: { type: 'string', required: true, description: '解释当前任务为何需要这项变更，至少 4 个字符' },
    },
    output: textOutput,
    async execute(args) {
      if (!['restrict', 'expand'].includes(args.kind)) throw new Error('kind 只能为 restrict 或 expand')
      if (args.justification.trim().length < 4) throw new Error('请提供至少 4 个字符的变更理由')
      const value = await request(config, '/scope-requests', {
        method: 'POST',
        body: JSON.stringify({ kind: args.kind, path: args.path || null, justification: args.justification }),
      })
      return `Scope 申请 ${value.id} 已提交，状态：${value.status}。权限在审核批准前不会变化。`
    },
  }))
}
