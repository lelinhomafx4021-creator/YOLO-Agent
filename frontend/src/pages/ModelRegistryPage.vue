<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>模型仓库</h1>
        <p>管理训练产出的模型，标记生产版本，导出部署。</p>
      </div>
      <div class="header-actions">
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
        <div class="card-title" style="padding:12px 18px 0">
          <strong>模型列表</strong>
          <select v-model.number="projectFilter" class="project-filter-select">
            <option :value="0">全部项目</option>
            <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <div class="table-card section-pad">
          <table class="training-table">
            <thead>
              <tr>
                <th>模型名称</th>
                <th>数据批次</th>
                <th>基础模型</th>
                <th>mAP50</th>
                <th>mAP50-95</th>
                <th>状态</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(group, groupName) in groupedModels" :key="groupName">
                <tr class="model-group-header">
                  <td colspan="6">
                    <strong>{{ groupName }}</strong>
                    <span class="muted-text" style="margin-left:8px;font-size:11px">{{ group.length }} 版本</span>
                  </td>
                </tr>
                <template v-for="model in group" :key="model.id">
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
                        <span class="model-name-cell">{{ model.model_name || model.run_id }}</span>
                        <button class="icon-btn-sm" title="重命名" @click.stop="startRename(model)">✎</button>
                      </template>
                    </td>
                    <td class="muted-text">{{ model.dataset_version }}</td>
                    <td class="mono muted-text">{{ shortPath(model.base_model) }}</td>
                    <td class="mono">{{ fmtMetric(model.map50) }}</td>
                    <td class="mono">{{ fmtMetric(model.map50_95) }}</td>
                    <td>
                      <span :class="['chip', model.is_production ? 'success' : '']">{{ modelStatus(model) }}</span>
                    </td>
                  </tr>
                  <!-- 展开详情行 -->
                  <tr v-if="expandedModelId === model.id" class="model-detail-row">
                    <td colspan="6">
                      <div class="model-detail-panel">
                        <div class="detail-grid">
                          <div class="info-item"><span>训练 Run</span><strong>{{ model.run_id }}</strong></div>
                          <div class="info-item"><span>数据批次</span><strong>{{ model.dataset_name }} / {{ model.dataset_version }}</strong></div>
                          <div class="info-item"><span>基础模型</span><strong>{{ model.base_model }}</strong></div>
                          <div class="info-item"><span>最佳 Epoch</span><strong>{{ model.best_epoch ?? '-' }}</strong></div>
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
              </template>
              <tr v-if="filteredModels.length === 0">
                <td colspan="6" class="empty-cell">还没有模型记录。训练完成后模型会自动注册到此处。</td>
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
        <p class="helper-text">将「{{ selected?.model_name || selected?.run_id }}」导出为部署格式</p>
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
        <div v-if="exporting" class="log-terminal-wrap" style="margin:12px 0">
          <div class="log-toolbar">
            <span class="log-status status-running">导出中...</span>
          </div>
          <div class="log-terminal" style="max-height:120px">
            <div v-for="(line, i) in exportLogLines" :key="i" class="log-line">{{ line }}</div>
          </div>
        </div>
        <div v-if="exportResult" class="export-result">
          <p class="action-msg">导出完成！{{ exportResult.files.length }} 个文件</p>
          <div v-for="f in exportResult.files" :key="f.name" class="artifact-row">
            <strong>{{ f.name }}</strong>
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
import { deleteModel, getModelArtifacts, listModels, listExportFormats, exportModel, getExportLog, importModel, promoteProduction, updateModel } from '../api/models.js'
import { listProjects } from '../api/projects.js'
import { readActiveProjectContext } from '../state/projectContext.js'
import { formatSize } from '../utils.js'

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

const projectFilter = ref(0)

const filteredModels = computed(() => {
  if (projectFilter.value) return models.value.filter(item => Number(item.project_id) === projectFilter.value)
  return models.value
})

const bestMap = computed(() => {
  if (!filteredModels.value.length) return '-'
  const values = filteredModels.value.map(item => Number(item.map50_95 || 0))
  return Math.max(...values).toFixed(3)
})

const groupedModels = computed(() => {
  const groups = {}
  for (const model of filteredModels.value) {
    const fmt = model.model_format || 'YOLO'
    const label = { onnx: 'ONNX', engine: 'TensorRT', tflite: 'TFLite', torchscript: 'TorchScript', coreml: 'CoreML', openvino: 'OpenVINO', paddle: 'Paddle', ncnn: 'NCNN', saved_model: 'SavedModel' }[fmt] || 'YOLO'
    if (!groups[label]) groups[label] = []
    groups[label].push(model)
  }
  for (const key of Object.keys(groups)) {
    groups[key].sort((a, b) => a.id - b.id)
  }
  return groups
})

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

function getBestVersion(group) {
  if (!group.length) return null
  return group.reduce((best, m) => {
    const score = Number(m.map50_95 || 0)
    const bestScore = Number(best.map50_95 || 0)
    return score > bestScore ? m : best
  }, group[0])
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
  if (!confirm(`确认删除模型「${model.run_id}」？关联的评估记录也将被删除。`)) return
  try {
    await deleteModel(model.id)
    selected.value = null
    artifacts.value = []
    await load()
  } catch (err) {
    actionMsg.value = '删除失败：' + (err?.message || err)
  }
}

function projectName(projectId) {
  return projects.value.find(item => Number(item.id) === Number(projectId))?.name || '未归属'
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

function closeExportDialog() {
  if (exporting.value) return // 导出中不允许关闭
  showExportDialog.value = false
  if (exportPollTimer) { clearInterval(exportPollTimer); exportPollTimer = null }
}

async function openExportDialog() {
  showExportDialog.value = true
  exportError.value = ''
  exportResult.value = null
  exportLogLines.value = []
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
  exportStatus.value = '正在导出 ' + exportForm.value.format.toUpperCase() + ' ...'

  // 模拟进度（YOLO 导出无实时进度，用脉冲动画代替）
  let fakeProgress = 0
  const progressTimer = setInterval(() => {
    fakeProgress += Math.random() * 15
    if (fakeProgress > 90) fakeProgress = 90
    exportPct.value = Math.round(fakeProgress)
  }, 800)

  try {
    const result = await exportModel(selected.value.id, exportForm.value)
    exportPct.value = 100
    exportStatus.value = '导出完成'
    exportResult.value = result
    await load()  // 刷新模型列表
  } catch (err) {
    exportError.value = err?.message || '导出失败'
    exportStatus.value = '导出失败'
  } finally {
    exporting.value = false
    clearInterval(progressTimer)
    setTimeout(() => { if (exportPct.value === 100) { exportPct.value = 0; exportStatus.value = '' } }, 3000)
  }
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
