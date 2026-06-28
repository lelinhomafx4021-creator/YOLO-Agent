import { authFetch, postForm } from './client.js'

export async function cameraFrame(modelId, frameBlob, conf, iou) {
  const form = new FormData()
  form.append('model_id', String(modelId))
  form.append('frame', frameBlob, 'frame.jpg')
  form.append('conf', String(conf))
  form.append('iou', String(iou))
  return postForm('/camera/frame', form)
}

export async function cameraSnapshot(modelId, frameBlob, conf, iou, batchName) {
  const form = new FormData()
  form.append('model_id', String(modelId))
  form.append('frame', frameBlob, 'frame.jpg')
  form.append('conf', String(conf))
  form.append('iou', String(iou))
  form.append('batch_name', batchName || '')
  return postForm('/camera/snapshot', form)
}

export async function startLocalStream(deviceIndex, modelId, conf, iou) {
  const form = new FormData()
  form.append('device_index', String(deviceIndex))
  form.append('model_id', String(modelId))
  form.append('conf', String(conf))
  form.append('iou', String(iou))
  return postForm('/camera/local/start', form)
}

export async function stopLocalStream(streamId) {
  const form = new FormData()
  form.append('stream_id', streamId)
  return postForm('/camera/local/stop', form)
}

export function getLocalResult(streamId) {
  return authFetch(`/camera/local/${streamId}/result`)
}

export async function localSnapshot(streamId, batchName = '') {
  const form = new FormData()
  form.append('stream_id', String(streamId))
  form.append('batch_name', batchName)
  return postForm('/camera/local/snapshot', form)
}

export async function startRtspStream(rtspUrl, modelId, conf, iou) {
  const form = new FormData()
  form.append('rtsp_url', rtspUrl)
  form.append('model_id', String(modelId))
  form.append('conf', String(conf))
  form.append('iou', String(iou))
  return postForm('/camera/rtsp/start', form)
}

export async function stopRtspStream(streamId) {
  const form = new FormData()
  form.append('stream_id', streamId)
  return postForm('/camera/rtsp/stop', form)
}

export function getRtspResult(streamId) {
  return authFetch(`/camera/rtsp/${streamId}/result`)
}
