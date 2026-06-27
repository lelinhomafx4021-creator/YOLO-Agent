// 共享工具函数 — 全项目复用

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
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
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

export function shortTime(value) {
  return value ? String(value).replace('T', ' ').replace('Z', '').slice(0, 16) : '-'
}

// 英文日期格式化 → 中文友好格式
export function formatDate(iso) {
  if (!iso) return '-'
  try {
    const d = new Date(iso)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  } catch {
    return iso
  }
}
