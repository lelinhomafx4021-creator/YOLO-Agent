import { del, get, post, postForm, put } from './client.js'

export async function listModels(page = 1, pageSize = 50) {
  const res = await get(`/models?page=${page}&page_size=${pageSize}`)
  return { items: res.items || [], total: res.total || 0 }
}

export function getModelArtifacts(id) {
  return get(`/models/${id}/artifacts`)
}

export function promoteCandidate(id) {
  return post(`/models/${id}/candidate`)
}

export function promoteProduction(id) {
  return post(`/models/${id}/production`)
}

export function deleteModel(id) {
  return del(`/models/${id}`)
}

export function updateModel(id, payload) {
  return put(`/models/${id}`, payload)
}

export function listExportFormats() {
  return get('/models/export/formats')
}

export function exportModel(modelId, payload) {
  return post(`/models/${modelId}/export`, payload)
}

export function getExportLog(modelId) {
  return get(`/models/${modelId}/export/log`)
}

export function getExportStatus(modelId) {
  return get(`/models/${modelId}/export/status`)
}

export function importModel(formData) {
  return postForm('/models/import', formData)
}
