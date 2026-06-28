<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>推理检测</h1>
        <p>上传图片、批量检查结果，或直接调用测试集和摄像头做推理。</p>
      </div>
    </div>

    <div v-if="loadingInitial" class="loading">加载中...</div>

    <template v-else>
      <div class="infobar">
        <div class="infer-tabs">
          <button :class="{ active: mode === 'image' }" @click="mode = 'image'">图片推理</button>
          <button :class="{ active: mode === 'dataset' }" @click="mode = 'dataset'">测试集</button>
          <button :class="{ active: mode === 'camera' }" @click="mode = 'camera'">摄像头</button>
        </div>
      </div>

      <template v-if="mode === 'image'">
        <div class="infobar">
          <select v-model="modelId" class="infobar-select">
            <option :value="0" disabled>选择模型</option>
            <option v-for="model in models" :key="model.id" :value="model.id">{{ displayModelName(model) }} - {{ modelFormatLabel(model) }}</option>
          </select>
          <label class="infobar-label">置信度 <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="confidence" /><em>{{ confidence.toFixed(2) }}</em></label>
          <label class="infobar-label">IOU <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="iou" /><em>{{ iou.toFixed(2) }}</em></label>
          <button class="primary-action small-action" :disabled="!canRun || running" @click="runInference">{{ running ? '推理中...' : '运行推理' }}</button>
          <button class="secondary-action small-action" :disabled="!selectedFiles.length" @click="clearFiles">清空</button>
        </div>

        <div class="image-infer-layout">
          <aside class="image-infer-sidebar">
            <div class="card section-pad image-upload-card">
              <div class="card-title" style="padding:0 0 8px">
                <strong>输入图片</strong>
                <span>{{ selectedFiles.length }} 张</span>
              </div>
              <div class="upload-box upload-clickable" :class="{ 'has-file': selectedFiles.length }" @dragover.prevent @drop.prevent="handleDrop">
                <AppIcon name="upload" />
                <strong>{{ selectedFiles.length ? '继续添加图片' : '拖拽图片到这里' }}</strong>
                <span>支持多图，也可以直接选择整个文件夹。</span>
              </div>
              <div class="image-upload-actions">
                <button class="primary-action small-action" @click="triggerUpload">选择图片</button>
                <button class="secondary-action small-action" @click="triggerFolderUpload">选择文件夹</button>
              </div>
              <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/bmp,image/webp" multiple hidden @change="handleFileSelect" />
              <input ref="folderInput" type="file" accept="image/jpeg,image/png,image/bmp,image/webp" webkitdirectory directory multiple hidden @change="handleFileSelect" />
            </div>

            <div class="card section-pad image-source-card" v-if="selectedFiles.length">
              <div class="card-title" style="padding:0 0 8px">
                <strong>待检图片</strong>
                <span>{{ activeSelectedFile ? activeIndex + 1 : 0 }}/{{ selectedFiles.length }}</span>
              </div>
              <div class="selected-media-list">
                <button
                  v-for="(file, index) in selectedFiles"
                  :key="thumbKeys[index]"
                  :class="['selected-media-item', { active: index === activeIndex }]"
                  @click="activeIndex = index"
                >
                  <div class="selected-media-thumb">
                    <img v-if="thumbUrls[index]" :src="thumbUrls[index]" :alt="file.name" />
                    <span v-else class="thumb-placeholder">{{ String(file.name || '?').slice(0, 1) }}</span>
                  </div>
                  <div class="selected-media-meta">
                    <strong>{{ file.name }}</strong>
                    <span>{{ formatFileSize(file.size) }}</span>
                    <span v-if="fileRelativePath(file)" class="selected-media-path">{{ fileRelativePath(file) }}</span>
                  </div>
                  <span v-if="batchResult?.results?.[index]" class="selected-media-status">{{ batchResult.results[index].box_count }} 目标</span>
                  <button class="thumb-remove" @click.stop="removeFile(index)" :disabled="running">×</button>
                </button>
              </div>
            </div>

            <div class="card section-pad image-history-card" v-if="history.length">
              <div class="card-title" style="padding:0 0 8px">
                <strong>推理历史</strong>
                <span>{{ history.length }} 条</span>
              </div>
              <div class="infer-history">
                <div v-for="item in history.slice(0, 12)" :key="item.session_id" :class="['history-row', { active: item.session_id === activeHistoryId }]" @click="loadHistoryResult(item)">
                  <div class="history-row-head">
                    <strong>{{ item.batch_name || '批量推理' }}</strong>
                    <button class="history-delete-btn" @click.stop="removeHistory(item)">删除</button>
                  </div>
                  <span class="muted-text">{{ item.total_images || 0 }} 张 · {{ item.total_boxes || 0 }} 个目标</span>
                </div>
              </div>
            </div>
          </aside>

          <div class="image-infer-workspace">
            <div class="card section-pad preview-surface" v-if="activeInputSrc">
              <div class="dataset-result-header">
                <strong>原图预览</strong>
                <span class="muted-text">{{ activePreviewTitle }}</span>
              </div>
              <div class="preview-stage-card" @click="previewSrc = activeInputSrc">
                <img :src="activeInputSrc" :alt="activeSelectedFile?.name || activeResult?.filename || 'input'" />
              </div>
              <div class="preview-meta-row">
                <span class="preview-meta-pill">第 {{ activeIndex + 1 }} 张</span>
                <span class="preview-meta-pill">{{ activeSelectedFile ? formatFileSize(activeSelectedFile.size) : '-' }}</span>
                <span v-if="fileRelativePath(activeSelectedFile)" class="preview-meta-pill">{{ fileRelativePath(activeSelectedFile) }}</span>
              </div>
            </div>
            <div class="card section-pad preview-surface" v-else>
              <div class="stage-empty">
                <AppIcon name="upload" />
                <span>{{ activeHistoryId ? '历史记录只保留检测结果，原图预览仅对当前上传图片显示。' : '先上传图片，再检查原图和检测结果。' }}</span>
              </div>
            </div>

            <div class="card section-pad preview-surface" v-if="activeResult?.prediction_image_url">
              <div class="dataset-result-header">
                <strong>检测结果</strong>
                <span class="muted-text">{{ activeResult.box_count || 0 }} 个目标 · {{ formatElapsed(activeResult.elapsed_seconds) }}</span>
              </div>
              <div class="preview-stage-card" @click="previewSrc = activeResult.prediction_image_url">
                <img :src="activeResult.prediction_image_url" :alt="activeResult.filename || 'prediction'" />
              </div>
              <div class="preview-meta-row">
                <span class="preview-meta-pill">{{ activeResult.filename || '-' }}</span>
                <span class="preview-meta-pill">{{ activeResult.image_width || 0 }} × {{ activeResult.image_height || 0 }}</span>
              </div>
            </div>
            <div v-else-if="activeSelectedFile || activeHistoryId" class="card section-pad preview-surface">
              <div class="dataset-result-header">
                <strong>检测结果</strong>
                <span class="muted-text">{{ running ? `已处理 ${processedCount}/${selectedFiles.length}` : '等待生成结果' }}</span>
              </div>
              <div class="preview-stage-card preview-stage-card--placeholder">
                <div class="stage-empty">
                  <AppIcon name="image" />
                  <span>{{ running ? '当前图片还在推理中。' : '运行推理后，这里显示当前图片的检测图。' }}</span>
                </div>
              </div>
            </div>

            <div class="card section-pad preview-surface" v-if="batchResult?.results?.length">
              <div class="dataset-result-header">
                <strong>{{ batchResult.batch_name || '批量推理' }}</strong>
                <span class="muted-text">{{ batchResult.results.length }} 张 · {{ batchResult.total_boxes || 0 }} 个目标 · {{ formatElapsed(batchResult.total_elapsed) }}</span>
              </div>
              <div class="infer-grid infer-grid--large">
                <div v-for="(result, index) in batchResult.results" :key="`${result.filename}-${index}`" :class="['infer-card', { active: index === activeIndex }]" @click="selectResult(index)">
                  <div class="infer-card-img">
                    <img v-if="result.prediction_image_url" :src="result.prediction_image_url" :alt="result.filename" />
                    <div v-else class="img-empty">?</div>
                    <div class="infer-card-overlay"><span>{{ result.box_count }} 目标</span></div>
                  </div>
                  <div class="infer-card-name">{{ result.filename }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="mode === 'dataset'">
        <div class="infobar">
          <select v-model="modelId" class="infobar-select">
            <option :value="0" disabled>选择模型</option>
            <option v-for="model in models" :key="model.id" :value="model.id">{{ displayModelName(model) }} - {{ modelFormatLabel(model) }}</option>
          </select>
          <select v-model="datasetVersionId" class="infobar-select" style="min-width:200px">
            <option :value="0" disabled>选择数据集</option>
            <option v-for="version in datasetVersions" :key="version.id" :value="version.id">{{ version.dataset_name }}-{{ version.version }} ({{ version.image_count }}张)</option>
          </select>
          <button class="primary-action small-action" :disabled="!datasetVersionId || !modelId || running" @click="runDatasetInference">{{ running ? '推理中...' : '运行推理' }}</button>
        </div>
        <div v-if="datasetResult" class="dataset-result-wrap" style="margin-top:10px">
          <div class="dataset-result-header">
            <strong>推理结果</strong>
            <span class="muted-text">{{ datasetResult.results?.length || 0 }} 张 · {{ datasetResult.total_boxes || 0 }} 个目标</span>
          </div>
          <div class="dataset-grid">
            <div v-for="(result, index) in (datasetResult.results || [])" :key="index" class="dataset-card" @click="previewSrc = result.prediction_image_url">
              <div class="dataset-card-img">
                <img v-if="result.prediction_image_url" :src="result.prediction_image_url" :alt="result.filename" />
                <div v-else class="img-empty">?</div>
                <div class="dataset-card-overlay">
                  <span>{{ result.box_count }} 目标 · {{ formatElapsed(result.elapsed_seconds) }}</span>
                </div>
              </div>
              <div class="dataset-card-name">{{ result.filename }}</div>
            </div>
          </div>
        </div>
      </template>

      <template v-if="mode === 'camera'">
        <div class="infobar">
          <select v-model="modelId" class="infobar-select">
            <option :value="0" disabled>选择模型</option>
            <option v-for="model in models" :key="model.id" :value="model.id">{{ displayModelName(model) }} - {{ modelFormatLabel(model) }}</option>
          </select>
          <label class="infobar-label">置信度 <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="confidence" /><em>{{ confidence.toFixed(2) }}</em></label>
          <label class="infobar-label">IOU <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="iou" /><em>{{ iou.toFixed(2) }}</em></label>
        </div>
        <CameraPanel :modelId="modelId" :confidence="confidence" :iou="iou" @error="error = $event" />
      </template>

      <div v-if="previewSrc" class="lightbox-overlay" @click="previewSrc = ''">
        <button class="lightbox-close" @click="previewSrc = ''">×</button>
        <img :src="previewSrc" class="lightbox-img" @click.stop />
      </div>

      <p v-if="error" class="error" style="margin-top:8px">{{ error }}</p>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import CameraPanel from '../components/CameraPanel.vue'
import { listImages, listVersions } from '../api/datasets.js'
import { deleteInferenceHistory, listHistory, predict } from '../api/inference.js'
import { listModels } from '../api/models.js'
import { displayModelName } from '../utils.js'

const models = ref([])
const datasetVersions = ref([])
const loadingInitial = ref(true)
const mode = ref('image')
const datasetVersionId = ref(0)
const modelId = ref(0)
const confidence = ref(0.25)
const iou = ref(0.45)
const running = ref(false)
const error = ref('')
const selectedFiles = ref([])
const thumbUrls = ref([])
const thumbKeys = ref([])
const activeIndex = ref(0)
const processedCount = ref(0)
const batchResult = ref(null)
const datasetResult = ref(null)
const previewSrc = ref('')
const history = ref([])
const activeHistoryId = ref(null)
const fileInput = ref(null)
const folderInput = ref(null)

const canRun = computed(() => modelId.value && selectedFiles.value.length > 0)
const activeSelectedFile = computed(() => selectedFiles.value[activeIndex.value] || null)
const activeInputSrc = computed(() => activeHistoryId.value ? '' : (thumbUrls.value[activeIndex.value] || ''))
const activeResult = computed(() => batchResult.value?.results?.[activeIndex.value] || null)
const activePreviewTitle = computed(() => {
  if (activeSelectedFile.value?.name) return activeSelectedFile.value.name
  if (activeResult.value?.filename) return activeResult.value.filename
  return '-'
})

onMounted(async () => {
  try {
    const [modelRows, versionRows, historyRows] = await Promise.all([
      listModels().then(result => result.items || []),
      listVersions().then(result => result.items || []),
      listHistory(20),
    ])
    models.value = modelRows
    datasetVersions.value = versionRows
    history.value = historyRows || []
    const production = modelRows.find(item => item.is_production) || modelRows[0]
    if (production) modelId.value = production.id
  } catch (err) {
    error.value = err?.message || '加载失败'
  } finally {
    loadingInitial.value = false
  }
})

onBeforeUnmount(() => {
  for (const url of thumbUrls.value) URL.revokeObjectURL(url)
})

function triggerUpload() {
  if (!running.value) fileInput.value?.click()
}

function triggerFolderUpload() {
  if (!running.value) folderInput.value?.click()
}

function handleFileSelect(event) {
  addFiles(Array.from(event.target.files || []))
  event.target.value = ''
}

function handleDrop(event) {
  addFiles(Array.from(event.dataTransfer.files || []))
}

function addFiles(files) {
  const images = files.filter(file => /\.(jpg|jpeg|png|bmp|webp)$/i.test(file.name))
  if (!images.length) return
  if (activeHistoryId.value || batchResult.value?.results?.length) {
    batchResult.value = null
    activeHistoryId.value = null
  }
  const hadFiles = selectedFiles.value.length > 0
  for (const file of images) {
    selectedFiles.value.push(file)
    thumbUrls.value.push(URL.createObjectURL(file))
    thumbKeys.value.push(`${file.name}-${file.size}-${file.lastModified}-${thumbKeys.value.length}`)
  }
  if (!hadFiles) {
    activeIndex.value = 0
  } else if (selectedFiles.value.length && activeIndex.value >= selectedFiles.value.length) {
    activeIndex.value = selectedFiles.value.length - 1
  }
}

function removeFile(index) {
  const url = thumbUrls.value[index]
  if (url) URL.revokeObjectURL(url)
  selectedFiles.value.splice(index, 1)
  thumbUrls.value.splice(index, 1)
  thumbKeys.value.splice(index, 1)
  if (batchResult.value?.results?.length) batchResult.value = null
  activeHistoryId.value = null
  if (activeIndex.value >= selectedFiles.value.length) {
    activeIndex.value = Math.max(0, selectedFiles.value.length - 1)
  }
}

function clearFiles() {
  for (const url of thumbUrls.value) URL.revokeObjectURL(url)
  selectedFiles.value = []
  thumbUrls.value = []
  thumbKeys.value = []
  batchResult.value = null
  activeIndex.value = 0
  activeHistoryId.value = null
  error.value = ''
  previewSrc.value = ''
}

async function runInference() {
  if (!canRun.value) return
  running.value = true
  error.value = ''
  batchResult.value = null
  processedCount.value = 0
  activeHistoryId.value = null
  previewSrc.value = ''

  const batchSize = 5
  const allResults = []
  const batchName = buildBatchName(selectedFiles.value)

  for (let index = 0; index < selectedFiles.value.length; index += batchSize) {
    const batch = selectedFiles.value.slice(index, index + batchSize)
    try {
      const result = await predict(modelId.value, batch, confidence.value, iou.value, batchName)
      allResults.push(...(result.results || []))
      processedCount.value = Math.min(index + batchSize, selectedFiles.value.length)
      batchResult.value = { ...result, batch_name: batchName, results: [...allResults] }
    } catch (err) {
      error.value = err?.message || '推理失败'
      break
    }
  }

  running.value = false
  if (allResults.length) await loadHistory()
}

function selectResult(index) {
  activeIndex.value = index
}

async function loadHistoryResult(item) {
  activeHistoryId.value = item.session_id
  batchResult.value = item
  activeIndex.value = 0
  previewSrc.value = ''
}

async function removeHistory(item) {
  if (!confirm(`确认删除推理历史「${item.batch_name || item.session_id}」？`)) return
  try {
    await deleteInferenceHistory(item.session_id)
    history.value = history.value.filter(row => row.session_id !== item.session_id)
    if (activeHistoryId.value === item.session_id) {
      activeHistoryId.value = null
      batchResult.value = null
    }
  } catch (err) {
    error.value = err?.message || '删除失败'
  }
}

async function runDatasetInference() {
  if (!datasetVersionId.value || !modelId.value) return
  running.value = true
  error.value = ''
  datasetResult.value = null
  try {
    const response = await listImages({ versionId: datasetVersionId.value, pageSize: 200 })
    const imageItems = response.items || []
    if (!imageItems.length) {
      error.value = '该数据集没有图片'
      running.value = false
      return
    }
    const files = []
    for (const item of imageItems) {
      const imageUrl = datasetImageUrl(item.image_path)
      if (!imageUrl) continue
      const imageResponse = await fetch(imageUrl)
      if (!imageResponse.ok) continue
      const blob = await imageResponse.blob()
      files.push(new File([blob], basename(item.image_path), { type: blob.type }))
    }
    if (!files.length) {
      error.value = '无法加载图片'
      running.value = false
      return
    }
    const result = await predict(modelId.value, files.slice(0, 50), confidence.value, iou.value, `测试集_${datasetVersionId.value}`)
    result.total_boxes = (result.results || []).reduce((sum, row) => sum + (row.box_count || 0), 0)
    datasetResult.value = result
  } catch (err) {
    error.value = err?.message || '推理失败'
  }
  running.value = false
}

async function loadHistory() {
  try {
    history.value = await listHistory(20) || []
  } catch {}
}

function modelFormatLabel(model) {
  return model?.model_format ? String(model.model_format).toUpperCase() : 'YOLO'
}

function buildBatchName(files) {
  const names = (files || []).map(file => String(file?.name || '').replace(/\.[^.]+$/, '')).filter(Boolean)
  if (!names.length) return '批量推理'
  if (names.length === 1) return names[0]
  if (names.length === 2) return `${names[0]} + ${names[1]}`
  return `${names[0]} 等 ${names.length} 张`
}

function datasetImageUrl(path) {
  const normalized = String(path || '').replace(/\\/g, '/')
  const marker = '/datasets/'
  const fullIndex = normalized.indexOf(marker)
  if (fullIndex >= 0) return '/images/' + normalized.slice(fullIndex + marker.length)
  const relativeIndex = normalized.indexOf('datasets/')
  if (relativeIndex >= 0) return '/images/' + normalized.slice(relativeIndex + 'datasets/'.length)
  return ''
}

function basename(path) {
  return String(path || '').replace(/\\/g, '/').split('/').pop() || '-'
}

function fileRelativePath(file) {
  const relativePath = String(file?.webkitRelativePath || '').trim()
  if (!relativePath) return ''
  return relativePath.replace(/\\/g, '/')
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0)
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function formatElapsed(value) {
  if (value === null || value === undefined || value === '') return '-'
  return `${Number(value).toFixed(1)} 秒`
}
</script>
