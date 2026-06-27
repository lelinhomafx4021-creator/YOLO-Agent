import { del, get, post, put } from './client.js'

export function listProjects() {
  return get('/projects')
}

export function createProject(payload) {
  return post('/projects', payload)
}

export function updateProject(id, payload) {
  return put(`/projects/${id}`, payload)
}

export function deleteProject(id) {
  return del(`/projects/${id}`)
}

export function getProject(id) {
  return get(`/projects/${id}`)
}

export function bindProjectDataset(projectId, payload) {
  return post(`/projects/${projectId}/datasets`, payload)
}

export function unbindProjectDataset(projectId, bindingId) {
  return del(`/projects/${projectId}/datasets/${bindingId}`)
}

export function createProjectTrainingRun(projectId, payload) {
  return post(`/projects/${projectId}/training-runs`, payload)
}

export function createProjectEvaluationRun(projectId, payload) {
  return post(`/projects/${projectId}/evaluation-runs`, payload)
}

export function getEvaluationRun(id) {
  return get(`/projects/evaluation-runs/${id}`)
}

export function listEvaluationSamples(id, { page = 1, pageSize = 48 } = {}) {
  return get(`/projects/evaluation-runs/${id}/samples?page=${page}&page_size=${pageSize}`)
}

export function getEvaluationLog(id) {
  return get(`/projects/evaluation-runs/${id}/log`)
}

export function getEvaluationProgress(id) {
  return get(`/projects/evaluation-runs/${id}/progress`)
}
