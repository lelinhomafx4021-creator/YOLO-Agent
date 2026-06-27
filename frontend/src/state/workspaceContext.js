const STORAGE_KEY = 'yolops.activeDatasetContext'
const EVENT_NAME = 'yolops:active-dataset-context'

export function readActiveDatasetContext() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export function setActiveDatasetContext(context) {
  if (!context) return
  const normalized = {
    datasetId: context.datasetId ?? context.dataset_id ?? null,
    versionId: context.versionId ?? context.version_id ?? context.id ?? null,
    datasetName: context.datasetName ?? context.dataset_name ?? context.name ?? '未命名数据集',
    version: context.version ?? '-',
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: normalized }))
}

export function clearActiveDatasetContext() {
  localStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: null }))
}

export function onActiveDatasetContextChange(handler) {
  const listener = (event) => handler(event.detail || readActiveDatasetContext())
  window.addEventListener(EVENT_NAME, listener)
  window.addEventListener('storage', listener)
  return () => {
    window.removeEventListener(EVENT_NAME, listener)
    window.removeEventListener('storage', listener)
  }
}
