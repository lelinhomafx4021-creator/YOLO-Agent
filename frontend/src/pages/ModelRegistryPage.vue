<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>模型仓库</h1>
        <p>管理训练产出的模型，标记生产版本，导出部署。</p>
      </div>
      <div class="header-actions">
        <RouterLink class="secondary-action" to="/training?create=1"><AppIcon name="train" /> 全局训练</RouterLink>
        <button class="primary-action" @click="showImportDialog = true">导入模型</button>
        <RouterLink v-if="activeProject" class="secondary-action" :to="`/projects/${activeProject.id}`"><AppIcon name="arrow" /> 返回项目</RouterLink>
      </div>
    </div>

    <div v-if="loading" class="card compact-panel">
      <div class="table-card section-pad">
        <div class="skeleton skeleton-row" style="width:100%"></div>
        <div class="skeleton skeleton-row" style="width:95%"></div>
        <div class="skeleton skeleton-row" style="width:90%"></div>
        <div class="skeleton skeleton-row" style="width:85%"></div>
      </div>
    </div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else>
      <div class="asset-summary dense-summary">
        <div><span>模型总数</span><strong>{{ filteredModels.length }}</strong></div>
        <div><span>生产模型</span><strong>{{ filteredModels.filter(item => item.is_production).length }}</strong></div>
        <div><span>归档模型</span><strong>{{ filteredModels.filter(item => !item.is_production).length }}</strong></div>
        <div><span>最佳 mAP50-95</span><strong>{{ bestMap }}</strong></div>
      </div>

      <div class="card compact-panel" style="padding:0">
        <div class="card-title registry-card-title" style="padding:12px 18px 0">
          <div class="registry-title-copy">
            <strong>模型列表</strong>
            <span>点击行可展开查看详情、导出和产物。</span>
          </div>
          <div class="registry-toolbar">
            <label class="inline-filter">
              <span>项目</span>
              <select v-model.number="projectFilter" class="project-filter-select">
                <option :value="0">全部项目</option>
                <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
              </select>
            </label>
            <label class="inline-filter">
              <span>格式</span>
              <select v-model="formatFilter" class="project-filter-select">
                <option value="">全部格式</option>
                <option v-for="item in formatOptions" :key="item.value" :value="item.value">
                  {{ item.label }} · {{ item.count }}
                </option>
              </select>
            </label>
            <span class="toolbar-count-pill">当前模型 <strong>{{ visibleModels.length }}</strong></span>
          </div>
        </div>
        <div class="table-card section-pad">
          <table class="training-table training-table--compact registry-table">
            <thead>
              <tr>
                <th>模型</th>
                <th>数据 / 来源</th>
                <th>基础模型</th>
                <th>指标</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="model in visibleModels" :key="model.id">
                <tr
                  class="clickable-row"
                  :class="{ 'active-row': expandedModelId === model.id }"
                  @click="toggleModel(model)"
                >
                  <td>
                    <template v-if="renamingId === model.id">
                      <input v-model="renamingName" class="inline-rename-input" @keyup.enter="saveRename(model)" @keyup.escape="cancelRename" @blur="saveRename(model)" />
                    </template>
                    <template v-else>
                      <div class="registry-name-cell">
                        <div class="table-cell-stack">
                          <span class="model-name-cell model-name-cell--compact" :title="displayModelName(model)">{{ compactModelName(model) }}</span>
                          <span class="table-cell-sub">{{ compactModelMeta(model) }}</span>
                        </div>
                        <div class="registry-row-tools">
                          <span class="format-badge">{{ modelFormatLabel(model) }}</span>
                          <button class="icon-btn-sm" title="重命名" @click.stop="startRename(model)">✎</button>
                        </div>
                      </div>
                    </template>
                  </td>
                  <td>
                    <div class="table-cell-stack">
                      <span class="table-cell-main">{{ displayDatasetName(model) }}</span>
                      <span class="table-cell-sub">{{ compactSourceName(model) }}</span>
                    </div>
                  </td>
                  <td class="mono muted-text">{{ shortPath(model.base_model) }}</td>
                  <td>
                    <div class="metric-stack">
                      <strong>{{ fmtMetric(model.map50_95) }}</strong>
                      <span class="table-cell-sub">mAP50 {{ fmtMetric(model.map50) }}</span>
                    </div>
                  </td>
                  <td>
                    <div class="table-cell-stack status-cell-stack">
                      <span :class="['chip', model.is_production ? 'success' : '']">{{ modelStatus(model) }}</span>
                      <span class="table-cell-sub">{{ model.project_name || '未归属项目' }}</span>
                    </div>
                  </td>
                </tr>
                <tr v-if="expandedModelId === model.id" class="model-detail-row">
                  <td colspan="5">
                    <div class="model-detail-panel">
                      <div class="detail-grid">
                        <div class="info-item"><span>技术 ID</span><strong>{{ model.run_id }}</strong></div>
                        <div class="info-item"><span>数据批次</span><strong>{{ displayDatasetName(model) }}</strong></div>
                        <div class="info-item"><span>基础模型</span><strong>{{ shortPath(model.base_model) }}</strong></div>
                        <div class="info-item"><span>最佳 Epoch</span><strong>{{ model.best_epoch ?? '-' }}</strong></div>
                        <div class="info-item"><span>所属项目</span><strong>{{ model.project_name || '未归属项目' }}</strong></div>
                        <div class="info-item"><span>来源类型</span><strong>{{ model.source_type_label || '模型记录' }}</strong></div>
                        <div class="info-item"><span>来源训练</span><strong>{{ model.source_training_display_name || '无关联训练' }}</strong></div>
                        <div class="info-item"><span>Precision</span><strong>{{ fmtMetric(model.precision) }}</strong></div>
                        <div class="info-item"><span>Recall</span><strong>{{ fmtMetric(model.recall) }}</strong></div>
                        <div class="info-item"><span>mAP50</span><strong>{{ fmtMetric(model.map50) }}</strong></div>
                        <div class="info-item"><span>mAP50-95</span><strong>{{ fmtMetric(model.map50_95) }}</strong></div>
                      </div>

                      <div class="model-notes-section">
                        <label class="form-field">
                          <span>备注</span>
                          <textarea v-model="editingNotes" rows="2" placeholder="记录模型特点、适用场景..." @blur="saveNotes"></textarea>
                        </label>
                      </div>

                      <div class="model-detail-actions">
                        <div class="weight-downloads">
                          <a class="weight-card highlight" :href="`/api/models/${model.id}/download/best`" target="_blank">
                            <AppIcon name="model" /><div><strong>best.pt</strong><span class="muted-text">最佳权重</span></div>
                          </a>
                          <a class="weight-card" :href="`/api/models/${model.id}/download/last`" target="_blank">
                            <AppIcon name="model" /><div><strong>last.pt</strong><span class="muted-text">可续训</span></div>
                          </a>
                        </div>
                        <div class="button-row tight">
                          <button class="primary-action" @click.stop="selected = model; openExportDialog()">导出模型</button>
                          <button class="primary-action small-action" @click.stop="promote(model.id)">设为生产</button>
                          <RouterLink v-if="model.training_run_id" class="secondary-action small-action" :to="`/training/${model.training_run_id}`">训练详情</RouterLink>
                          <button class="secondary-action small-action danger-action" @click.stop="confirmDeleteModel(model)">删除</button>
                        </div>
                      </div>
                      <p v-if="actionMsg" class="action-msg" style="font-size:11px">{{ actionMsg }}</p>

                      <div class="card-title" style="padding:6px 0">
                        <strong>产物清单</strong>
                        <span class="muted-text">{{ artifacts.length }} 项</span>
                      </div>
                      <div class="table-card compact-table">
                        <table>
                          <thead><tr><th>文件</th><th>路径</th></tr></thead>
                          <tbody>
                            <tr v-for="art in artifacts" :key="art.relative_path">
                              <td><a :href="art.url" target="_blank" class="mono">{{ art.name }}</a></td>
                              <td class="mono muted-text">{{ art.relative_path }}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
              <tr v-if="visibleModels.length === 0">
                <td colspan="5" class="empty-cell">还没有模型记录。训练完成后模型会自动注册到此处。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- 导出模型对话框 -->
    <div v-if="showExportDialog" class="dialog-overlay" @click.self="closeExportDialog">
      <div class="dialog import-dialog">
        <h3>导出模型</h3>
        <p class="helper-text">将「{{ selected ? displayModelName(selected) : '' }}」导出为部署格式</p>
        <label class="form-field">
          <span>导出格式</span>
          <select v-model="exportForm.format">
            <option v-for="fmt in exportFormats" :key="fmt.format" :value="fmt.format">{{ fmt.label }} — {{ fmt.description }}</option>
          </select>
        </label>
        <label class="form-field">
          <span>图像尺寸</span>
          <select v-model.number="exportForm.imgsz">
            <option :value="320">320</option>
            <option :value="640">640</option>
            <option :value="1280">1280</option>
          </select>
        </label>
        <label class="form-field checkbox-field">
          <input type="checkbox" v-model="exportForm.half" />
          <span>半精度 (FP16) — 体积减半，TensorRT/ONNX 支持</span>
        </label>
        <div v-if="exporting || exportLogLines.length" class="log-terminal-wrap" style="margin:12px 0">
          <div class="log-toolbar">
            <span :class="['log-status', exporting ? 'status-running' : exportError ? 'status-failed' : 'status-completed']">
              {{ exportStatus || (exporting ? '导出中...' : '导出完成') }}
            </span>
          </div>
          <div class="log-terminal" style="max-height:120px">
            <div v-for="(line, i) in exportLogLines" :key="i" class="log-line">{{ line }}</div>
          </div>
        </div>
        <div v-if="exportResult" class="export-result">
          <p class="action-msg">
            导出完成：{{ exportResult.files.length }} 个文件
            <span v-if="exportResult.exported_model">，已注册为 {{ displayModelName(exportResult.exported_model) }}</span>
          </p>
          <div v-for="f in exportResult.files" :key="f.name" class="artifact-row">
            <a v-if="f.url" :href="f.url" target="_blank"><strong>{{ f.name }}</strong></a>
            <strong v-else>{{ f.name }}</strong>
            <span>{{ formatSize(f.size) }}</span>
          </div>
        </div>
        <p v-if="exportError" class="error">{{ exportError }}</p>
        <div class="dialog-actions">
          <button class="secondary-action" @click="closeExportDialog">关闭</button>
          <button class="primary-action" :disabled="exporting" @click="doExport">{{ exporting ? '导出中...' : '开始导出' }}</button>
        </div>
      </div>
    </div>

    <!-- 导入模型对话框 -->
    <div v-if="showImportDialog" class="dialog-overlay" @click.self="closeImportDialog">
      <div class="dialog import-dialog">
        <h3>导入模型</h3>
        <p class="helper-text">支持 .pt / .onnx / .torchscript / .engine 格式</p>
        <div
          class="upload-box upload-clickable"
          :class="{ 'has-file': importFile }"
          @dragover.prevent
          @drop.prevent="handleImportDrop"
          @click="$refs.importInput.click()"
        >
          <template v-if="!importFile">
            <strong>拖拽模型文件到此处</strong>
            <span>或点击选择文件</span>
          </template>
          <template v-else>
            <strong>{{ importFile.name }}</strong>
            <span>{{ formatSize(importFile.size) }}</span>
          </template>
        </div>
        <input ref="importInput" type="file" accept=".pt,.onnx,.torchscript,.engine" hidden @change="handleImportFileSelect" />
        <label class="form-field">
          <span>模型名称</span>
          <input v-model="importForm.model_name" :placeholder="importFile ? importFile.name.replace(/\.[^.]+$/, '') : '可选，默认用文件名'" />
        </label>
        <label class="form-field">
          <span>关联项目</span>
          <select v-model.number="importForm.project_id">
            <option :value="0">不关联</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <label class="form-field">
          <span>备注</span>
          <input v-model="importForm.notes" placeholder="可选" />
        </label>
        <p v-if="importError" class="error">{{ importError }}</p>
        <div class="dialog-actions">
          <button class="secondary-action" @click="closeImportDialog">取消</button>
          <button class="primary-action" :disabled="!importFile || importing" @click="doImport">{{ importing ? '导入中...' : '导入' }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { deleteModel, getModelArtifacts, listModels, listExportFormats, exportModel, getExportStatus, importModel, promoteProduction, updateModel } from '../api/models.js'
import { listProjects } from '../api/projects.js'
import { readActiveProjectContext } from '../state/projectContext.js'
import { pushNotification } from '../state/notifications.js'
import { displayDatasetName, displayModelName, formatSize } from '../utils.js'

const models = ref([])
const projects = ref([])
const artifacts = ref([])
const selected = ref(null)

const imageArtifacts = computed(() => artifacts.value.filter(a => /\.(png|jpg|jpeg|webp)$/i.test(a.name)))
const fileArtifacts = computed(() => artifacts.value.filter(a => !/\.(png|jpg|jpeg|webp)$/i.test(a.name)))
const loading = ref(true)
const error = ref('')
const actionMsg = ref('')
const activeProject = ref(readActiveProjectContext())
const renamingId = ref(null)
const renamingName = ref('')
const editingNotes = ref('')

const projectFilter = ref(activeProject.value?.id || 0)
const formatFilter = ref('')

const FORMAT_LABELS = {
  onnx: 'ONNX',
  engine: 'TensorRT',
  tflite: 'TFLite',
  torchscript: 'TorchScript',
  coreml: 'CoreML',
  openvino: 'OpenVINO',
  paddle: 'Paddle',
  ncnn: 'NCNN',
  saved_model: 'SavedModel',
}

const filteredModels = computed(() => {
  if (projectFilter.value) return models.value.filter(item => Number(item.project_id) === projectFilter.value)
  return models.value
})

const isSingleProjectView = computed(() => Number(projectFilter.value) > 0)

const formatOptions = computed(() => {
  const counts = new Map()
  for (const model of filteredModels.value) {
    const label = modelFormatLabel(model)
    counts.set(label, (counts.get(label) || 0) + 1)
  }
  return Array.from(counts.entries())
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([label, count]) => ({ label, value: label, count }))
})

const bestMap = computed(() => {
  if (!filteredModels.value.length) return '-'
  const values = filteredModels.value.map(item => Number(item.map50_95 || 0))
  return Math.max(...values).toFixed(3)
})

const visibleModels = computed(() => {
  const rows = formatFilter.value
    ? filteredModels.value.filter(model => modelFormatLabel(model) === formatFilter.value)
    : filteredModels.value.slice()
  return rows.sort((a, b) => {
    if (a.is_production !== b.is_production) return a.is_production ? -1 : 1
    return Number(b.id) - Number(a.id)
  })
})

function stripProjectPrefix(text, projectName) {
  const value = String(text || '').trim()
  const prefix = projectName ? `${projectName} / ` : ''
  if (prefix && value.startsWith(prefix)) return value.slice(prefix.length)
  return value
}

function compactSourceName(model) {
  const source = stripProjectPrefix(model.source_training_display_name, model.project_name)
  if (source) return source
  return model.source_type_label || '无关联训练'
}

function compactModelName(model) {
  return displayModelName(model)
}

function compactModelMeta(model) {
  const meta = []
  if (!isSingleProjectView.value && model.project_name) meta.push(model.project_name)
  if (model.source_type_label) meta.push(model.source_type_label)
  return meta.join(' / ') || '模型记录'
}

function modelFormatLabel(model) {
  const key = String(model?.model_format || 'yolo').toLowerCase()
  return FORMAT_LABELS[key] || 'YOLO'
}

const expandedModelId = ref(null)

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [modelResp, projectRows] = await Promise.all([listModels(), listProjects()])
    const modelRows = modelResp.items
    models.value = modelRows
    projects.value = projectRows
    selected.value = null
    expandedModelId.value = null
    artifacts.value = []
  } catch (err) {
    error.value = err?.message || '模型记录加载失败'
  } finally {
    loading.value = false
  }
}

function shortPath(path) {
  if (!path) return '-'
  const n = String(path).replace(/\\/g, '/')
  return n.split('/').pop() || n
}

async function toggleModel(model) {
  if (expandedModelId.value === model.id) {
    expandedModelId.value = null
    selected.value = null
    artifacts.value = []
    return
  }
  expandedModelId.value = model.id
  selected.value = model
  editingNotes.value = model.notes || ''
  actionMsg.value = ''
  try {
    const result = await getModelArtifacts(model.id)
    artifacts.value = result.artifacts || []
  } catch {
    artifacts.value = []
  }
}

async function promote(modelId) {
  try {
    await promoteProduction(modelId)
    actionMsg.value = '已设为生产，旧生产已自动归档。'
    await load()
  } catch (err) {
    actionMsg.value = err?.message || '设置失败'
  }
}

function modelStatus(model) {
  return model.is_production ? '生产' : '归档'
}

function startRename(model) {
  renamingId.value = model.id
  renamingName.value = model.model_name || model.run_id
  nextTick(() => {
    const input = document.querySelector('.inline-rename-input')
    if (input) { input.focus(); input.select() }
  })
}
function cancelRename() { renamingId.value = null; renamingName.value = '' }

async function saveNotes() {
  if (!selected.value) return
  try {
    await updateModel(selected.value.id, { model_name: selected.value.model_name || selected.value.run_id, notes: editingNotes.value })
    selected.value.notes = editingNotes.value
  } catch {}
}
async function saveRename(model) {
  const name = renamingName.value.trim()
  if (!name || name === (model.model_name || model.run_id)) { cancelRename(); return }
  try {
    await updateModel(model.id, { model_name: name })
    model.model_name = name
    if (selected.value?.id === model.id) selected.value.model_name = name
  } catch (err) { alert(err?.message || '重命名失败') }
  renamingId.value = null
}

async function confirmDeleteModel(model) {
  if (!confirm(`确认删除模型「${displayModelName(model)}」？关联的评估记录也将被删除。`)) return
  try {
    await deleteModel(model.id)
    selected.value = null
    artifacts.value = []
    await load()
  } catch (err) {
    actionMsg.value = '删除失败：' + (err?.message || err)
  }
}

function fmtMetric(value) {
  return value === null || value === undefined ? '-' : Number(value).toFixed(3)
}

// ---------------------------------------------------------------------------
// 导出
// ---------------------------------------------------------------------------
const showExportDialog = ref(false)
const exportFormats = ref([])
const exportForm = ref({ format: 'onnx', imgsz: 640, half: false })
const exporting = ref(false)
const exportError = ref('')
const exportResult = ref(null)
const exportLogLines = ref([])
const exportPct = ref(0)
const exportStatus = ref('')
let exportPollTimer = null
let exportProgressTimer = null

function closeExportDialog() {
  if (exporting.value) return // 导出中不允许关闭
  showExportDialog.value = false
  if (exportPollTimer) { clearInterval(exportPollTimer); exportPollTimer = null }
  if (exportProgressTimer) { clearInterval(exportProgressTimer); exportProgressTimer = null }
}

async function openExportDialog() {
  showExportDialog.value = true
  exportError.value = ''
  exportResult.value = null
  exportLogLines.value = []
  exportPct.value = 0
  exportStatus.value = ''
  try {
    if (!exportFormats.value.length) {
      exportFormats.value = await listExportFormats()
    }
  } catch {
    exportFormats.value = [
      { format: 'onnx', label: 'ONNX', description: '通用部署格式' },
      { format: 'torchscript', label: 'TorchScript', description: 'PyTorch JIT' },
    ]
  }
}

async function doExport() {
  if (!selected.value) return
  exporting.value = true
  exportError.value = ''
  exportResult.value = null
  exportPct.value = 0
  exportLogLines.value = []
  exportStatus.value = '正在启动导出 ' + exportForm.value.format.toUpperCase() + ' ...'

  let fakeProgress = 0
  if (exportProgressTimer) clearInterval(exportProgressTimer)
  exportProgressTimer = setInterval(() => {
    fakeProgress += Math.random() * 15
    if (fakeProgress > 90) fakeProgress = 90
    exportPct.value = Math.round(fakeProgress)
  }, 800)

  try {
    await exportModel(selected.value.id, exportForm.value)
    exportStatus.value = '导出中，正在等待转换结果...'
    await pollExportStatus(selected.value.id)
  } catch (err) {
    exportError.value = err?.message || '导出失败'
    exportStatus.value = '导出失败'
    exporting.value = false
    if (exportProgressTimer) { clearInterval(exportProgressTimer); exportProgressTimer = null }
  }
}

async function pollExportStatus(modelId) {
  if (exportPollTimer) { clearInterval(exportPollTimer); exportPollTimer = null }
  return new Promise((resolve) => {
    const tick = async () => {
      try {
        const status = await getExportStatus(modelId)
        exportLogLines.value = (status.log || '').split(/\r?\n/).filter(Boolean).slice(-80)
        if (status.status === 'completed') {
          exportPct.value = 100
          exportStatus.value = '导出完成'
          exportResult.value = {
            files: status.files || [],
            exported_model: status.exported_model || null,
          }
          pushNotification({
            tone: 'success',
            title: '模型导出完成',
            message: status.exported_model ? displayModelName(status.exported_model) : `${displayModelName(selected.value)} 已导出`,
            url: '/registry',
          })
          exporting.value = false
          if (exportPollTimer) { clearInterval(exportPollTimer); exportPollTimer = null }
          if (exportProgressTimer) { clearInterval(exportProgressTimer); exportProgressTimer = null }
          const currentModel = selected.value
          await load()
          selected.value = currentModel
          resolve()
        } else if (status.status === 'failed') {
          exportError.value = '导出失败，请查看日志末尾'
          exportStatus.value = '导出失败'
          pushNotification({
            tone: 'danger',
            title: '模型导出失败',
            message: displayModelName(selected.value),
            url: '/registry',
            duration: 14000,
          })
          exporting.value = false
          if (exportPollTimer) { clearInterval(exportPollTimer); exportPollTimer = null }
          if (exportProgressTimer) { clearInterval(exportProgressTimer); exportProgressTimer = null }
          resolve()
        } else {
          exportStatus.value = '导出中，ONNX/TensorRT 转换可能需要一段时间...'
        }
      } catch (err) {
        exportError.value = err?.message || '读取导出状态失败'
        exportStatus.value = '导出状态读取失败'
        exporting.value = false
        if (exportPollTimer) { clearInterval(exportPollTimer); exportPollTimer = null }
        if (exportProgressTimer) { clearInterval(exportProgressTimer); exportProgressTimer = null }
        resolve()
      }
    }
    tick()
    exportPollTimer = setInterval(tick, 1200)
  })
}

// ---------------------------------------------------------------------------
// 导入
// ---------------------------------------------------------------------------
const showImportDialog = ref(false)
const importFile = ref(null)
function closeImportDialog() {
  showImportDialog.value = false
  importFile.value = null
  importError.value = ''
}
const importForm = ref({ model_name: '', project_id: 0, notes: '' })
const importing = ref(false)
const importError = ref('')

function handleImportDrop(e) {
  const files = Array.from(e.dataTransfer?.files || [])
  if (files.length) importFile.value = files[0]
}
function handleImportFileSelect(e) {
  const files = Array.from(e.target.files || [])
  if (files.length) importFile.value = files[0]
}

async function doImport() {
  if (!importFile.value) return
  importing.value = true
  importError.value = ''
  try {
    const form = new FormData()
    form.append('file', importFile.value)
    form.append('model_name', importForm.value.model_name || importFile.value.name.replace(/\.[^.]+$/, ''))
    form.append('project_id', String(importForm.value.project_id || 0))
    form.append('notes', importForm.value.notes || '')
    await importModel(form)
    showImportDialog.value = false
    importFile.value = null
    importForm.value = { model_name: '', project_id: 0, notes: '' }
    await load()
  } catch (err) {
    importError.value = err?.message || '导入失败'
  } finally {
    importing.value = false
  }
}

</script>

<style scoped>
.registry-card-title {
  gap: 12px;
  align-items: flex-start;
}

.registry-title-copy {
  display: grid;
  gap: 4px;
}

.registry-title-copy span {
  font-size: 12px;
  color: var(--muted-1);
}

.registry-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.registry-table td {
  padding-top: 6px;
  padding-bottom: 6px;
}

.registry-name-cell {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.registry-row-tools {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.model-name-cell--compact {
  display: block;
  max-width: 280px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.format-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(92, 180, 255, 0.12);
  border: 1px solid rgba(92, 180, 255, 0.2);
  color: var(--primary-ink);
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
}

.metric-stack {
  display: grid;
  gap: 3px;
}

.metric-stack strong {
  color: var(--heading);
  font-size: 12px;
}

.status-cell-stack {
  align-items: flex-start;
}

@media (max-width: 1100px) {
  .registry-card-title {
    flex-direction: column;
  }

  .registry-toolbar {
    width: 100%;
  }

  .model-name-cell--compact {
    max-width: 200px;
  }
}
</style>
