<template>
  <div class="log-terminal-wrap">
    <div class="log-toolbar">
      <span class="log-status-pill" :class="statusClass">
        <span class="status-dot"></span>
        {{ statusText }}
      </span>
      <div class="log-progress-bar" v-if="status === 'running' && epochProgress != null">
        <div class="log-progress-fill" :style="{ width: epochProgress + '%' }"></div>
        <span class="log-progress-text">{{ epochText }}</span>
      </div>
      <span class="log-count muted-text">{{ lines.length }} 行</span>
      <button v-if="lines.length > 0" class="log-download-btn" @click="downloadLog" title="下载日志">↓ 下载</button>
    </div>
    <div class="log-terminal" ref="terminal">
      <div v-for="(line, i) in lines" :key="i" :class="['log-line', lineClass(line)]">
        <span class="log-num">{{ i + 1 }}</span>
        <span class="log-text">{{ line }}</span>
      </div>
      <div v-if="lines.length === 0" class="log-line dim">等待日志输出...</div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps({
  logApi: { type: Function, required: true },
  progressApi: { type: Function, default: null },
  pollInterval: { type: Number, default: 2000 },
  autoScroll: { type: Boolean, default: true },
  externalStatus: { type: String, default: '' },
  /** SSE 实时流地址（训练中时传入），有则优先 SSE */
  sseUrl: { type: String, default: '' },
})

const emit = defineEmits(['status-change'])

const lines = ref([])
const status = ref(props.externalStatus || '')
const terminal = ref(null)
const progress = ref(null)
let timer = null
let eventSource = null

const epochProgress = computed(() => {
  if (!progress.value) return null
  const done = progress.value.epochs_completed || 0
  const total = progress.value.epochs_total || 1
  return Math.min(100, Math.round((done / total) * 100))
})

const epochText = computed(() => {
  if (!progress.value) return ''
  const done = progress.value.epochs_completed || 0
  const total = progress.value.epochs_total || '?'
  return `${done}/${total} epochs`
})

const statusClass = computed(() => {
  const s = status.value
  if (s === 'completed') return 'status-success'
  if (s === 'failed') return 'status-error'
  if (s === 'running') return 'status-running'
  return 'status-idle'
})

const statusText = computed(() => {
  const map = {
    completed: '已完成',
    failed: '失败',
    running: '运行中',
    created: '已创建',
  }
  return map[status.value] || status.value || '就绪'
})

// 监听外部状态变化
watch(() => props.externalStatus, (val) => {
  if (val) status.value = val
})

// 监听轮询间隔变化
watch(() => props.pollInterval, () => {
  stopPolling()
  startPolling()
})

onMounted(() => {
  if (props.sseUrl) {
    startSSE()
  } else {
    fetchLog()
    startPolling()
  }
})

onUnmounted(() => {
  stopPolling()
  stopSSE()
})

// SSE 实时流
function startSSE() {
  if (!props.sseUrl) return
  stopSSE()
  const url = props.sseUrl.startsWith('/') ? props.sseUrl : `/api/training-runs/${props.sseUrl}/log/stream`
  const es = new EventSource(url)
  eventSource = es

  es.onmessage = (e) => {
    if (e.data) {
      lines.value.push(e.data)
      if (lines.value.length > 500) lines.value.shift() // 限制行数
      if (props.autoScroll) scrollBottom()
    }
  }

  es.addEventListener('progress', (e) => {
    try { progress.value = JSON.parse(e.data) } catch {}
  })
  es.addEventListener('done', (e) => {
    status.value = e.data
    progress.value = null
    emit('status-change', e.data)
    stopSSE()
  })

  es.onerror = () => {
    stopSSE()
    // SSE 断开后回退到轮询
    startPolling()
  }
}

function stopSSE() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function scrollBottom() {
  nextTick(() => {
    if (terminal.value) terminal.value.scrollTop = terminal.value.scrollHeight
  })
}

function startPolling() {
  if (timer) return
  timer = setInterval(async () => {
    await fetchLog()
    // 如果有进度 API，也获取状态
    if (props.progressApi) {
      try {
        const p = await props.progressApi()
        status.value = p.status || status.value
        progress.value = p
        emit('status-change', p.status)
        if (p.status === 'completed' || p.status === 'failed') {
          stopPolling()
        }
      } catch { /* ignore */ }
    }
  }, props.pollInterval)
}

function stopPolling() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
}

async function fetchLog() {
  try {
    const res = await props.logApi()
    if (res && res.log !== undefined) {
      const newLines = res.log.split('\n').filter(l => l.trim())
      // 只在内容变化时更新
      if (newLines.length !== lines.value.length || newLines[newLines.length - 1] !== lines.value[lines.value.length - 1]) {
        lines.value = newLines
        if (props.autoScroll) {
          nextTick(() => {
            if (terminal.value) {
              terminal.value.scrollTop = terminal.value.scrollHeight
            }
          })
        }
      }
    }
  } catch { /* ignore */ }
}

function lineClass(line) {
  if (line.includes('[ERROR]') || line.includes('error') || line.includes('Error') || line.includes('✗')) return 'log-error'
  if (line.includes('WARNING') || line.includes('warn')) return 'log-warn'
  if (line.includes('===') && (line.includes('完成') || line.includes('completed'))) return 'log-success'
  if (line.includes('===') && (line.includes('开始') || line.includes('start'))) return 'log-header'
  if (line.includes('Epoch') || line.includes('epoch')) return 'log-epoch'
  if (line.includes('✓')) return 'log-ok'
  if (line.includes('---')) return 'log-section'
  return ''
}

function downloadLog() {
  const blob = new Blob([lines.value.join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `log_${Date.now()}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

// 暴露给父组件
defineExpose({ fetchLog, stopPolling, startPolling, lines, status })
</script>
