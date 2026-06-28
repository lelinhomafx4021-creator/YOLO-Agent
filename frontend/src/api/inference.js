import { authFetch, del as deleteRequest, postForm } from './client.js'

export async function predict(modelId, files, conf, iou, batchName = '') {
  const form = new FormData()
  form.append('model_id', String(modelId))
  for (const file of files) {
    form.append('files', file)
  }
  form.append('conf', String(conf))
  form.append('iou', String(iou))
  form.append('save_result', 'true')
  form.append('batch_name', batchName)
  return postForm('/inference/predict', form)
}

export function listHistory(limit = 20) {
  return authFetch(`/inference/history?limit=${limit}`)
}

export function getInferenceLog(sessionId) {
  return authFetch(`/inference/${sessionId}/log`)
    .catch(() => ({ log: '' }))
}

export function deleteInferenceHistory(sessionId) {
  return deleteRequest(`/inference/${sessionId}`)
}
