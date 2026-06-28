<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>训练任务</h1>
        <p>全局查看所有项目的训练任务，也可以直接从这里发起新的训练。</p>
      </div>
      <div class="header-actions">
        <button class="primary-action" @click="showCreatePanel = !showCreatePanel"><AppIcon name="train" /> {{ showCreatePanel ? '收起训练入口' : '全局训练入口' }}</button>
        <RouterLink v-if="activeProject" class="secondary-action" :to="`/projects/${activeProject.id}?tab=training`"><AppIcon name="projects" /> 项目训练台</RouterLink>
        <RouterLink v-else class="secondary-action" to="/projects"><AppIcon name="projects" /> 项目列表</RouterLink>
      </div>
    </div>

    <div v-if="activeProject" class="context-hint">
      当前项目：<strong>{{ activeProject.name }}</strong>
      <RouterLink :to="`/projects/${activeProject.id}?tab=training`">打开项目训练台</RouterLink>
    </div>

    <section v-if="showCreatePanel" class="card compact-panel global-train-panel">
      <div class="card-title">
        <strong>全局训练入口</strong>
        <span>不需要先进入项目页。建议任务仍然归属到项目，后续模型关系会更清晰。</span>
      </div>
      <div class="global-train-grid">
        <label class="form-field">
          <span>归属项目</span>
          <select v-model.number="createForm.project_id">
            <option :value="0">不归属项目</option>
            <option v-for="project in projects" :key="project.id" :value="project.id">{{ project.name }}</option>
          </select>
        </label>
        <label class="form-field">
          <span>训练数据</span>
          <select v-model.number="createForm.dataset_version_id">
            <option :value="0" disabled>选择训练数据</option>
            <option v-for="version in labeledVersions" :key="version.id" :value="version.id">
              {{ version.dataset_name }} / {{ version.version }} ({{ version.image_count }}张)
            </option>
          </select>
        </label>
        <label class="form-field">
          <span>基础模型</span>
          <select v-model="createForm.base_model">
            <option value="yolo11n.pt">YOLO11n</option>
            <option value="yolo11s.pt">YOLO11s</option>
            <option value="yolo11m.pt">YOLO11m</option>
            <option value="yolo11l.pt">YOLO11l</option>
            <option value="yolo11x.pt">YOLO11x</option>
            <option value="yolov8n.pt">YOLOv8n</option>
            <option value="yolov8s.pt">YOLOv8s</option>
            <option value="yolov8m.pt">YOLOv8m</option>
            <option value="yolov8l.pt">YOLOv8l</option>
            <option value="yolov8x.pt">YOLOv8x</option>
          </select>
        </label>
        <label class="form-field">
          <span>epochs</span>
          <input v-model.number="createForm.epochs" type="number" min="1" />
        </label>
        <label class="form-field">
          <span>图像尺寸</span>
          <input v-model.number="createForm.imgsz" type="number" min="64" />
        </label>
        <label class="form-field">
          <span>Batch</span>
          <input v-model.number="createForm.batch" type="number" min="1" />
        </label>
      </div>
      <div class="global-train-actions">
        <button class="primary-action" @click="startGlobalTraining" :disabled="creatingRun">{{ creatingRun ? '创建中...' : '启动训练' }}</button>
        <span class="helper-text">创建后会直接进入全局训练队列。</span>
      </div>
      <p v-if="createError" class="error">{{ createError }}</p>
      <p v-if="createMsg" class="action-msg">{{ createMsg }}</p>
    </section>

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
          <span class="toolbar-count-pill">当前记录 <strong>{{ filteredRuns.length }}</strong></span>
        </div>

        <div class="table-card section-pad">
          <table class="training-table">
            <thead>
              <tr>
                <th>训练任务 / 注册模型</th>
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
                  <div class="table-cell-stack">
                    <RouterLink class="task-name-link" :to="`/training/${run.id}`">{{ displayTrainingName(run) }}</RouterLink>
                    <span class="table-cell-sub">{{ modelBindingLabel(run) }}</span>
                  </div>
                </td>
                <td>
                  <div class="table-cell-stack">
                    <span class="table-cell-main">{{ run.dataset_display_name || datasetName(run.dataset_version_id) }}</span>
                    <span class="table-cell-sub">{{ run.project_name || '未归属' }}</span>
                  </div>
                </td>
                <td>
                  <span class="model-arch-tag">{{ modelArch(run.base_model) }}</span>
                </td>
                <td>
                  <span :class="['chip', statusChip(run.status)]">{{ statusLabel(run.status) }}</span>
                </td>
                <td>
                  <div :class="['epoch-progress-cell', `epoch-progress-cell--${run.status || 'unknown'}`]">
                    <div class="epoch-progress-top">
                      <span class="epoch-progress-value">{{ epochProgressText(run) }}</span>
                      <span class="epoch-progress-rate">{{ epochProgressPct(run) }}%</span>
                    </div>
                    <div class="progress-bar-wrap">
                      <div class="progress-bar" :class="{ 'progress-bar--running': run.status === 'running', 'progress-bar--completed': run.status === 'completed' }" :style="{ width: epochProgressPct(run) + '%' }"></div>
                    </div>
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
                    <span>你可以直接使用上面的全局训练入口，或者进入项目工作台发起训练。</span>
                    <button class="primary-action" @click="showCreatePanel = true">打开训练入口</button>
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
import { computed, onActivated, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import { listVersions } from '../api/datasets.js'
import { listProjects } from '../api/projects.js'
import { createRun, deleteRun, getProgress, listRuns } from '../api/training.js'
import { readActiveProjectContext } from '../state/projectContext.js'
import { displayTrainingName, formatRemainingFromMs } from '../utils.js'

const loading = ref(true)
const creatingRun = ref(false)
const error = ref('')
const createError = ref('')
const createMsg = ref('')
const showCreatePanel = ref(false)
const runs = ref([])
const versions = ref([])
const projects = ref([])
const route = useRoute()
const activeProject = ref(readActiveProjectContext())
const projectFilter = ref(activeProject.value?.id ? String(activeProject.value.id) : '')
const progressMap = ref({})
let pollTimer = null

const createForm = reactive({
  project_id: activeProject.value?.id || 0,
  dataset_version_id: 0,
  base_model: 'yolo11n.pt',
  epochs: 50,
  imgsz: 640,
  batch: 8,
})

const filteredRuns = computed(() => {
  if (!projectFilter.value) return runs.value
  return runs.value.filter((run) => String(run.project_id || '') === projectFilter.value)
})

const labeledVersions = computed(() => versions.value.filter((version) => {
  const dtype = String(version.dtype || '').trim()
  if (dtype === 'val' || dtype === 'test' || dtype === 'annotation') return false
  return Number(version.label_file_count || 0) > 0
}))

watch(() => route.query.create, syncCreatePanel, { immediate: true })

onMounted(() => load())
onActivated(() => {
  syncCreatePanel()
  load({ silent: true })
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function load(options = {}) {
  const { silent = false } = options
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [runResp, verResp, projectRows] = await Promise.all([listRuns(), listVersions(), listProjects()])
    runs.value = runResp.items
    versions.value = verResp.items
    projects.value = projectRows
    if (!activeProject.value?.id && !createForm.project_id) {
      const lastProjectId = Number(localStorage.getItem('global_train_project_id') || 0)
      createForm.project_id = projects.value.find((item) => item.id === lastProjectId)?.id || 0
    }
    if (!createForm.dataset_version_id) {
      const lastDatasetId = Number(localStorage.getItem('global_train_dataset_id') || 0)
      createForm.dataset_version_id = labeledVersions.value.find((item) => item.id === lastDatasetId)?.id || labeledVersions.value[0]?.id || 0
    }
    startPolling()
  } catch (err) {
    error.value = err?.message || '训练记录加载失败'
  } finally {
    if (!silent) loading.value = false
  }
}

function syncCreatePanel() {
  showCreatePanel.value = String(route.query.create || '') === '1'
}

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(pollRunning, 3000)
  pollRunning()
}

async function pollRunning() {
  const running = runs.value.filter((run) => run.status === 'running' || run.status === 'created')
  for (const run of running) {
    try {
      const progress = await getProgress(run.id)
      progressMap.value[run.id] = progress
      if (progress.status === 'completed' || progress.status === 'failed') {
        run.status = progress.status
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
  return progressMap.value[run.id] || null
}

async function startGlobalTraining() {
  createMsg.value = ''
  createError.value = ''
  if (!createForm.dataset_version_id) {
    createError.value = '请先选择训练数据'
    return
  }
  creatingRun.value = true
  try {
    await createRun({
      ...createForm,
      project_id: createForm.project_id || null,
    })
    localStorage.setItem('global_train_dataset_id', String(createForm.dataset_version_id))
    if (createForm.project_id) localStorage.setItem('global_train_project_id', String(createForm.project_id))
    createMsg.value = '训练任务已创建，已进入全局训练队列。'
    showCreatePanel.value = false
    await load({ silent: true })
  } catch (err) {
    createError.value = err?.message || '启动训练失败'
  } finally {
    creatingRun.value = false
  }
}

async function confirmDeleteRun(run) {
  if (!confirm(`确认删除训练「${displayTrainingName(run)}」？关联的模型和评估记录也会一并删除。`)) return
  try {
    await deleteRun(run.id)
    await load({ silent: true })
  } catch (err) {
    error.value = '删除失败：' + (err?.message || err)
  }
}

function countStatus(status) {
  return filteredRuns.value.filter((run) => run.status === status).length
}

function datasetName(versionId) {
  const version = versions.value.find((item) => Number(item.id) === Number(versionId))
  return version ? `${version.dataset_name} / ${version.version}` : '-'
}

function modelBindingLabel(run) {
  return run.output_model_display_name ? `产出模型：${run.output_model_display_name}` : '未注册模型'
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

function modelArch(path) {
  if (!path) return '-'
  const name = String(path).replace(/\\/g, '/').split('/').pop().toLowerCase()
  const archMap = {
    'yolo11n.pt': 'YOLO11n', 'yolo11s.pt': 'YOLO11s', 'yolo11m.pt': 'YOLO11m', 'yolo11l.pt': 'YOLO11l', 'yolo11x.pt': 'YOLO11x',
    'yolov8n.pt': 'YOLOv8n', 'yolov8s.pt': 'YOLOv8s', 'yolov8m.pt': 'YOLOv8m', 'yolov8l.pt': 'YOLOv8l', 'yolov8x.pt': 'YOLOv8x',
    'yolov5n.pt': 'YOLOv5n', 'yolov5s.pt': 'YOLOv5s', 'yolov5m.pt': 'YOLOv5m', 'yolov5l.pt': 'YOLOv5l', 'yolov5x.pt': 'YOLOv5x',
  }
  if (archMap[name]) return archMap[name]
  const stem = name.replace(/\.pt$/i, '')
  return stem.length > 1 ? stem.charAt(0).toUpperCase() + stem.slice(1) : stem || name
}

function epochProgressPct(run) {
  const progress = getProgressInfo(run)
  if (progress && progress.epochs_total > 0) return Math.round((progress.epochs_completed / progress.epochs_total) * 100)
  if (run.status === 'completed') return 100
  return 0
}

function epochProgressText(run) {
  const progress = getProgressInfo(run)
  if (progress && progress.epochs_total > 0) return `${progress.epochs_completed}/${progress.epochs_total} epochs`
  if (run.status === 'completed') return `${run.epochs}/${run.epochs} epochs`
  return `${run.epochs} epochs`
}

function bestMapDisplay(run) {
  if (run.map50 != null) return Number(run.map50).toFixed(3)
  return ''
}

function remainingTime(run) {
  if (run.status === 'completed' || run.status === 'failed') return '-'
  if (run.status === 'created' || !run.started_at) return '-'
  const progress = getProgressInfo(run)
  if (!progress || !progress.epochs_completed || progress.epochs_completed <= 0) return '计算中...'
  const start = new Date(run.started_at).getTime()
  const elapsed = Date.now() - start
  const rate = elapsed / progress.epochs_completed
  return formatRemainingFromMs(rate * (progress.epochs_total - progress.epochs_completed))
}
</script>

<style scoped>
.global-train-panel {
  margin-bottom: 14px;
}

.global-train-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 12px;
}

.global-train-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
}

@media (max-width: 960px) {
  .global-train-grid {
    grid-template-columns: 1fr;
  }

  .global-train-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
