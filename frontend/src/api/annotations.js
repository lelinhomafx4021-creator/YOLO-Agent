/**
 * 标注模块 API 接口
 * 提供图片标注的增、删、改、查，以及预标注和版本回滚功能
 */

import { get, post, put } from './client.js'

/** 获取指定图片的标注数据 */
export function getAnnotation(imageId) { return get(`/annotations/${imageId}`) }

/**
 * 更新指定图片的标注信息
 * @param {string} imageId - 图片 ID
 * @param {Array}  boxes   - 标注框列表
 * @param {string} status  - 标注状态，默认 'reviewed'（已审核）
 */
export function updateAnnotation(imageId, boxes, status = 'reviewed') {
  return put(`/annotations/${imageId}`, { boxes, status })
}

/**
 * 对指定图片执行模型预标注
 * @param {string} imageId   - 图片 ID
 * @param {string} modelPath - 模型路径，默认 'yolo11n.pt'
 * @param {number} conf      - 置信度阈值，默认 0.25
 */
export function prelabel(imageId, modelPath = 'yolo11n.pt', conf = 0.25, classMapping = null, dropUnmapped = true) {
  const body = { model_path: modelPath, conf, drop_unmapped: dropUnmapped }
  if (classMapping) body.class_mapping = classMapping
  return post(`/annotations/${imageId}/prelabel`, body)
}

/**
 * 批量预标注 — 对数据集版本中所有未复核图片执行模型标注
 * @param {number} versionId    - 数据集版本 ID
 * @param {string} modelPath    - 模型路径
 * @param {number} conf         - 置信度阈值
 * @param {object} classMapping - 类别映射 {模型class: 数据集class}
 * @param {boolean} autoMap     - 是否自动按名称匹配
 */
export function batchPrelabel(versionId, modelPath = 'yolo11n.pt', conf = 0.25, classMapping = null, autoMap = false, dropUnmapped = true) {
  const body = { version_id: versionId, model_path: modelPath, conf, drop_unmapped: dropUnmapped }
  if (classMapping) body.class_mapping = classMapping
  if (autoMap) body.auto_map = true
  return post('/annotations/batch-prelabel', body)
}

/** 获取模型类别列表（用于映射参考） */
export function getModelClasses(modelPath = 'yolo11n.pt') {
  return get(`/annotations/model-classes?model_path=${encodeURIComponent(modelPath)}`)
}

/** 获取指定图片的标注版本历史 */
export function getRevisionHistory(imageId) { return get(`/annotations/${imageId}/history`) }

/** 获取指定版本的历史详情 */
export function getRevisionDetail(imageId, revisionId) { return get(`/annotations/${imageId}/history/${revisionId}`) }

/**
 * 将标注恢复到指定历史版本
 * @param {string} imageId    - 图片 ID
 * @param {string} revisionId - 目标版本 ID
 */
export function restoreRevision(imageId, revisionId) { return post(`/annotations/${imageId}/restore/${revisionId}`) }
