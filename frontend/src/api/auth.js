/**
 * 登录门禁 API。
 */

export async function getAuthStatus() {
  const res = await fetch('/api/auth/status')
  return res.json()
}

export async function login(password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) {
    const text = await res.text()
    try {
      const parsed = JSON.parse(text)
      throw new Error(parsed.detail || text)
    } catch (e) {
      if (e.message) throw e
      throw new Error(text || `${res.status}`)
    }
  }
  return res.json()
}

export async function verifyToken() {
  const token = localStorage.getItem('yolops_token') || ''
  if (!token) return false
  try {
    const res = await fetch('/api/auth/verify', {
      method: 'POST',
      headers: { 'X-Auth-Token': token },
    })
    if (!res.ok) {
      localStorage.removeItem('yolops_token')
      return false
    }
    return true
  } catch {
    return false
  }
}

export function saveToken(token) {
  localStorage.setItem('yolops_token', token)
}

export function clearToken() {
  localStorage.removeItem('yolops_token')
}

export function hasToken() {
  return !!localStorage.getItem('yolops_token')
}
