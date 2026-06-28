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

export async function logout() {
  const token = localStorage.getItem('yolops_token') || ''
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers: token ? { 'X-Auth-Token': token } : {},
    })
  } catch {
    // ignore lock/logout network failures on the client
  }
}

export async function changePassword(oldPassword, newPassword) {
  const token = localStorage.getItem('yolops_token') || ''
  const res = await fetch('/api/auth/password', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { 'X-Auth-Token': token } : {}),
    },
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
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
