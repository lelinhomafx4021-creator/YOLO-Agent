<template>
  <section class="page compact-page">
    <div class="page-header">
      <div><h1>推理检测</h1><p>上传图片，用已注册模型进行目标检测</p></div>
    </div>

    <div v-if="loadingInitial" class="loading">加载中...</div>

    <template v-else>
      <!-- 模式切换 -->
      <div class="infobar">
        <div class="infer-tabs">
          <button :class="{ active: mode === 'image' }" @click="mode = 'image'">图片推理</button>
          <button :class="{ active: mode === 'dataset' }" @click="mode = 'dataset'">测试集</button>
          <button :class="{ active: mode === 'camera' }" @click="mode = 'camera'">摄像头</button>
        </div>
      </div>

      <!-- ====== 图片推理 ====== -->
      <template v-if="mode === 'image'">
        <div class="infobar">
          <select v-model="modelId" class="infobar-select">
            <option :value="0" disabled>选择模型</option>
            <option v-for="m in models" :key="m.id" :value="m.id">{{ displayModelName(m) }} — {{ modelFormatLabel(m) }}</option>
          </select>
          <label class="infobar-label">置信度 <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="confidence" /><em>{{ confidence.toFixed(2) }}</em></label>
          <label class="infobar-label">IOU <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="iou" /><em>{{ iou.toFixed(2) }}</em></label>
          <button class="primary-action small-action" :disabled="!canRun || running" @click="runInference">{{ running ? `推理中...` : '运行推理' }}</button>
          <button class="secondary-action small-action" :disabled="!selectedFiles.length" @click="clearFiles">清空</button>
        </div>

        <div class="infer-layout">
          <div class="infer-left">
            <div class="upload-box upload-clickable" :class="{ 'has-file': selectedFiles.length }" @dragover.prevent @drop.prevent="handleDrop" @click="triggerUpload">
              <template v-if="!selectedFiles.length"><AppIcon name="upload" /><span>拖拽或点击上传图片</span></template>
              <template v-else><strong>{{ selectedFiles.length }} 张</strong><span>继续添加</span></template>
            </div>
            <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/bmp,image/webp" multiple hidden @change="handleFileSelect" />
            <div class="infer-thumbs" v-if="selectedFiles.length">
              <div v-for="(f, i) in selectedFiles" :key="i" :class="['infer-thumb', { active: i === activeIndex }]" @click="activeIndex = i">
                <img v-if="thumbUrls[i]" :src="thumbUrls[i]" /><span v-else class="thumb-placeholder">{{ f.name.slice(0,1) }}</span>
                <button class="thumb-remove" @click.stop="removeFile(i)" :disabled="running">×</button>
              </div>
            </div>
            <div class="infer-history" v-if="history.length">
              <div class="card-title" style="padding:6px 0"><strong>历史</strong></div>
              <div v-for="h in history.slice(0,8)" :key="h.session_id" :class="['history-row',{active:h.session_id===activeHistoryId}]" @click="loadHistoryResult(h)">
                <span>{{ h.batch_name||'推理' }}</span><span class="muted-text">{{ h.total_images }}图·{{ h.total_boxes }}目标</span>
              </div>
            </div>
          </div>
          <div class="infer-stage">
            <div v-if="!batchResult && !hasInput" class="stage-empty"><AppIcon name="upload" /><span>上传图片并运行推理</span></div>
            <template v-if="batchResult">
              <div class="dataset-result-header" style="padding:10px 10px 0">
                <strong>{{ batchResult.batch_name || '批量推理' }}</strong>
                <span class="muted-text">{{ batchResult.results?.length || 0 }} 张 · {{ batchResult.total_boxes || 0 }} 个目标</span>
              </div>
              <div class="infer-grid">
                <div v-for="(r, i) in batchResult.results" :key="i" class="infer-card" @click="previewSrc = r.prediction_image_url">
                  <div class="infer-card-img"><img v-if="r.prediction_image_url" :src="r.prediction_image_url" /><div v-else class="img-empty">?</div><div class="infer-card-overlay"><span>{{ r.box_count }}目标</span></div></div>
                  <div class="infer-card-name">{{ r.filename }}</div>
                </div>
              </div>
            </template>
            <div v-if="previewSrc" class="lightbox-overlay" @click="previewSrc=''"><button class="lightbox-close" @click="previewSrc=''">✕</button><img :src="previewSrc" class="lightbox-img" @click.stop /></div>
          </div>
        </div>
      </template>

      <!-- ====== 测试集 ====== -->
      <template v-if="mode === 'dataset'">
        <div class="infobar">
          <select v-model="modelId" class="infobar-select">
            <option :value="0" disabled>选择模型</option>
            <option v-for="m in models" :key="m.id" :value="m.id">{{ displayModelName(m) }} — {{ modelFormatLabel(m) }}</option>
          </select>
          <select v-model="datasetVersionId" class="infobar-select" style="min-width:200px">
            <option :value="0" disabled>选择数据集</option>
            <option v-for="v in datasetVersions" :key="v.id" :value="v.id">{{ v.dataset_name }} ({{ v.image_count }}张)</option>
          </select>
          <button class="primary-action small-action" :disabled="!datasetVersionId || !modelId || running" @click="runDatasetInference">{{ running ? '推理中...' : '运行推理' }}</button>
        </div>
        <!-- 测试集结果：大图网格 -->
        <div v-if="datasetResult" class="dataset-result-wrap" style="margin-top:10px">
          <div class="dataset-result-header">
            <strong>推理结果</strong>
            <span class="muted-text">{{ datasetResult.results?.length || 0 }} 张 · {{ datasetResult.total_boxes || 0 }} 个目标</span>
          </div>
          <div class="dataset-grid">
            <div v-for="(r, i) in (datasetResult.results || [])" :key="i" class="dataset-card" @click="previewSrc = r.prediction_image_url">
              <div class="dataset-card-img">
                <img v-if="r.prediction_image_url" :src="r.prediction_image_url" />
                <div v-else class="img-empty">?</div>
                <div class="dataset-card-overlay">
                  <span>{{ r.box_count }} 目标 · {{ r.elapsed_seconds?.toFixed(1) }}s</span>
                </div>
              </div>
              <div class="dataset-card-name">{{ r.filename }}</div>
            </div>
          </div>
        </div>
        <div v-if="previewSrc" class="lightbox-overlay" @click="previewSrc=''"><button class="lightbox-close" @click="previewSrc=''">✕</button><img :src="previewSrc" class="lightbox-img" @click.stop /></div>
      </template>

      <!-- ====== 摄像头 ====== -->
      <template v-if="mode === 'camera'">
        <div class="infobar">
          <select v-model="modelId" class="infobar-select">
            <option :value="0" disabled>选择模型</option>
            <option v-for="m in models" :key="m.id" :value="m.id">{{ displayModelName(m) }} — {{ modelFormatLabel(m) }}</option>
          </select>
          <label class="infobar-label">置信度 <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="confidence" /><em>{{ confidence.toFixed(2) }}</em></label>
          <label class="infobar-label">IOU <input type="range" min="0.05" max="0.95" step="0.05" v-model.number="iou" /><em>{{ iou.toFixed(2) }}</em></label>
        </div>
        <CameraPanel :modelId="modelId" :confidence="confidence" :iou="iou" @error="error = $event" />
      </template>

      <p v-if="error" class="error" style="margin-top:8px">{{ error }}</p>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import CameraPanel from '../components/CameraPanel.vue'
import { listModels } from '../api/models.js'
import { listImages, listVersions } from '../api/datasets.js'
import { predict, listHistory } from '../api/inference.js'
import { displayModelName } from '../utils.js'

const models = ref([])
const datasetVersions = ref([])
const loadingInitial = ref(true)
const mode = ref('image')
const datasetVersionId = ref(0)
const modelId = ref(0)
const projectFilter = ref('')
const confidence = ref(0.25)
const iou = ref(0.45)
const running = ref(false)
const error = ref('')
const selectedFiles = ref([])
const thumbUrls = ref([])
const activeIndex = ref(0)
const processedCount = ref(0)
const batchResult = ref(null)
const datasetResult = ref(null)
const previewSrc = ref('')
const history = ref([])
const activeHistoryId = ref(null)

const filteredModels = computed(() => {
  if (!projectFilter.value) return models.value
  return models.value.filter(m => String(m.project_id || '') === projectFilter.value)
})
const canRun = computed(() => modelId.value && selectedFiles.value.length > 0)
const hasInput = computed(() => selectedFiles.value.length > 0)

onMounted(async () => {
  try {
    const [ms, vs, h] = await Promise.all([
      listModels().then(r => r.items),
      listVersions().then(r => r.items),
      listHistory(20),
    ])
    models.value = ms
    datasetVersions.value = vs
    history.value = h || []
    // 自动选生产模型
    const prod = ms.find(m => m.is_production) || ms[0]
    if (prod) modelId.value = prod.id
  } catch (e) { error.value = '加载失败' }
  finally { loadingInitial.value = false }
})

function triggerUpload() { if (!running.value) document.querySelector('input[type=file]')?.click() }
function handleFileSelect(e) { addFiles(Array.from(e.target.files || [])) }
function handleDrop(e) { addFiles(Array.from(e.dataTransfer.files || [])) }
function addFiles(files) {
  const imgs = files.filter(f => /\.(jpg|jpeg|png|bmp|webp)$/i.test(f.name))
  selectedFiles.value = [...selectedFiles.value, ...imgs]
  for (const f of imgs) { thumbUrls.value.push(URL.createObjectURL(f)) }
}
function removeFile(i) { selectedFiles.value.splice(i, 1); thumbUrls.value.splice(i, 1); if (activeIndex.value >= selectedFiles.value.length) activeIndex.value = Math.max(0, selectedFiles.value.length - 1) }
function clearFiles() { selectedFiles.value = []; thumbUrls.value = []; batchResult.value = null; activeIndex.value = 0; error.value = '' }

async function runInference() {
  if (!canRun.value) return
  running.value = true; error.value = ''; batchResult.value = null; processedCount.value = 0
  activeHistoryId.value = null
  // 分批跑，每批 5 张
  const batchSize = 5
  const allResults = []
  const batchName = buildBatchName(selectedFiles.value)
  for (let i = 0; i < selectedFiles.value.length; i += batchSize) {
    const batch = selectedFiles.value.slice(i, i + batchSize)
    try {
      const res = await predict(modelId.value, batch, confidence.value, iou.value, batchName)
      allResults.push(...(res.results || []))
      processedCount.value = Math.min(i + batchSize, selectedFiles.value.length)
      batchResult.value = { ...res, batch_name: batchName, results: [...allResults] }
      if (!previewSrc.value && res.results?.[0]?.prediction_image_url) {
        previewSrc.value = res.results[0].prediction_image_url
      }
    } catch (e) {
      error.value = e?.message || '推理失败'
      break
    }
  }
  running.value = false
  if (allResults.length) loadHistory()
}

async function loadHistoryResult(h) {
  activeHistoryId.value = h.session_id
  batchResult.value = h
  activeIndex.value = 0
  previewSrc.value = h?.results?.[0]?.prediction_image_url || ''
}

async function runDatasetInference() {
  if (!datasetVersionId.value || !modelId.value) return
  running.value = true; error.value = ''; datasetResult.value = null
  try {
    const data = await listImages({ versionId: datasetVersionId.value, pageSize: 200 })
    const imageItems = data.items || []
    if (!imageItems.length) { error.value = '该数据集没有图片'; running.value = false; return }
    const blobs = []
    for (const item of imageItems) {
      const imgUrl = datasetImageUrl(item.image_path)
      if (!imgUrl) continue
      const r = await fetch(imgUrl)
      if (r.ok) {
        const blob = await r.blob()
        const file = new File([blob], item.image_path.split(/[\\/]/).pop(), { type: blob.type })
        blobs.push(file)
      }
    }
    if (!blobs.length) { error.value = '无法加载图片'; running.value = false; return }
    const res = await predict(modelId.value, blobs.slice(0, 50), confidence.value, iou.value)
    res.total_boxes = (res.results || []).reduce((s, r) => s + (r.box_count || 0), 0)
    datasetResult.value = res
  } catch (e) { error.value = e?.message || '推理失败' }
  running.value = false
}

async function loadHistory() {
  try { history.value = await listHistory(20) || [] } catch {}
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
  const idx = normalized.indexOf(marker)
  if (idx >= 0) return '/images/' + normalized.slice(idx + marker.length)
  const simpleIdx = normalized.indexOf('datasets/')
  if (simpleIdx >= 0) return '/images/' + normalized.slice(simpleIdx + 'datasets/'.length)
  return ''
}
</script>
