import { spawn } from 'node:child_process'
import fs from 'node:fs/promises'
import path from 'node:path'
import z from '@deepseek-ai/schemastery'
import { createUserMessage } from '@deepseek-ai/dsh-llm'

/** The DSH loader name for this plugin. */
export const name = 'actplane-feedback-native'

/**
 * The binary is intentionally configurable so a user-installed ActPlane can
 * be used instead of the default system installation.
 */
export const Config = z.object({
  binary: z.string().default('/usr/local/bin/actplane'),
  timeoutMs: z.number().default(5000),
})

function commandOf(args) {
  if (args && typeof args === 'object' && typeof args.command === 'string') return args.command
  return ''
}

function readAdditionalContext(raw) {
  if (typeof raw !== 'string' || raw.trim().length === 0) return ''
  try {
    const parsed = JSON.parse(raw)
    const value = parsed?.hookSpecificOutput?.additionalContext
    return typeof value === 'string' ? value.trim() : ''
  } catch {
    return ''
  }
}

function inside(child, parent) {
  const relative = path.relative(parent, child)
  return relative === '' || (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
}

async function runtimeHookFiles(config, cwd, currentStatePath, currentFeedbackPath) {
  const taskId = process.env.AGENTSCOPE_TASK_ID || ''
  const token = process.env.AGENTSCOPE_TASK_TOKEN || ''
  const current = { statePath: currentStatePath, feedbackPath: currentFeedbackPath }
  if (!taskId || !token) return current

  const baseUrl = (process.env.AGENTSCOPE_URL || config.baseUrl).replace(/\/$/, '')
  try {
    const response = await fetch(`${baseUrl}/api/plugin/tasks/${encodeURIComponent(taskId)}/scope`, {
      headers: { authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(3000),
    })
    if (!response.ok) return current
    const scope = await response.json()
    const paths = (scope.runtime_restrictions || [])
      .filter(item => typeof item.path === 'string' && item.path.length > 0)
      .map(item => path.resolve(item.path))
    if (!paths.length || paths.some(item => !inside(item, cwd))) return current

    // Multiple restrictions intersect. Keep the feedback cursor only under a
    // directory that remains writable under every approved restriction.
    let writable = paths[0]
    for (const candidate of paths.slice(1)) {
      if (inside(candidate, writable)) writable = candidate
      else if (!inside(writable, candidate)) return current
    }
    const nextStatePath = path.join(writable, '.agentscope-feedback-hook.state.json')
    const nextFeedbackPath = path.join(writable, '.agentscope-actplane-feedback.txt')
    const state = JSON.parse(await fs.readFile(currentStatePath, 'utf8'))
    if (!Number.isInteger(state.root_pid) || !Number.isInteger(state.offset)) return current
    const feedbackText = await fs.readFile(currentFeedbackPath, 'utf8').catch(() => '')
    const nextState = {
      ...state,
      feedback_file: nextFeedbackPath,
      // The hook runs as a child of the DSH process. ActPlane's anchor PID is
      // a sibling of this child domain in AgentScope's watch/launch topology,
      // so bind this per-session cursor to the DSH PID for feedback matching.
      root_pid: process.pid,
      offset: state.offset,
    }
    await fs.writeFile(nextFeedbackPath, feedbackText, { mode: 0o600 })
    await fs.writeFile(nextStatePath, JSON.stringify(nextState), { mode: 0o600 })
    return { statePath: nextStatePath, feedbackPath: nextFeedbackPath }
  } catch {
    return current
  }
}

/** Run one ActPlane PostToolUse-compatible hook without invoking a shell. */
function runFeedback(binary, cwd, payload, timeoutMs, signal, hookFiles) {
  return new Promise((resolve) => {
    if (signal?.aborted) {
      resolve('')
      return
    }

    const child = spawn(binary, ['feedback-hook'], {
      cwd,
      env: {
        ...process.env,
        ...(hookFiles?.statePath ? { ACTPLANE_HOOK_STATE: hookFiles.statePath } : {}),
        ...(hookFiles?.feedbackPath ? { ACTPLANE_FEEDBACK_FILE: hookFiles.feedbackPath } : {}),
      },
      stdio: ['pipe', 'pipe', 'ignore'],
    })
    let stdout = ''
    let settled = false
    let timer

    const finish = (value) => {
      if (settled) return
      settled = true
      if (timer !== undefined) clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
      resolve(value)
    }
    const abort = () => {
      child.kill('SIGTERM')
      finish('')
    }

    timer = setTimeout(() => {
      child.kill('SIGTERM')
      finish('')
    }, timeoutMs)

    child.stdout.setEncoding('utf8')
    child.stdout.on('data', (chunk) => {
      stdout += chunk
    })
    child.once('error', () => finish(''))
    child.once('close', (code) => finish(code === 0 ? readAdditionalContext(stdout) : ''))
    signal?.addEventListener('abort', abort, { once: true })
    child.stdin.end(JSON.stringify(payload))
  })
}

export function apply(ctx, config) {
  let hookStatePath = process.env.ACTPLANE_HOOK_STATE || path.join(process.cwd(), '.actplane', 'feedback-hook.state.json')
  let feedbackPath = process.env.ACTPLANE_FEEDBACK_FILE || path.join(process.cwd(), '.actplane', 'last-violation.txt')
  ctx.on('tools/post-execute', async (exec, _result, next) => {
    const downstream = await next()
    const cwd = exec.agent?.session?.header?.cwd ?? process.cwd()
    const payload = {
      cwd,
      hook_event_name: 'PostToolUse',
      tool_name: exec.name,
      tool_input: { command: commandOf(exec.arguments) },
      tool_use_id: exec.callId,
    }
    const hookFiles = await runtimeHookFiles(config, cwd, hookStatePath, feedbackPath)
    hookStatePath = hookFiles.statePath
    feedbackPath = hookFiles.feedbackPath
    const text = await runFeedback(config.binary, cwd, payload, config.timeoutMs, exec.signal, hookFiles)
    if (!text) return downstream

    const context = createUserMessage({
      content: [{ type: 'text', text }],
      source: { kind: 'plugin', plugin: name },
    })
    return {
      ...downstream,
      additionalContexts: [context, ...(downstream.additionalContexts ?? [])],
    }
  })
}
