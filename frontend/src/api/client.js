const BASE_URL = '/api'

// 从 localStorage 读取 token
function getAuthToken() {
  return localStorage.getItem('yolops_token') || ''
}

export async function request(path, options = {}) {
  try {
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    }
    const token = getAuthToken()
    if (token) {
      headers['X-Auth-Token'] = token
    }

    const res = await fetch(`${BASE_URL}${path}`, {
      headers,
      ...options,
    })

    // 401 → 触发登录
    if (res.status === 401) {
      localStorage.removeItem('yolops_token')
      window.dispatchEvent(new Event('auth-required'))
      throw new Error('未登录或登录已过期')
    }

    if (!res.ok) {
      const text = await res.text()
      try {
        const parsed = JSON.parse(text)
        throw new Error(parsed.detail || parsed.message || text || `请求失败 (${res.status})`)
      } catch (e) {
        if (e.message && !e.message.includes('请求失败')) throw e
        throw new Error(text || `请求失败 (${res.status})`)
      }
    }

    if (res.status === 204) return null
    return res.json()
  } catch (err) {
    if (err instanceof TypeError && err.message.includes('fetch')) {
      throw new Error('网络连接失败，请检查后端是否正在运行')
    }
    throw err
  }
}

export const get = (path) => request(path)
export const post = (path, body) => request(path, { method: 'POST', body: JSON.stringify(body) })
export const put = (path, body) => request(path, { method: 'PUT', body: JSON.stringify(body) })
export const del = (path) => request(path, { method: 'DELETE' })

// multipart/form-data 上传（不设 Content-Type，让浏览器自动设置 boundary）
export async function postForm(path, formData) {
  const token = getAuthToken()
  const headers = {}
  if (token) headers['X-Auth-Token'] = token
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: formData,
  })
  if (res.status === 401) {
    localStorage.removeItem('yolops_token')
    window.dispatchEvent(new Event('auth-required'))
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) {
    const text = await res.text()
    try {
      const parsed = JSON.parse(text)
      throw new Error(parsed.detail || parsed.message || text)
    } catch (e) {
      if (e.message && !e.message.includes('请求失败')) throw e
      throw new Error(text || `请求失败 (${res.status})`)
    }
  }
  if (res.status === 204) return null
  return res.json()
}

// 带 auth 的通用 GET（用于原始 fetch 调用替换）
export async function authFetch(path, options = {}) {
  const token = getAuthToken()
  const headers = { ...(options.headers || {}) }
  if (token) headers['X-Auth-Token'] = token
  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers })
  if (res.status === 401) {
    localStorage.removeItem('yolops_token')
    window.dispatchEvent(new Event('auth-required'))
    throw new Error('未登录或登录已过期')
  }
  if (!res.ok) {
    const text = await res.text()
    try { const p = JSON.parse(text); throw new Error(p.detail || p.message || text) } catch (e) { if (e.message && !e.message.includes('请求失败')) throw e; throw new Error(text || `请求失败 (${res.status})`) }
  }
  if (res.status === 204) return null
  return res.json()
}
