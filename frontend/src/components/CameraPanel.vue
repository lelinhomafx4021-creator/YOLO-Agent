<template>
  <div class="card">
    <div class="card-title"><strong>摄像头检测</strong></div>
    <div class="section-pad">
      <div class="segmented" style="margin-bottom:12px">
        <button :class="{ active: cameraType === 'webcam' }" @click="cameraType = 'webcam'">本机摄像头</button>
        <button :class="{ active: cameraType === 'rtsp' }" @click="cameraType = 'rtsp'">RTSP / IP 摄像头</button>
      </div>

      <!-- RTSP -->
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
        <div v-if="rtspStreamId" class="camera-view" style="margin-top:12px">
          <img v-if="rtspFrameSrc" :src="rtspFrameSrc" class="camera-video" style="object-fit:contain" />
          <div v-else class="camera-placeholder"><strong>{{ rtspConnected ? '等待画面...' : '连接中...' }}</strong></div>
        </div>
        <div v-if="rtspStreamId" class="camera-controls" style="margin-top:8px">
          <div class="camera-stats">
            <span>状态: {{ rtspConnected ? '已连接' : '连接中' }}</span>
            <span>目标: {{ boxCount }}</span>
            <span>延迟: {{ latency }}ms</span>
          </div>
        </div>
      </div>

      <!-- 画质 -->
      <div class="camera-perf-settings">
        <div class="slider-field">
          <span>上传画质</span>
          <div class="slider-row">
            <input type="range" min="0.3" max="1" step="0.1" v-model.number="jpegQuality" />
            <em>{{ (jpegQuality * 100).toFixed(0) }}%</em>
          </div>
        </div>
      </div>

      <!-- 本机摄像头 -->
      <div v-if="cameraType === 'webcam'" class="camera-container">
        <div class="camera-dual">
          <!-- 左：原始摄像头 -->
          <div class="camera-view">
            <div class="camera-label">摄像头</div>
            <video ref="videoEl" autoplay playsinline muted class="camera-video"></video>
            <div v-if="!active" class="camera-placeholder">
              <strong>点击「开启摄像头」开始</strong>
            </div>
          </div>
          <!-- 右：检测结果 -->
          <div class="camera-view">
            <div class="camera-label">检测结果</div>
            <canvas ref="canvasEl" class="camera-video"></canvas>
            <div v-if="!active" class="camera-placeholder">
              <span>等待摄像头...</span>
            </div>
          </div>
        </div>
        <div class="camera-controls">
          <div class="camera-stats">
            <span>FPS: {{ fps }}</span>
            <span>目标: {{ boxCount }}</span>
            <span>延迟: {{ latency }}ms</span>
          </div>
          <div class="camera-actions">
            <button v-if="!active" class="primary-action" @click="startCamera">开启摄像头</button>
            <button v-else class="secondary-action danger-action" @click="stopCamera">停止</button>
            <button v-if="active && !detecting" class="primary-action" @click="startDetection">开始检测</button>
            <button v-if="detecting" class="secondary-action" @click="stopDetection">暂停检测</button>
            <button v-if="active" class="secondary-action" @click="takeSnapshot">截图保存</button>
          </div>
        </div>
      </div>

      <!-- 检测结果 -->
      <div v-if="lastBoxes.length > 0" class="camera-detections">
        <div class="card-title"><strong>当前检测</strong><span>{{ lastBoxes.length }} 个目标</span></div>
        <div class="detection-chips">
          <span v-for="(box, i) in lastBoxes" :key="i" class="class-chip">
            {{ resolveName(box.class_id) }} {{ (box.confidence * 100).toFixed(0) }}%
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onUnmounted, ref } from 'vue'
import { cameraFrame, cameraSnapshot, startRtspStream, stopRtspStream, getRtspResult } from '../api/camera.js'

const props = defineProps({
  modelId: { type: [Number, String], default: '' },
  confidence: { type: Number, default: 0.25 },
  iou: { type: Number, default: 0.45 },
})

const emit = defineEmits(['snapshot', 'error'])

// ---- State ----
const cameraType = ref('webcam')
const active = ref(false)
const detecting = ref(false)
const fps = ref(0)
const boxCount = ref(0)
const latency = ref(0)
const lastBoxes = ref([])
const classNames = ref([])
const jpegQuality = ref(0.8)

const videoEl = ref(null)
const canvasEl = ref(null)
let stream = null
let timer = null
let lastFrameTime = 0
let busy = false
let adaptiveInterval = 300

// RTSP
const rtspUrl = ref('')
const rtspStreamId = ref('')
const rtspConnected = ref(false)
const rtspError = ref('')
const rtspResult = ref(null)
let rtspPollTimer = null

const rtspFrameSrc = computed(() => {
  if (!rtspResult.value?.frame_base64) return ''
  return 'data:image/jpeg;base64,' + rtspResult.value.frame_base64
})

// ---- Webcam ----
async function startCamera() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720 }, audio: false })
    if (videoEl.value) videoEl.value.srcObject = stream
    active.value = true
  } catch (err) {
    emit('error', '无法访问摄像头：' + (err.message || '请检查浏览器权限设置'))
  }
}

function stopCamera() {
  stopDetection()
  if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null }
  if (videoEl.value) videoEl.value.srcObject = null
  active.value = false
  fps.value = 0
}

function startDetection() {
  if (!active.value || !props.modelId) return
  detecting.value = true
  adaptiveInterval = 300
  detectLoop()
}

function stopDetection() {
  detecting.value = false
  if (timer) { clearTimeout(timer); timer = null }
}

async function detectLoop() {
  if (!detecting.value) return
  await detectFrame()
  const delay = Math.max(50, Math.min(2000, adaptiveInterval))
  timer = setTimeout(detectLoop, delay)
}

async function detectFrame() {
  if (busy || !videoEl.value || !canvasEl.value || !props.modelId) return
  const video = videoEl.value
  const canvas = canvasEl.value
  if (video.readyState < 2) return

  busy = true
  const t0 = Date.now()
  try {
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    ctx.drawImage(video, 0, 0)

    const blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', jpegQuality.value))
    if (!blob) return

    const result = await cameraFrame(Number(props.modelId), blob, props.confidence, props.iou)
    const elapsed = Date.now() - t0
    latency.value = elapsed

    const now = Date.now()
    if (lastFrameTime > 0) {
      const interval = now - lastFrameTime
      if (interval > 0) fps.value = Math.round(1000 / interval)
    }
    lastFrameTime = now
    adaptiveInterval = Math.max(50, elapsed + 20)

    lastBoxes.value = result.boxes || []
    boxCount.value = result.box_count || 0
    if (result.class_names?.length) classNames.value = result.class_names

    drawDetections(ctx, canvas.width, canvas.height, result.boxes || [])
  } catch (err) {
    console.warn('Frame error:', err.message)
    adaptiveInterval = 2000
  } finally {
    busy = false
  }
}

function drawDetections(ctx, w, h, boxes) {
  const video = videoEl.value
  if (video) ctx.drawImage(video, 0, 0)
  const colors = ['#D4783C', '#3B82F6', '#10B981', '#8B5CF6', '#EF4444', '#F59E0B']
  for (const box of boxes) {
    const color = colors[box.class_id % colors.length]
    const x = (box.x_center - box.width / 2) * w
    const y = (box.y_center - box.height / 2) * h
    const bw = box.width * w
    const bh = box.height * h
    ctx.strokeStyle = color
    ctx.lineWidth = 2
    ctx.strokeRect(x, y, bw, bh)
    const label = `${resolveName(box.class_id)} ${(box.confidence * 100).toFixed(0)}%`
    ctx.font = '12px sans-serif'
    const tw = ctx.measureText(label).width
    ctx.fillStyle = color
    ctx.fillRect(x, y - 18, tw + 8, 18)
    ctx.fillStyle = '#fff'
    ctx.fillText(label, x + 4, y - 4)
  }
}

function resolveName(id) {
  if (classNames.value.length && id >= 0 && id < classNames.value.length) return classNames.value[id]
  return 'class_' + id
}

async function takeSnapshot() {
  if (!videoEl.value || !props.modelId) return
  const video = videoEl.value
  const c = document.createElement('canvas')
  c.width = video.videoWidth
  c.height = video.videoHeight
  c.getContext('2d').drawImage(video, 0, 0)
  const blob = await new Promise(r => c.toBlob(r, 'image/jpeg', 0.9))
  if (!blob) return
  try {
    const result = await cameraSnapshot(Number(props.modelId), blob, props.confidence, props.iou, '手动截图')
    emit('snapshot', result)
  } catch (err) {
    emit('error', '截图保存失败：' + (err.message || ''))
  }
}

// ---- RTSP ----
async function startRtsp() {
  if (!rtspUrl.value || !props.modelId) return
  rtspError.value = ''
  try {
    const res = await startRtspStream(rtspUrl.value, Number(props.modelId), props.confidence, props.iou)
    rtspStreamId.value = res.stream_id
    rtspPollTimer = setInterval(pollRtsp, 1000)
    pollRtsp()
  } catch (err) { rtspError.value = err.message || '连接失败' }
}

async function stopRtsp() {
  if (rtspStreamId.value) { try { await stopRtspStream(rtspStreamId.value) } catch {} }
  if (rtspPollTimer) { clearInterval(rtspPollTimer); rtspPollTimer = null }
  rtspStreamId.value = ''
  rtspConnected.value = false
  rtspResult.value = null
  lastBoxes.value = []
  boxCount.value = 0
}

async function pollRtsp() {
  if (!rtspStreamId.value) return
  try {
    const res = await getRtspResult(rtspStreamId.value)
    rtspConnected.value = res.connected || false
    if (res.error) { rtspError.value = res.error; stopRtsp(); return }
    if (res.result) {
      rtspResult.value = res.result
      lastBoxes.value = res.result.boxes || []
      boxCount.value = res.result.box_count || 0
      latency.value = res.result.elapsed_ms || 0
      if (res.result.class_names?.length) classNames.value = res.result.class_names
    }
    if (!res.running) stopRtsp()
  } catch {}
}

onUnmounted(() => { stopCamera(); stopRtsp() })
</script>
