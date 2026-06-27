const STORAGE_KEY = 'yolops.activeProjectContext'
const EVENT_NAME = 'yolops:active-project-context'

export function readActiveProjectContext() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setActiveProjectContext(project) {
  if (!project) return
  const normalized = {
    id: project.id,
    name: project.name || '未命名项目',
    taskType: project.task_type || project.taskType || 'detect',
    status: project.status || 'active',
  }
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  localStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: normalized }))
}

export function clearActiveProjectContext() {
  sessionStorage.removeItem(STORAGE_KEY)
  localStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: null }))
}

export function onActiveProjectContextChange(handler) {
  const listener = (event) => handler(event.detail || readActiveProjectContext())
  window.addEventListener(EVENT_NAME, listener)
  window.addEventListener('storage', listener)
  return () => {
    window.removeEventListener(EVENT_NAME, listener)
    window.removeEventListener('storage', listener)
  }
}
