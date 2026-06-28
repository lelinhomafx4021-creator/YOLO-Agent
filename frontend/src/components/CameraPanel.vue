<template>
  <div class="card">
    <div class="card-title"><strong>摄像头检测</strong></div>
    <div class="section-pad">
      <div class="segmented" style="margin-bottom:12px">
        <button :class="{ active: cameraType === 'webcam' }" @click="cameraType = 'webcam'">本机摄像头</button>
        <button :class="{ active: cameraType === 'rtsp' }" @click="cameraType = 'rtsp'">RTSP / IP 摄像头</button>
      </div>

      <div v-if="cameraType === 'webcam'" class="camera-local-config">
        <label class="form-field">
          <span>设备索引</span>
          <select v-model.number="deviceIndex">
            <option v-for="idx in deviceOptions" :key="idx" :value="idx">摄像头 {{ idx }}</option>
          </select>
        </label>
        <div class="camera-actions" style="margin-top:8px">
          <button v-if="!localStreamId" class="primary-action" :disabled="!modelId" @click="startCamera">开启后端直采</button>
          <button v-else class="secondary-action danger-action" @click="stopCamera">停止</button>
          <button v-if="localStreamId && localFrameSrc" class="secondary-action" @click="takeSnapshot">截图保存</button>
        </div>
        <p class="helper-text" style="margin-top:8px">当前模式由后端直接读取本机设备，不再逐帧走浏览器上传。</p>
        <p v-if="localError" class="error" style="margin-top:6px">{{ localError }}</p>

        <div class="camera-dual" style="margin-top:12px">
          <div class="camera-view">
            <div class="camera-label">摄像头</div>
            <img v-if="localFrameSrc" :src="localFrameSrc" class="camera-video" style="object-fit:contain" />
            <div v-else class="camera-placeholder">
              <strong>{{ localStreamId ? '等待画面...' : '点击“开启后端直采”开始' }}</strong>
            </div>
          </div>
          <div class="camera-view">
            <div class="camera-label">检测结果</div>
            <canvas ref="resultCanvas" class="camera-video"></canvas>
            <div v-if="!localFrameSrc" class="camera-placeholder">
              <span>{{ localStreamId ? '等待检测结果...' : '后端直采开启后显示检测结果' }}</span>
            </div>
          </div>
        </div>

        <div class="camera-controls">
          <div class="camera-stats">
            <span>状态: {{ localConnected ? '已连接' : (localStreamId ? '连接中' : '未开启') }}</span>
            <span>FPS: {{ fps }}</span>
            <span>目标: {{ boxCount }}</span>
            <span>延迟: {{ latency }}ms</span>
          </div>
        </div>
      </div>

      <div v-if="cameraType === 'rtsp'" class="camera-rtsp-config">
        <div class="form-field">
          <span>RTSP 地址</span>
          <input v-model="rtspUrl" placeholder="rtsp://192.168.1.100:554/stream1" />
        </div>
        <div class="camera-actions" style="margin-top:8px">
          <button v-if="!rtspStreamId" class="primary-action" :disabled="!rtspUrl || !modelId" @click="startRtsp">连接摄像头</button>
          <button v-else class="secondary-action danger-action" @click="stopRtsp">断开</button>
        </div>
        <p v-if="rtspError" class="error" style="margin-top:6px">{{ rtspError }}</p>
        <div v-if="rtspStreamId" class="camera-view camera-view--single" style="margin-top:12px">
          <img v-if="rtspFrameSrc" :src="rtspFrameSrc" class="camera-video" style="object-fit:contain" />
          <div v-else class="camera-placeholder"><strong>{{ rtspConnected ? '等待画面...' : '连接中...' }}</strong></div>
        </div>
        <div v-if="rtspStreamId" class="camera-controls" style="margin-top:8px">
          <div class="camera-stats">
            <span>状态: {{ rtspConnected ? '已连接' : '连接中' }}</span>
            <span>FPS: {{ fps }}</span>
            <span>目标: {{ boxCount }}</span>
            <span>延迟: {{ latency }}ms</span>
          </div>
        </div>
      </div>

      <div v-if="lastBoxes.length > 0" class="camera-detections">
        <div class="card-title"><strong>当前检测</strong><span>{{ lastBoxes.length }} 个目标</span></div>
        <div class="detection-chips">
          <span v-for="(box, i) in lastBoxes" :key="i" class="class-chip">
            {{ resolveName(box.class_id) }} {{ (box.confidence * 100).toFixed(0) }}%
          </span>
        </div>
      </div>

      <div v-if="lastSnapshot" class="camera-snapshot-card">
        <div class="card-title">
          <strong>截图已保存</strong>
          <span>{{ snapshotFolderLabel }}</span>
        </div>
        <div class="camera-snapshot-actions">
          <a v-if="lastSnapshot.snapshot_url" class="secondary-action small-action" :href="lastSnapshot.snapshot_url" target="_blank">原图</a>
          <a v-if="lastSnapshot.prediction_url" class="primary-action small-action" :href="lastSnapshot.prediction_url" target="_blank">检测图</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import {
  getLocalResult,
  getRtspResult,
  localSnapshot,
  startLocalStream,
  startRtspStream,
  stopLocalStream,
  stopRtspStream,
} from '../api/camera.js'

const props = defineProps({
  modelId: { type: [Number, String], default: '' },
  confidence: { type: Number, default: 0.25 },
  iou: { type: Number, default: 0.45 },
})

const emit = defineEmits(['snapshot', 'error'])

const cameraType = ref('webcam')
const deviceIndex = ref(0)
const deviceOptions = [0, 1, 2, 3]
const resultCanvas = ref(null)

const localStreamId = ref('')
const localConnected = ref(false)
const localError = ref('')
const localResult = ref(null)
let localPollTimer = null

const rtspUrl = ref('')
const rtspStreamId = ref('')
const rtspConnected = ref(false)
const rtspError = ref('')
const rtspResult = ref(null)
let rtspPollTimer = null

const fps = ref(0)
const boxCount = ref(0)
const latency = ref(0)
const lastBoxes = ref([])
const classNames = ref([])
const lastSnapshot = ref(null)

const localFrameSrc = computed(() => {
  const frame = localResult.value?.frame_base64
  return frame ? `data:image/jpeg;base64,${frame}` : ''
})

const rtspFrameSrc = computed(() => {
  const frame = rtspResult.value?.frame_base64
  return frame ? `data:image/jpeg;base64,${frame}` : ''
})

const snapshotFolderLabel = computed(() => {
  const sessionId = lastSnapshot.value?.session_id
  return sessionId ? `camera_snapshots/${sessionId}` : ''
})

watch(localFrameSrc, () => drawDetectionCanvas())
watch(lastBoxes, () => drawDetectionCanvas(), { deep: true })

function resetMetrics() {
  fps.value = 0
  boxCount.value = 0
  latency.value = 0
  lastBoxes.value = []
}

function clearCanvas() {
  if (!resultCanvas.value) return
  const ctx = resultCanvas.value.getContext('2d')
  ctx.clearRect(0, 0, resultCanvas.value.width || 0, resultCanvas.value.height || 0)
}

function drawDetectionCanvas() {
  const src = localFrameSrc.value
  const canvas = resultCanvas.value
  if (!src || !canvas) {
    clearCanvas()
    return
  }
  const img = new Image()
  img.onload = () => {
    canvas.width = img.naturalWidth || img.width
    canvas.height = img.naturalHeight || img.height
    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
    drawBoxes(ctx, canvas.width, canvas.height, lastBoxes.value)
  }
  img.src = src
}

function drawBoxes(ctx, width, height, boxes) {
  const colors = ['#E47630', '#3B82F6', '#10B981', '#8B5CF6', '#EF4444', '#F59E0B']
  for (const box of boxes || []) {
    const classId = Number(box.class_id || 0)
    const color = colors[classId % colors.length]
    const x = (box.x_center - box.width / 2) * width
    const y = (box.y_center - box.height / 2) * height
    const bw = box.width * width
    const bh = box.height * height
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.strokeRect(x, y, bw, bh)
    const label = `${resolveName(classId)} ${(box.confidence * 100).toFixed(0)}%`
    ctx.font = '12px sans-serif'
    const tw = ctx.measureText(label).width
    ctx.fillStyle = color
    ctx.fillRect(x, Math.max(0, y - 18), tw + 8, 18)
    ctx.fillStyle = '#fff'
    ctx.fillText(label, x + 4, Math.max(12, y - 4))
  }
}

function resolveName(id) {
  return classNames.value[id] || `class_${id}`
}

async function startCamera() {
  if (!props.modelId) return
  localError.value = ''
  try {
    const res = await startLocalStream(deviceIndex.value, Number(props.modelId), props.confidence, props.iou)
    localStreamId.value = res.stream_id
    if (localPollTimer) clearInterval(localPollTimer)
    localPollTimer = setInterval(pollLocal, 120)
    await pollLocal()
  } catch (err) {
    localError.value = err?.message || '开启本机摄像头失败'
    emit('error', localError.value)
  }
}

async function stopCamera() {
  if (localStreamId.value) {
    try { await stopLocalStream(localStreamId.value) } catch {}
  }
  if (localPollTimer) {
    clearInterval(localPollTimer)
    localPollTimer = null
  }
  localStreamId.value = ''
  localConnected.value = false
  localResult.value = null
  resetMetrics()
  clearCanvas()
}

async function pollLocal() {
  if (!localStreamId.value) return
  try {
    const res = await getLocalResult(localStreamId.value)
    localConnected.value = res.connected || false
    if (res.error) {
      localError.value = res.error
      emit('error', localError.value)
      await stopCamera()
      return
    }
    if (res.result) {
      localResult.value = res.result
      lastBoxes.value = res.result.boxes || []
      boxCount.value = res.result.box_count || 0
      latency.value = Math.round(res.result.elapsed_ms || 0)
      fps.value = Number(res.result.fps || 0).toFixed ? Number(res.result.fps || 0) : 0
      if (res.result.class_names?.length) classNames.value = res.result.class_names
    }
    if (!res.running) await stopCamera()
  } catch {}
}

async function takeSnapshot() {
  if (!localStreamId.value) return
  try {
    const result = await localSnapshot(localStreamId.value, '手动截图')
    lastSnapshot.value = result
    emit('snapshot', result)
  } catch (err) {
    const message = err?.message || '截图保存失败'
    emit('error', message)
  }
}

async function startRtsp() {
  if (!rtspUrl.value || !props.modelId) return
  rtspError.value = ''
  try {
    const res = await startRtspStream(rtspUrl.value, Number(props.modelId), props.confidence, props.iou)
    rtspStreamId.value = res.stream_id
    if (rtspPollTimer) clearInterval(rtspPollTimer)
    rtspPollTimer = setInterval(pollRtsp, 200)
    await pollRtsp()
  } catch (err) {
    rtspError.value = err?.message || '连接失败'
    emit('error', rtspError.value)
  }
}

async function stopRtsp() {
  if (rtspStreamId.value) {
    try { await stopRtspStream(rtspStreamId.value) } catch {}
  }
  if (rtspPollTimer) {
    clearInterval(rtspPollTimer)
    rtspPollTimer = null
  }
  rtspStreamId.value = ''
  rtspConnected.value = false
  rtspResult.value = null
  resetMetrics()
}

async function pollRtsp() {
  if (!rtspStreamId.value) return
  try {
    const res = await getRtspResult(rtspStreamId.value)
    rtspConnected.value = res.connected || false
    if (res.error) {
      rtspError.value = res.error
      emit('error', rtspError.value)
      await stopRtsp()
      return
    }
    if (res.result) {
      rtspResult.value = res.result
      lastBoxes.value = res.result.boxes || []
      boxCount.value = res.result.box_count || 0
      latency.value = Math.round(res.result.elapsed_ms || 0)
      fps.value = Number(res.result.fps || 0)
      if (res.result.class_names?.length) classNames.value = res.result.class_names
    }
    if (!res.running) await stopRtsp()
  } catch {}
}

watch(cameraType, async (type) => {
  if (type === 'webcam') await stopRtsp()
  if (type === 'rtsp') await stopCamera()
})

watch(() => props.modelId, async () => {
  if (localStreamId.value) await stopCamera()
  if (rtspStreamId.value) await stopRtsp()
})

onUnmounted(async () => {
  await stopCamera()
  await stopRtsp()
})
</script>
