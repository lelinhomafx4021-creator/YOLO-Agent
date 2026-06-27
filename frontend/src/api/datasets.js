import { del, get, post, postForm, put } from './client.js'

export function getOverview() {
  return get('/overview')
}

export function createDataset(nameOrPayload, description = '') {
  const payload = typeof nameOrPayload === 'object' ? nameOrPayload : { name: nameOrPayload, description }
  return post('/datasets', payload)
}

export function updateDataset(id, payload) {
  return put(`/datasets/${id}`, payload)
}

export async function listVersions(page = 1, pageSize = 200) {
  const res = await get(`/dataset-versions?page=${page}&page_size=${pageSize}`)
  return { items: res.items || [], total: res.total || 0 }
}

export function listImages(versionIdOrOptions, options = {}) {
  const paramsInput = typeof versionIdOrOptions === 'object' ? versionIdOrOptions : { versionId: versionIdOrOptions, ...options }
  const { versionId, split, status, page = 1, pageSize, page_size } = paramsInput
  const params = new URLSearchParams()
  params.set('page', String(page))
  params.set('page_size', String(page_size ?? pageSize ?? 100))
  if (split) params.set('split', split)
  if (status) params.set('status', status)
  return get(`/dataset-versions/${versionId}/images?${params.toString()}`)
}

export function getAudit(versionId) {
  return get(`/dataset-versions/${versionId}/audit`)
}

/** 获取数据集 AI 质量分析（模糊/曝光/重复/标注一致性） */
export function getAiQuality(versionId, checks = 'quality,duplicates') {
  return get(`/dataset-versions/${versionId}/ai-quality?checks=${checks}`)
}

/** 获取单张图片质量 */
export function getImageQuality(versionId, imageId) {
  return get(`/dataset-versions/${versionId}/images/${imageId}/quality`)
}

export function getClassConfig(versionId) {
  return get(`/dataset-versions/${versionId}/class-config`)
}

export function updateClassConfig(versionId, payload) {
  return put(`/dataset-versions/${versionId}/class-config`, payload)
}

export function deleteDatasetVersion(versionId) {
  return del(`/dataset-versions/${versionId}`)
}

export async function uploadVersion(datasetId, file) {
  const form = new FormData()
  form.append('file', file)
  return postForm(`/datasets/${datasetId}/versions/upload`, form)
}

export async function uploadFolderVersion(datasetId, files) {
  const form = new FormData()
  Array.from(files).forEach(file => form.append('files', file, file.webkitRelativePath || file.name))
  return postForm(`/datasets/${datasetId}/versions/upload-folder`, form)
}

export async function uploadAnnotationFolder(datasetId, files, classText = '', onProgress) {
  const allFiles = Array.from(files)
  const batch = 50  // 每批 50 张
  let createdId = null
  let totalAdded = 0
  let batchErrors = []

  for (let i = 0; i < allFiles.length; i += batch) {
    const chunk = allFiles.slice(i, i + batch)
    const form = new FormData()
    chunk.forEach(f => form.append('files', f, f.webkitRelativePath || f.name))
    if (i === 0 && !createdId) form.append('class_names', classText)

    try {
      const url = createdId
        ? `/dataset-versions/${createdId}/append-images`
        : `/datasets/${datasetId}/annotation/upload-folder`
      const res = await postForm(url, form)

      if (!createdId) {
        createdId = res.id || res.version_id
        if (!createdId) throw new Error('创建数据集版本失败：未返回版本 ID')
      }

      totalAdded += (res.added || chunk.length)
      if (res.errors?.length) {
        batchErrors.push(...res.errors)
      }

      if (onProgress) {
        onProgress({
          done: Math.min(i + batch, allFiles.length),
          total: allFiles.length,
          added: totalAdded,
          errors: batchErrors.length,
        })
      }
    } catch (err) {
      // 单批失败不中断整体流程，但记录错误
      batchErrors.push(`批次 ${Math.floor(i / batch) + 1}: ${err?.message || String(err)}`)
      if (onProgress) {
        onProgress({
          done: Math.min(i + batch, allFiles.length),
          total: allFiles.length,
          added: totalAdded,
          errors: batchErrors.length,
          lastError: err?.message || String(err),
        })
      }
      // 如果是第一批失败，没有 createdId，则无法继续
      if (!createdId) throw err
    }
  }

  return { versionId: createdId, added: totalAdded, errors: batchErrors }
}


export function splitIntoIndependent(versionId, payload = {}) {
  return post(`/dataset-versions/${versionId}/split-into`, payload)
}

export function changeDatasetDtype(versionId, dtype) {
  return post(`/dataset-versions/${versionId}/dtype`, { dtype })
}

export function getAnnotationProgress(versionId) {
  return get(`/dataset-versions/${versionId}/annotation-progress`)
}

export function getDataYaml(versionId) {
  return get(`/dataset-versions/${versionId}/data-yaml`)
}

export function appendImagesToVersion(versionId, files, onProgress) {
  // 分批追加图片到已有数据集版本
  const allFiles = Array.from(files)
  const batch = 50
  let totalAdded = 0
  const errors = []

  const uploadBatch = async (startIdx) => {
    if (startIdx >= allFiles.length) return
    const chunk = allFiles.slice(startIdx, startIdx + batch)
    const form = new FormData()
    chunk.forEach(f => form.append('files', f, f.webkitRelativePath || f.name))

    try {
      const res = await postForm(`/dataset-versions/${versionId}/append-images`, form)
      totalAdded += (res.added || 0)
      if (res.errors?.length) errors.push(...res.errors)
      if (onProgress) onProgress({ done: Math.min(startIdx + batch, allFiles.length), total: allFiles.length, added: totalAdded, errors: errors.length })
    } catch (err) {
      errors.push(`批次 ${Math.floor(startIdx / batch) + 1}: ${err?.message || String(err)}`)
      if (onProgress) onProgress({ done: Math.min(startIdx + batch, allFiles.length), total: allFiles.length, added: totalAdded, errors: errors.length, lastError: err?.message })
    }

    await uploadBatch(startIdx + batch)
  }

  return uploadBatch(0).then(() => ({ versionId, added: totalAdded, errors }))
}

// ── 合集管理 ──

export function listCollections() {
  return get('/collections')
}

export function renameCollection(oldName, newName) {
  return put('/collections/rename', { old_name: oldName, new_name: newName })
}
