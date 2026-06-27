import { del, get } from './client.js'

export async function listRuns(page = 1, pageSize = 50) {
  const res = await get(`/training-runs?page=${page}&page_size=${pageSize}`)
  return { items: res.items || [], total: res.total || 0 }
}

export function getRunDetail(id) {
  return get(`/training-runs/${id}/detail`)
}

export function getLog(id) {
  return get(`/training-runs/${id}/log`)
}

export function getProgress(id) {
  return get(`/training-runs/${id}/progress`)
}

export function deleteRun(id) {
  return del(`/training-runs/${id}`)
}

export function updateRun(id, payload) {
  return put(`/training-runs/${id}`, payload)
}
