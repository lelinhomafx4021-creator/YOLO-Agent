import { reactive } from 'vue'

let nextId = 1

export const notificationState = reactive({
  items: [],
})

export function pushNotification(payload) {
  const item = {
    id: nextId++,
    tone: payload.tone || 'info',
    title: payload.title || '通知',
    message: payload.message || '',
    url: payload.url || '',
    createdAt: Date.now(),
  }
  notificationState.items.unshift(item)
  notificationState.items = notificationState.items.slice(0, 8)

  if ('Notification' in window && Notification.permission === 'granted') {
    try {
      new Notification(item.title, { body: item.message || undefined })
    } catch {}
  }

  window.setTimeout(() => dismissNotification(item.id), payload.duration || 8000)
  return item
}

export function dismissNotification(id) {
  const index = notificationState.items.findIndex(item => item.id === id)
  if (index >= 0) notificationState.items.splice(index, 1)
}

export async function requestBrowserNotificationPermission() {
  if (!('Notification' in window)) return 'unsupported'
  if (Notification.permission !== 'default') return Notification.permission
  try {
    return await Notification.requestPermission()
  } catch {
    return Notification.permission
  }
}
