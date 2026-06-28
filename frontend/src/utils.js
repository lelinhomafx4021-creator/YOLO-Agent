const STATUS_MAP = {
  created: '已创建',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  imported: '已导入',
  annotation: '待标注',
  active: '活跃',
  archived: '已归档',
}

export function statusText(status) {
  return STATUS_MAP[status] || status || '-'
}

export function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function formatError(err, fallback = '操作失败') {
  return err?.message?.replace(/^Error:\s*/, '') || fallback
}

export function basename(path) {
  return String(path || '').split(/[\\/]/).pop() || '-'
}

export function fmtMetric(value) {
  return value === null || value === undefined ? '-' : Number(value).toFixed(3)
}

function toDate(value) {
  if (!value) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

function pad(value) {
  return String(value).padStart(2, '0')
}

export function formatDateTime(value, { withSeconds = false } = {}) {
  const date = toDate(value)
  if (!date) return '-'
  const base = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  return withSeconds ? `${base}:${pad(date.getSeconds())}` : base
}

export function shortTime(value) {
  return formatDateTime(value)
}

export function formatDate(value) {
  return formatDateTime(value)
}

export function formatClockDuration(totalSeconds) {
  const value = Number(totalSeconds)
  if (!Number.isFinite(value) || value < 0) return '-'
  const seconds = Math.round(value)
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hours > 0) return `${pad(hours)}:${pad(minutes)}:${pad(secs)}`
  return `${pad(minutes)}:${pad(secs)}`
}

export function formatRemainingFromMs(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value) || value < 0) return '-'
  return formatClockDuration(value / 1000)
}

export function displayTrainingName(item) {
  return item?.training_display_name || item?.display_name || item?.run_id || '-'
}

export function displayModelName(item) {
  if (!item) return '-'
  return item.model_display_name || item.display_model_name || item.model_name || item.run_id || '-'
}

export function displayDatasetName(item) {
  if (!item) return '-'
  if (item.dataset_display_name) return item.dataset_display_name
  const datasetName = item.dataset_name || item.model_dataset_name || ''
  const version = item.dataset_version_name || item.dataset_version || item.version || ''
  if (datasetName && version) return `${datasetName} / ${version}`
  return datasetName || version || '-'
}
