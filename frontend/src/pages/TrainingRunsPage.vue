<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>训练任务</h1>
        <p>全局查看所有项目的训练任务。单个项目的训练建议从项目工作台发起。</p>
      </div>
      <div class="header-actions">
        <RouterLink v-if="activeProject" class="primary-action" :to="`/projects/${activeProject.id}?tab=training`"><AppIcon name="train" /> 发起训练</RouterLink>
        <RouterLink v-else class="primary-action" to="/projects"><AppIcon name="projects" /> 选择项目</RouterLink>
      </div>
    </div>

    <div v-if="activeProject" class="context-hint">
      当前项目：<strong>{{ activeProject.name }}</strong>
      <RouterLink :to="`/projects/${activeProject.id}?tab=training`">去项目详情 →</RouterLink>
    </div>

    <div v-if="loading" class="card compact-panel">
      <div class="table-card section-pad">
        <div class="skeleton skeleton-row" style="width:100%"></div>
        <div class="skeleton skeleton-row" style="width:95%"></div>
        <div class="skeleton skeleton-row" style="width:90%"></div>
        <div class="skeleton skeleton-row" style="width:85%"></div>
        <div class="skeleton skeleton-row" style="width:80%"></div>
      </div>
    </div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else>
      <div class="asset-summary dense-summary">
        <div><span>训练任务</span><strong>{{ filteredRuns.length }}</strong></div>
        <div><span>运行中</span><strong>{{ countStatus('running') }}</strong></div>
        <div><span>已完成</span><strong>{{ countStatus('completed') }}</strong></div>
        <div><span>排队/失败</span><strong>{{ countStatus('created') + countStatus('failed') }}</strong></div>
      </div>

      <section class="card compact-panel">
        <div class="asset-toolbar">
          <label class="inline-filter">
            <span>项目筛选</span>
            <select v-model="projectFilter">
              <option value="">全部项目</option>
              <option v-for="project in projects" :key="project.id" :value="String(project.id)">
                {{ project.name }}
              </option>
            </select>
          </label>
          <span class="muted-text">{{ filteredRuns.length }} 条记录</span>
        </div>

        <div class="table-card section-pad">
          <table class="training-table">
            <thead>
              <tr>
                <th>任务名称</th>
                <th>关联数据集</th>
                <th>模型架构</th>
                <th>状态</th>
                <th>进度 (Epoch)</th>
                <th>最佳 mAP</th>
                <th>剩余时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in filteredRuns" :key="run.id">
                <td>
                  <RouterLink class="task-name-link" :to="`/training/${run.id}`">{{ run.run_id }}</RouterLink>
                </td>
                <td class="muted-text">{{ datasetName(run.dataset_version_id) }}</td>
                <td>
                  <span class="model-arch-tag">{{ modelArch(run.base_model) }}</span>
                </td>
                <td>
                  <span :class="['chip', statusChip(run.status)]">{{ statusLabel(run.status) }}</span>
                </td>
                <td>
                  <div class="epoch-progress-cell">
                    <div class="progress-bar-wrap">
                      <div class="progress-bar" :class="{ 'progress-bar--running': run.status === 'running' }" :style="{ width: epochProgressPct(run) + '%' }"></div>
                    </div>
                    <span class="progress-text">{{ epochProgressText(run) }}</span>
                  </div>
                </td>
                <td>
                  <span v-if="bestMapDisplay(run)" class="map-value">{{ bestMapDisplay(run) }}</span>
                  <span v-else class="muted-text">-</span>
                </td>
                <td class="muted-text">{{ remainingTime(run) }}</td>
                <td>
                  <div class="action-btn-group">
                    <RouterLink class="secondary-action small-action" :to="`/training/${run.id}`">详情</RouterLink>
                    <button class="secondary-action small-action danger-action" @click="confirmDeleteRun(run)">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredRuns.length">
                <td colspan="8" class="empty-cell">
                  <div class="empty-state compact-empty">
                    <strong>还没有训练记录</strong>
                    <span>去项目工作台选择数据集后发起训练。</span>
                    <RouterLink class="primary-action" to="/projects">前往项目工作台</RouterLink>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { listVersions } from '../api/datasets.js'
import { listModels } from '../api/models.js'
import { listProjects } from '../api/projects.js'
import { deleteRun, listRuns, getProgress } from '../api/training.js'
import { readActiveProjectContext } from '../state/projectContext.js'

const loading = ref(true)
const error = ref('')
const runs = ref([])
const versions = ref([])
const models = ref([])
const projects = ref([])
const activeProject = ref(readActiveProjectContext())
const projectFilter = ref(activeProject.value?.id ? String(activeProject.value.id) : '')
const progressMap = ref({}) // run_id -> {epochs_completed, epochs_total, latest_log_tail}
let pollTimer = null

const filteredRuns = computed(() => {
  if (!projectFilter.value) return runs.value
  return runs.value.filter(run => String(run.project_id || '') === projectFilter.value)
})

onMounted(load)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [runResp, verResp, projectRows, modelResp] = await Promise.all([listRuns(), listVersions(), listProjects(), listModels()])
    const runRows = runResp.items
    const versionRows = verResp.items
    const modelRows = modelResp.items
    runs.value = runRows
    versions.value = versionRows
    projects.value = projectRows
    models.value = modelRows
    startPolling()
  } catch (err) {
    error.value = err?.message || '训练记录加载失败'
  } finally {
    loading.value = false
  }
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(pollRunning, 3000)
  pollRunning()
}

async function pollRunning() {
  const running = runs.value.filter(r => r.status === 'running' || r.status === 'created')
  for (const run of running) {
    try {
      const p = await getProgress(run.id)
      progressMap.value[run.id] = p
      if (p.status === 'completed' || p.status === 'failed') {
        run.status = p.status
        delete progressMap.value[run.id]
      }
    } catch {}
  }
  if (running.length === 0 && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function getProgressInfo(run) {
  const p = progressMap.value[run.id]
  if (!p) return null
  return p
}

async function confirmDeleteRun(run) {
  if (!confirm(`确认删除训练「${run.run_id}」？关联的模型和评估记录也会被一并删除。`)) return
  try {
    await deleteRun(run.id)
    await load()
  } catch (err) {
    error.value = '删除失败：' + (err?.message || err)
  }
}

function countStatus(status) {
  return filteredRuns.value.filter(run => run.status === status).length
}

function projectName(projectId) {
  return projects.value.find(project => Number(project.id) === Number(projectId))?.name || '未归属'
}

function datasetName(versionId) {
  const version = versions.value.find(item => Number(item.id) === Number(versionId))
  return version ? `${version.dataset_name} / ${version.version}` : versionId
}

function modelForRun(run) {
  const m = models.value.find(mv => Number(mv.training_run_id) === Number(run.id))
  return m || null
}

function statusLabel(status) {
  return {
    completed: '已完成',
    running: '运行中',
    failed: '失败',
    created: '排队中',
    pending: '排队中',
  }[status] || status
}

function statusChip(status) {
  return {
    completed: 'success',
    running: 'info',
    failed: 'danger',
    created: 'warning',
    pending: 'warning',
  }[status] || ''
}

/** Extract model architecture name from base_model path */
function modelArch(path) {
  if (!path) return '-'
  const n = String(path).replace(/\\/g, '/').split('/').pop().toLowerCase()
  // Map known model files to display names
  const archMap = {
    'yolo11n.pt': 'YOLO11n', 'yolo11s.pt': 'YOLO11s', 'yolo11m.pt': 'YOLO11m', 'yolo11l.pt': 'YOLO11l', 'yolo11x.pt': 'YOLO11x',
    'yolov8n.pt': 'YOLOv8n', 'yolov8s.pt': 'YOLOv8s', 'yolov8m.pt': 'YOLOv8m', 'yolov8l.pt': 'YOLOv8l', 'yolov8x.pt': 'YOLOv8x',
    'yolov5n.pt': 'YOLOv5n', 'yolov5s.pt': 'YOLOv5s', 'yolov5m.pt': 'YOLOv5m', 'yolov5l.pt': 'YOLOv5l', 'yolov5x.pt': 'YOLOv5x',
  }
  if (archMap[n]) return archMap[n]
  // Fallback: capitalize first letter of stem (e.g. "best.pt" → "best")
  const stem = n.replace(/\.pt$/i, '')
  return stem.length > 1 ? stem.charAt(0).toUpperCase() + stem.slice(1) : stem || n
}

/** Epoch progress percentage */
function epochProgressPct(run) {
  const p = getProgressInfo(run)
  if (p && p.epochs_total > 0) return Math.round((p.epochs_completed / p.epochs_total) * 100)
  if (run.status === 'completed') return 100
  return 0
}

/** Epoch progress text: "136/200" or "200 epochs" for completed */
function epochProgressText(run) {
  const p = getProgressInfo(run)
  if (p && p.epochs_total > 0) return `${p.epochs_completed}/${p.epochs_total}`
  if (run.status === 'completed') return `${run.epochs} epochs`
  return `${run.epochs} epochs`
}

/** Best mAP from associated model */
function bestMapDisplay(run) {
  const m = modelForRun(run)
  if (m && m.map50 != null) return Number(m.map50).toFixed(3)
  return ''
}

/** Remaining time estimate for running tasks */
function remainingTime(run) {
  if (run.status === 'completed') return '-'
  if (run.status === 'failed') return '-'
  if (run.status === 'created' || !run.started_at) return '-'
  const p = getProgressInfo(run)
  if (!p || !p.epochs_completed || p.epochs_completed <= 0) return '计算中...'
  const start = new Date(run.started_at).getTime()
  const elapsed = Date.now() - start
  const rate = elapsed / p.epochs_completed // ms per epoch
  const remaining = rate * (p.epochs_total - p.epochs_completed)
  if (remaining < 60000) return '< 1m'
  if (remaining < 3600000) return `${Math.round(remaining / 60000)}m`
  const h = Math.floor(remaining / 3600000)
  const m = Math.round((remaining % 3600000) / 60000)
  return `${h}h ${m}m`
}

function cleanModel(path) {
  if (!path) return '-'
  const n = String(path).replace(/\\/g, '/')
  const last = n.split('/').pop()
  if (last.length > 4) return last
  return n
}
</script>
