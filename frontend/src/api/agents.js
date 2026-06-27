import { del, get, post, put } from './client.js'

export function listSessions(projectId = null) {
  return get(`/agent/sessions${projectId ? `?project_id=${projectId}` : ''}`)
}

export function createSession(title, projectId = null) {
  return post('/agent/sessions', { title, project_id: projectId })
}

export function getMessages(sessionId) {
  return get(`/agent/sessions/${sessionId}/messages`)
}

export function sendMessage(sessionId, message, projectId = null) {
  return post(`/agent/sessions/${sessionId}/chat`, { message, project_id: projectId })
}

/**
 * 流式发送消息，返回 AbortController 和异步迭代器。
 * 用法: const { abort, stream } = sendMessageStream(sessionId, message, projectId)
 *        for await (const event of stream) { ... }
 */
export function sendMessageStream(sessionId, message, projectId = null) {
  const controller = new AbortController()
  const baseUrl = import.meta.env.VITE_API_BASE || ''

  const stream = (async function* () {
    const resp = await fetch(`${baseUrl}/api/agent/sessions/${sessionId}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, project_id: projectId }),
      signal: controller.signal,
    })

    if (!resp.ok) {
      const err = await resp.text().catch(() => 'stream error')
      throw new Error(err)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // 保留未完成的行
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6)
          if (data === '[DONE]') return
          try {
            yield JSON.parse(data)
          } catch { /* skip bad JSON */ }
        }
      }
    }
  })()

  return { abort: () => controller.abort(), stream }
}

export function getContext(projectId = null) {
  return get(`/agent/context${projectId ? `?project_id=${projectId}` : ''}`)
}

export function listPlans(status) {
  const qs = status ? `?status=${status}` : ''
  return get(`/agent/plans${qs}`)
}

export function savePlan(plan) {
  return post('/agent/plans', plan)
}

export function applyPlan(planId) {
  return post(`/agent/plans/${planId}/apply`)
}

export function updatePlanStatus(planId, status) {
  return put(`/agent/plans/${planId}/status`, { status })
}

export function markPlanRead(planId) {
  return post(`/agent/plans/${planId}/read`)
}

export function deleteSession(sessionId) {
  return del(`/agent/sessions/${sessionId}`)
}

export function renameSession(sessionId, title) {
  return put(`/agent/sessions/${sessionId}`, { title })
}
