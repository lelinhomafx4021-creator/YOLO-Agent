<template>
  <section v-if="!selectedVersionId" class="page">
    <div class="page-header">
      <div>
        <h1>标注工作台</h1>
        <p>先选择一个待标注图集，再进入逐张标注。类别配置来自该图集自己的 <code>data.yaml</code>。</p>
      </div>
      <div class="header-actions">
        <RouterLink class="primary-action" to="/datasets">去数据页选择图集</RouterLink>
      </div>
    </div>

    <section class="card annotation-empty">
      <strong>选择一个图集</strong>
      <span>选择一个已导入的图集版本开始标注，或前往数据页导入新的数据集。</span>
    </section>

    <div v-if="versions.length === 0" class="loading">暂无可用图集，请先导入数据。</div>
    <div v-else class="dataset-card-grid">
      <div
        v-for="version in versions"
        :key="version.id"
        class="dataset-card"
        :class="'dsc-dtype--' + (version.dtype || 'none')"
        @click="selectVersion(version)"
        style="cursor:pointer"
      >
        <div class="dsc-accent-bar"></div>
        <div class="dsc-head">
          <div class="dsc-title-row">
            <strong class="dsc-name">{{ version.dataset_name }}</strong>
            <div class="dsc-meta">
              <span class="version-chip">{{ version.version }}</span>
              <ChipBadge :tone="versionStatusTone(version.status)">{{
                versionStatusLabel(version.status)
              }}</ChipBadge>
            </div>
          </div>
        </div>
        <div class="dsc-stats">
          <div class="dsc-stat">
            <span class="dsc-stat-label">图像总数</span>
            <b class="dsc-stat-value">{{ version.image_count?.toLocaleString() }}</b>
          </div>
          <div class="dsc-stat">
            <span class="dsc-stat-label">类别数</span>
            <b class="dsc-stat-value">{{ version.class_count || 0 }}</b>
          </div>
          <div class="dsc-stat">
            <span class="dsc-stat-label">标签总数</span>
            <b class="dsc-stat-value">{{ (version.instance_count || version.label_file_count || 0)?.toLocaleString() }}</b>
          </div>
          <div class="dsc-stat">
            <span class="dsc-stat-label">含框图像</span>
            <b class="dsc-stat-value">{{ version.label_file_count || 0 }}</b>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section v-else class="annotation-page">
    <!-- 顶部栏 -->
    <div class="annotation-topbar">
      <button class="secondary-action small-action" @click="selectedVersionId = null">← 返回列表</button>
      <select v-model.number="selectedVersionId" @change="loadImages" class="topbar-version-select">
        <option v-for="ver in versions" :key="ver.id" :value="ver.id">
          {{ ver.dataset_name }} / {{ ver.version }}
        </option>
      </select>
      <span class="muted-text" style="font-size:11px">
        共 {{ images.length }} 张 ·
        已复核 {{ annotationProgress?.reviewed || 0 }} ·
        待标注 {{ annotationProgress?.unlabeled || 0 }}
      </span>
      <span v-if="hasUnsavedChanges" class="unsaved-indicator">未保存</span>
      <button class="secondary-action small-action" style="margin-left:auto" @click="askAgent">
        问 Agent
      </button>
    </div>

    <div class="annotation-list">
      <h2>图片列表</h2>

      <!-- 标注进度面板 -->
      <div v-if="annotationProgress" class="progress-panel">
        <div class="progress-header">
          <span>标注进度</span>
          <strong>{{ annotationProgress.annotated }}/{{ annotationProgress.total }}</strong>
        </div>
        <div class="progress-bar-wrap">
          <div class="progress-bar-seg reviewed" :style="{ width: pct(annotationProgress.reviewed) + '%' }"></div>
          <div class="progress-bar-seg prelabel" :style="{ width: pct(annotationProgress.ai_prelabel) + '%' }"></div>
          <div class="progress-bar-seg unlabeled" :style="{ width: pct(annotationProgress.unlabeled) + '%' }"></div>
        </div>
        <div class="progress-legend">
          <span><span class="dot reviewed"></span>已复核 {{ annotationProgress.reviewed }}</span>
          <span><span class="dot prelabel"></span>模型预标 {{ annotationProgress.ai_prelabel }}</span>
          <span><span class="dot unlabeled"></span>未标注 {{ annotationProgress.unlabeled }}</span>
        </div>
        <button
          v-if="annotationProgress.next_unlabeled_image_id"
          class="secondary-action small-action"
          style="margin-top:6px;width:100%"
          @click="jumpToNextUnlabeled"
        >
          → 跳转到下一张未标注
        </button>
        <button
          class="secondary-action small-action"
          style="margin-top:6px;width:100%"
          :disabled="prelabeling || !annotationProgress.unlabeled && !annotationProgress.ai_prelabel"
          title="对当前图集所有未复核图片执行模型预标注，已复核图片不会被覆盖"
          @click="doBatchPrelabel"
        >
          批量模型预标注
        </button>
      </div>

      <div class="filter-row">
        <span :class="['filter', { active: filter === '' }]" @click="setFilter('')">全部</span>
        <span :class="['filter', { active: filter === 'unlabeled' }]" @click="setFilter('unlabeled')">未标注</span>
        <span :class="['filter', { active: filter === 'ai_prelabel' }]" @click="setFilter('ai_prelabel')">模型预标注</span>
        <span :class="['filter', { active: filter === 'reviewed' }]" @click="setFilter('reviewed')">已复核</span>
      </div>

      <div v-if="imageLoading" class="loading">正在加载图片...</div>
      <button
        v-for="item in images"
        :key="item.id"
        :class="['image-item', { active: item.id === currentImageId }]"
        @click="selectImage(item)"
      >
        <div class="thumb" :style="thumbStyle(item)">
          <span class="thumb-status-dot" :class="'dot-' + (item.annotation_status || 'unlabeled')"></span>
        </div>
        <div>
          <strong>{{ basename(item.image_path) }}</strong>
          <span>{{ statusLabel(item.annotation_status) }}</span>
        </div>
      </button>
      <div v-if="images.length === 0 && !imageLoading" class="loading">这个图集下暂时没有图片。</div>
    </div>

    <div class="annotation-canvas-area">
      <div v-if="classWarning" class="class-warning">{{ classWarning }}</div>
      <div class="canvas-toolbar">
        <button :class="{ active: mode === 'select' }" title="快捷键 V：选择、移动或调整已有标注框" @click="mode = 'select'">选择 V</button>
        <button :class="{ active: mode === 'draw' }" title="快捷键 B：进入画框模式，拖拽图片区域创建标注框" @click="mode = 'draw'">画框 B</button>
        <button :class="{ active: mode === 'delete' }" title="快捷键 Delete / Backspace：删除选中的标注框" @click="mode = 'delete'">删除 Del</button>
        <span class="toolbar-sep"></span>
        <button title="将当前图片缩放到画布可视范围" @click="canvasRef?.fitToScreen()">适应屏幕</button>
        <button :class="{ active: !showBoxes }" @click="showBoxes = !showBoxes" :title="showBoxes ? '点击隐藏标注框查看原图' : '点击显示标注框'">
          {{ showBoxes ? '隐藏框' : '显示框' }}
        </button>
        <span class="toolbar-spacer"></span>
        <span v-if="classes.length && drawClassId >= 0" class="current-class-badge" :style="{ background: classColor(drawClassId) }">
          当前: {{ classes[drawClassId] || '?' }}
        </span>
        <span v-else class="current-class-badge" style="background:var(--muted-2)">
          请先在右侧添加类别
        </span>
      </div>

      <AnnotationCanvas
        ref="canvasRef"
        :imageUrl="currentImageUrl"
        :boxes="showBoxes ? currentBoxes : []"
        :classes="classes"
        :selectedBoxIndex="selectedBoxIndex"
        :mode="mode"
        @box-select="onBoxSelect"
        @box-create="onBoxCreate"
        @box-update="onBoxUpdate"
        @box-delete="onBoxDelete"
      />

      <div class="canvas-status">
        <span><kbd>A</kbd>/<kbd>D</kbd> 上/下一张</span>
        <span><kbd>B</kbd> 画框</span>
        <span><kbd>V</kbd> 选择</span>
        <span><kbd>S</kbd> 保存</span>
        <span><kbd>Del</kbd> 删除框</span>
        <span><kbd>1-0</kbd> 切换类别</span>
        <span>共 {{ images.length }} 张</span>
      </div>
    </div>

    <div class="annotation-inspector">
      <!-- 类别管理 -->
      <div class="class-manager">
        <div class="class-manager-header">
          <strong>类别管理</strong>
          <span class="muted-text">{{ classes.length }} 类</span>
        </div>
        <div class="class-shortcut-hint">
          数字键 <kbd>1</kbd>-<kbd>0</kbd> 快速切换前 10 个类别；选中类别后新画的框会使用该类别。
        </div>
        <div class="class-chips">
          <button
            v-for="(name, idx) in classes"
            :key="idx"
            :class="['class-chip-btn', { active: idx === drawClassId }]"
            :title="idx <= 9 ? `快捷键 ${classShortcutKey(idx)}：切换到 ${name}` : `切换到 ${name}`"
            @click="drawClassId = idx"
          >
            <span class="class-chip-color" :style="{ background: classColor(idx) }"></span>
            <span class="class-chip-name">{{ name }}</span>
            <span class="class-chip-del" @click.stop="removeClass(idx)" title="删除此类别">×</span>
          </button>
        </div>
        <div class="class-add-row">
          <input
            v-model="newClassName"
            placeholder="新类别名称，回车添加"
            @keyup.enter="confirmAddClass"
            class="class-add-input"
          />
          <button
            class="primary-action small-action"
            :disabled="!newClassName.trim()"
            @click="confirmAddClass"
          >添加</button>
        </div>
      </div>

      <!-- 当前图片 -->
      <div class="current-image-status">
        <ChipBadge :tone="currentImageStatus === 'reviewed' ? 'success' : 'warning'">
          {{ statusLabel(currentImageStatus) }}
        </ChipBadge>
        <span class="muted-text" style="font-size:10px">{{ basename(currentImage?.image_path || '') }}</span>
      </div>

      <!-- 标注框列表 -->
      <div class="box-section">
        <div class="box-section-header">
          <strong>标注框</strong>
          <span class="muted-text">{{ currentBoxes.length }} 个</span>
        </div>
        <div class="box-list">
        <button
          v-for="(box, i) in currentBoxes"
          :key="i"
          :class="['box-item', { active: i === selectedBoxIndex }]"
          @click="onBoxSelect(i)"
        >
          <span class="box-color" :style="{ background: classColor(box.class_id) }"></span>
          <span>{{ classes[box.class_id] || 'class_' + box.class_id }}</span>
          <span v-if="box.confidence != null" class="box-conf">{{ box.confidence.toFixed(2) }}</span>
        </button>
        <div v-if="currentBoxes.length === 0" class="loading">暂无标注框</div>
        </div>
      </div>

      <div v-if="selectedBoxIndex >= 0 && currentBoxes[selectedBoxIndex]" class="coord-grid">
        <InfoItem label="class_id" :value="currentBoxes[selectedBoxIndex].class_id" />
        <InfoItem label="x_center" :value="currentBoxes[selectedBoxIndex].x_center.toFixed(4)" />
        <InfoItem label="y_center" :value="currentBoxes[selectedBoxIndex].y_center.toFixed(4)" />
        <InfoItem label="width" :value="currentBoxes[selectedBoxIndex].width.toFixed(4)" />
        <InfoItem label="height" :value="currentBoxes[selectedBoxIndex].height.toFixed(4)" />
      </div>

      <div class="inspector-actions">
        <button class="primary-action full" title="快捷键 S：保存当前图片标注并标记为已复核" @click="doSave" :disabled="saving || !currentImageId">
          {{ saving ? '保存中...' : '保存' }}
        </button>
        <button class="secondary-action full" title="使用 YOLO 模型预标注，提交前需要确认类别映射" @click="doPrelabel" :disabled="prelabeling || !currentImageId">
          {{ prelabeling ? '模型推理中...' : '模型预标注' }}
        </button>
        <button class="secondary-action full" title="不改变当前框内容，仅将当前图片标记为已复核" @click="doMarkReviewed" :disabled="!currentImageId">标记已复核</button>
      </div>
      <p v-if="actionMsg" :class="actionOk ? 'action-msg' : 'error'">{{ actionMsg }}</p>
    </div>

    <div v-if="showPrelabelMapping" class="dialog-overlay" @click.self="closePrelabelMapping">
      <div class="dialog prelabel-map-dialog">
        <h3>{{ prelabelMode === 'batch' ? '确认批量模型预标注类别映射' : '确认模型预标注类别映射' }}</h3>
        <p class="helper-text">
          模型类别需要映射到当前图集类别。未映射的模型类别会被忽略，不会写入标签文件。
          <template v-if="prelabelMode === 'batch'">批量预标注只处理未复核图片。</template>
        </p>
        <div class="prelabel-map-toolbar">
          <label>模型
            <select v-model="prelabelModelPath" @change="clearLoadedModelClasses">
              <optgroup label="官方 COCO 模型">
                <option value="yolo11n.pt">YOLO11n (nano, 最快)</option>
                <option value="yolo11s.pt">YOLO11s (small)</option>
                <option value="yolov8n.pt">YOLOv8n (nano)</option>
              </optgroup>
              <optgroup v-if="prelabelModelOptions.length" label="已训练产出模型">
                <option
                  v-for="model in prelabelModelOptions"
                  :key="model.id"
                  :value="model.best_pt_path || model.last_pt_path"
                >
                  {{ prelabelModelLabel(model) }}
                </option>
              </optgroup>
            </select>
          </label>
          <label>置信度
            <input v-model.number="prelabelConf" type="number" min="0.05" max="0.95" step="0.05" />
          </label>
          <button class="secondary-action small-action" :disabled="loadingModelClasses" @click="loadModelClassOptions">
            {{ loadingModelClasses ? '加载中...' : '加载类别' }}
          </button>
        </div>
        <div v-if="modelClasses.length" class="prelabel-map-list">
          <div v-for="(name, idx) in modelClasses" :key="idx" class="prelabel-map-row">
            <span class="model-class-name">#{{ idx }} {{ name }}</span>
            <select v-model="prelabelMapping[idx]">
              <option value="">忽略</option>
              <option v-for="(cls, cidx) in classes" :key="cidx" :value="String(cidx)">
                #{{ cidx }} {{ cls }}
              </option>
            </select>
          </div>
        </div>
        <div v-else class="loading">请先加载模型类别。</div>
        <p v-if="prelabelMapError" class="error">{{ prelabelMapError }}</p>
        <div class="dialog-actions">
          <button class="secondary-action" @click="closePrelabelMapping">取消</button>
          <button class="primary-action" :disabled="prelabeling" @click="submitPrelabelMapping">
            {{ prelabeling ? '模型推理中...' : prelabelMode === 'batch' ? '确认批量预标注' : '确认预标注' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AnnotationCanvas from '../components/AnnotationCanvas.vue'
import ChipBadge from '../components/ChipBadge.vue'
import InfoItem from '../components/InfoItem.vue'
import { useAnnotationKeyboard } from '../composables/useAnnotationKeyboard.js'
import { getAnnotationProgress, getClassConfig, listImages, listVersions, updateClassConfig } from '../api/datasets.js'
import { batchPrelabel, getAnnotation, getModelClasses, prelabel, updateAnnotation } from '../api/annotations.js'
import { listModels } from '../api/models.js'
import { setActiveDatasetContext } from '../state/workspaceContext.js'

const COLORS = ['#E47630', '#3e7b59', '#667ea2', '#b65246', '#7c5ce0', '#0f8b8d', '#5b8def', '#9b6b3f']

const route = useRoute()
const router = useRouter()
const versions = ref([])
const selectedVersionId = ref(null)
const filter = ref('')
const imageLoading = ref(false)
const images = ref([])
const classes = ref([])
const classWarning = ref('')
const currentImageId = ref(null)
const currentImage = ref(null)
const currentBoxes = ref([])
const selectedBoxIndex = ref(-1)
const mode = ref('select')
const drawClassId = ref(0)
const saving = ref(false)
const prelabeling = ref(false)
const actionMsg = ref('')
const actionOk = ref(false)
const canvasRef = ref(null)
const newClassName = ref('')
const annotationProgress = ref(null)
const showBoxes = ref(true)
const showPrelabelMapping = ref(false)
const modelClasses = ref([])
const loadingModelClasses = ref(false)
const prelabelModelPath = ref('yolo11n.pt')
const prelabelConf = ref(0.25)
const prelabelMapping = ref({})
const prelabelMapError = ref('')
const prelabelMode = ref('single')
const prelabelModelOptions = ref([])
const hasUnsavedChanges = ref(false)

const currentImageUrl = computed(() => currentImage.value ? imageUrl(currentImage.value.image_path) : '')
const currentImageStatus = computed(() => currentImage.value?.annotation_status || 'unlabeled')

onMounted(async () => {
  try {
    loadPrelabelModelOptions()
    const all = (await listVersions()).items
    // 标注工作台只显示需要标注的数据集：
    //   annotation → 专门创建的标注图集
    //   test 无标注 → 上传的纯图片（原 predict）
    //   未分类 + 有待标注图片 → 导入后还未全部标完
    // 已完成的 train/val/test 不进入标注工作台
    versions.value = all.filter(v => {
      const dt = (v.dtype || '').trim()
      if (dt === 'annotation') return true
      if (dt === 'test' && Number(v.label_file_count || 0) === 0) return true
      if (!dt && Number(v.pending_count || 0) > 0) return true
      return false
    })
    const routeVersion = Number(route.query.version)
    const routeImage = Number(route.query.image)
    if (routeVersion) {
      selectedVersionId.value = routeVersion
      await loadImages(routeImage || null)
    }
  } catch (err) {
    console.error('标注工作台加载失败:', err)
    // auth 错误由 client.js 的全局事件处理，这里静默即可
  }
})

async function loadPrelabelModelOptions() {
  try {
    const result = await listModels(1, 200)
    prelabelModelOptions.value = (result.items || []).filter(model => {
      const format = String(model.model_format || 'YOLO').toUpperCase()
      return (!format || format === 'YOLO') && (model.best_pt_path || model.last_pt_path)
    })
  } catch {
    prelabelModelOptions.value = []
  }
}

function selectVersion(version) {
  const id = Number(version.id)
  router.push({ path: '/annotation', query: { version: id } })
  selectedVersionId.value = id
  loadImages()
}

function versionStatusTone(status) {
  return {
    imported: 'info',
    completed: 'success',
    failed: 'danger',
    running: 'warning',
  }[status] || 'info'
}

function versionStatusLabel(status) {
  return {
    imported: '已导入',
    completed: '已完成',
    failed: '已失败',
    running: '进行中',
  }[status] || status || '已导入'
}

async function loadImages(targetImageId = null) {
  if (!selectedVersionId.value) return
  imageLoading.value = true
  try {
    const version = versions.value.find(v => Number(v.id) === Number(selectedVersionId.value))
    if (version) {
      setActiveDatasetContext({
        datasetId: version.dataset_id,
        versionId: version.id,
        datasetName: version.dataset_name,
        version: version.version,
      })
    }
    await loadClasses()
    // 加载标注进度
    try {
      annotationProgress.value = await getAnnotationProgress(selectedVersionId.value)
    } catch { annotationProgress.value = null }
    images.value = await loadAllImages(filter.value || undefined)
    const target = targetImageId ? images.value.find(item => Number(item.id) === Number(targetImageId)) : null
    if (target) await selectImage(target)
    else if (images.value[0]) await selectImage(images.value[0])
    else {
      currentImage.value = null
      currentImageId.value = null
      currentBoxes.value = []
    }
  } finally {
    imageLoading.value = false
  }
}

async function loadAllImages(status = undefined) {
  const pageSize = 500
  let page = 1
  let total = 0
  const all = []
  do {
    const result = await listImages(selectedVersionId.value, { status, page, pageSize })
    const items = result.items || []
    all.push(...items)
    total = Number(result.total || all.length)
    page += 1
    if (!items.length) break
  } while (all.length < total)
  return all
}

function pct(count) {
  if (!annotationProgress.value?.total) return 0
  return Math.round((count / annotationProgress.value.total) * 100)
}

async function jumpToNextUnlabeled() {
  if (!annotationProgress.value?.next_unlabeled_image_id) return
  // 先切换到全部视图，确保能找到该图片
  filter.value = ''
  await loadImages(annotationProgress.value.next_unlabeled_image_id)
}

async function loadClasses() {
  classWarning.value = ''
  try {
    const config = await getClassConfig(selectedVersionId.value)
    if (config.class_names?.length) {
      const names = config.class_names
      const nonDefault = names.filter(
        (n) => n !== 'class_0' && !/^class_\d+$/.test(n),
      )
      classes.value = names
      if (nonDefault.length === 0) {
        classWarning.value = '尚未配置类别。请在右侧面板中添加至少一个类别名称，然后开始标注。'
      }
    } else {
      classes.value = []
      classWarning.value = '尚未配置类别。请在右侧面板中添加至少一个类别名称，然后开始标注。'
    }
  } catch {
    classes.value = []
    classWarning.value = '无法加载类别配置。请在右侧面板中手动添加类别。'
  }
  if (classes.value.length === 0) drawClassId.value = -1
  else if (drawClassId.value >= classes.value.length) drawClassId.value = 0
}

function setFilter(value) {
  filter.value = value
  loadImages()
}

async function selectImage(item) {
  if (!(await confirmDiscardUnsaved())) return
  currentImageId.value = item.id
  currentImage.value = item
  selectedBoxIndex.value = -1
  actionMsg.value = ''
  try {
    const result = await getAnnotation(item.id)
    currentBoxes.value = result.boxes || []
    currentImage.value = result.image || item
  } catch {
    currentBoxes.value = []
  }
  hasUnsavedChanges.value = false
  nextTick(() => canvasRef.value?.fitToScreen())
}

function onBoxSelect(index) {
  selectedBoxIndex.value = index
}

function onBoxCreate(box) {
  const clsId = drawClassId.value >= 0 ? drawClassId.value : 0
  currentBoxes.value = [...currentBoxes.value, { ...box, class_id: clsId }]
  selectedBoxIndex.value = currentBoxes.value.length - 1
  hasUnsavedChanges.value = true
  mode.value = 'select'
}

function onBoxUpdate({ index, box }) {
  const next = [...currentBoxes.value]
  next[index] = box
  currentBoxes.value = next
  hasUnsavedChanges.value = true
}

function onBoxDelete(index) {
  currentBoxes.value = currentBoxes.value.filter((_, i) => i !== index)
  selectedBoxIndex.value = -1
  hasUnsavedChanges.value = true
}

async function doSave() {
  if (!currentImageId.value) return
  saving.value = true
  try {
    const result = await updateAnnotation(currentImageId.value, currentBoxes.value, 'reviewed')
    setImageStatus(currentImageId.value, result.status)
    hasUnsavedChanges.value = false
    await refreshAnnotationProgress()
    showAction('已保存', true)
  } catch (err) {
    showAction('保存失败：' + err.message, false)
  } finally {
    saving.value = false
  }
}

function askAgent() {
  const version = versions.value.find(v => v.id === selectedVersionId.value)
  const name = version ? `${version.dataset_name}/${version.version}` : '当前图集'
  const q = `分析标注图集 ${name} 的质量和进度，哪些图片需要优先复核？`
  router.push({ path: '/agent', query: { q } })
}

async function doPrelabel() {
  if (!currentImageId.value) return
  if (!classes.value.length) {
    showAction('请先配置图集类别，再进行模型预标注', false)
    return
  }
  if (currentImageStatus.value === 'reviewed') {
    showAction('已复核图片不会被模型预标注覆盖', false)
    return
  }
  prelabelMode.value = 'single'
  showPrelabelMapping.value = true
  if (!modelClasses.value.length) await loadModelClassOptions()
}

async function doBatchPrelabel() {
  if (!selectedVersionId.value) return
  if (!classes.value.length) {
    showAction('请先配置图集类别，再进行批量模型预标注', false)
    return
  }
  if (!(await confirmDiscardUnsaved())) return
  hasUnsavedChanges.value = false
  prelabelMode.value = 'batch'
  showPrelabelMapping.value = true
  if (!modelClasses.value.length) await loadModelClassOptions()
}

async function loadModelClassOptions() {
  loadingModelClasses.value = true
  prelabelMapError.value = ''
  try {
    const result = await getModelClasses(prelabelModelPath.value || 'yolo11n.pt')
    modelClasses.value = result.classes || []
    prelabelMapping.value = suggestClassMapping(modelClasses.value, classes.value)
  } catch (err) {
    prelabelMapError.value = '模型类别加载失败：' + err.message
  } finally {
    loadingModelClasses.value = false
  }
}

function clearLoadedModelClasses() {
  modelClasses.value = []
  prelabelMapping.value = {}
  prelabelMapError.value = ''
}

function prelabelModelLabel(model) {
  const name = model.display_model_name || model.model_name || model.run_id || model.dataset_name || '已训练模型'
  const score = model.map50 != null ? ` · mAP50 ${Number(model.map50).toFixed(3)}` : ''
  return `${name}${score}`
}

function suggestClassMapping(modelNames, datasetNames) {
  const mapping = {}
  modelNames.forEach((modelName, idx) => {
    const normalizedModel = normalizeClassName(modelName)
    const hit = datasetNames.findIndex(name => {
      const normalizedDataset = normalizeClassName(name)
      return normalizedModel && (
        normalizedModel === normalizedDataset ||
        normalizedModel.includes(normalizedDataset) ||
        normalizedDataset.includes(normalizedModel)
      )
    })
    if (hit >= 0) mapping[idx] = String(hit)
  })
  return mapping
}

function normalizeClassName(name) {
  return String(name || '').toLowerCase().replace(/[\s_-]/g, '')
}

function selectedPrelabelMapping() {
  const mapping = {}
  Object.entries(prelabelMapping.value || {}).forEach(([modelId, datasetId]) => {
    if (datasetId !== '' && datasetId != null) mapping[modelId] = Number(datasetId)
  })
  return mapping
}

function closePrelabelMapping() {
  if (prelabeling.value) return
  showPrelabelMapping.value = false
  prelabelMapError.value = ''
}

async function submitPrelabelMapping() {
  if (prelabelMode.value === 'single' && !currentImageId.value) return
  const mapping = selectedPrelabelMapping()
  if (!Object.keys(mapping).length) {
    prelabelMapError.value = '请至少选择一个模型类别到图集类别的映射'
    return
  }
  prelabeling.value = true
  try {
    const modelPath = prelabelModelPath.value || 'yolo11n.pt'
    const conf = prelabelConf.value || 0.25
    let result
    if (prelabelMode.value === 'batch') {
      result = await batchPrelabel(selectedVersionId.value, modelPath, conf, mapping, false, true)
      await refreshAnnotationProgress()
      const activeId = currentImageId.value
      await loadImages(activeId)
      showAction(`批量模型预标注完成：成功 ${result.success || 0} 张，失败 ${result.failed || 0} 张，保留 ${result.mapped_count || 0} 个框`, true)
    } else {
      result = await prelabel(currentImageId.value, modelPath, conf, mapping, true)
      currentBoxes.value = result.boxes || []
      setImageStatus(currentImageId.value, result.status)
      await refreshAnnotationProgress()
      showAction(`模型预标注完成：保留 ${result.mapped_count || 0} 个，忽略 ${result.dropped_count || 0} 个`, true)
    }
    hasUnsavedChanges.value = false
    showPrelabelMapping.value = false
  } catch (err) {
    prelabelMapError.value = '模型预标注失败：' + err.message
    showAction('模型预标注失败：' + err.message, false)
  } finally {
    prelabeling.value = false
  }
}

async function doMarkReviewed() {
  if (!currentImageId.value) return
  try {
    await updateAnnotation(currentImageId.value, currentBoxes.value, 'reviewed')
    setImageStatus(currentImageId.value, 'reviewed')
    hasUnsavedChanges.value = false
    await refreshAnnotationProgress()
    showAction('已标记为复核', true)
  } catch (err) {
    showAction('操作失败：' + err.message, false)
  }
}

async function confirmAddClass() {
  const name = newClassName.value.trim()
  if (!name) return
  // 检查重复
  if (classes.value.includes(name)) {
    showAction(`类别「${name}」已存在`, false)
    return
  }
  const updated = [...classes.value, name]
  try {
    await updateClassConfig(selectedVersionId.value, { class_text: updated.join('\n') })
    classes.value = updated
    drawClassId.value = updated.length - 1
    newClassName.value = ''
    showAction(`已添加类别「${name}」`, true)
  } catch (err) {
    showAction('添加失败：' + err.message, false)
  }
}

async function removeClass(idx) {
  const name = classes.value[idx]
  showAction(`类别「${name}」不能直接删除；为避免 class_id 变义，请通过后续重映射工具处理`, false)
}

function showAction(message, ok) {
  actionMsg.value = message
  actionOk.value = ok
  setTimeout(() => {
    actionMsg.value = ''
  }, 2200)
}

function setImageStatus(imageId, status) {
  currentImage.value = { ...currentImage.value, annotation_status: status }
  images.value = images.value.map(item => (
    Number(item.id) === Number(imageId) ? { ...item, annotation_status: status } : item
  ))
}

async function refreshAnnotationProgress() {
  try {
    annotationProgress.value = await getAnnotationProgress(selectedVersionId.value)
  } catch {}
}

async function confirmDiscardUnsaved() {
  if (!hasUnsavedChanges.value) return true
  return confirm('当前图片有未保存标注，切换图片会丢失这些修改。是否继续？')
}

async function navigateImage(dir) {
  const index = images.value.findIndex(item => item.id === currentImageId.value)
  const next = images.value[index + dir]
  if (next) await selectImage(next)
}

useAnnotationKeyboard({
  onPrevImage: () => navigateImage(-1),
  onNextImage: () => navigateImage(1),
  onSave: () => doSave(),
  onToggleMode: (nextMode) => { mode.value = nextMode },
  onSetClass: (id) => { if (id < classes.value.length) drawClassId.value = id },
  onDeleteBox: () => {
    if (selectedBoxIndex.value >= 0) onBoxDelete(selectedBoxIndex.value)
  },
  onDeselect: () => { selectedBoxIndex.value = -1 },
})

function imageUrl(path) {
  const normalized = String(path || '').replace(/\\/g, '/')
  const marker = '/datasets/'
  const idx = normalized.indexOf(marker)
  if (idx >= 0) return '/images/' + normalized.slice(idx + marker.length)
  const simpleIdx = normalized.indexOf('datasets/')
  if (simpleIdx >= 0) return '/images/' + normalized.slice(simpleIdx + 'datasets/'.length)
  return ''
}

function thumbStyle(item) {
  const url = imageUrl(item.image_path)
  return url ? { backgroundImage: `url("${url}")`, backgroundSize: 'cover', backgroundPosition: 'center' } : {}
}

function basename(path) {
  return String(path || '').replace(/\\/g, '/').split('/').pop()
}

function statusLabel(status) {
  return {
    unlabeled: '未标注',
    reviewed: '已复核',
    ai_prelabel: '模型预标注',
  }[status] || status || '未标注'
}

function classColor(classId) {
  return COLORS[classId % COLORS.length]
}

function classShortcutKey(classId) {
  return classId === 9 ? '0' : String(classId + 1)
}
</script>

<style scoped>
.class-warning {
  margin: 0 0 8px 0;
  padding: 10px 14px;
  background: #FFF3E0;
  border: 1px solid #FFB74D;
  border-radius: 8px;
  color: #C25E2E;
  font-size: 13px;
  line-height: 1.5;
}

/* 缩略图状态指示点 */
.thumb { position: relative; }
.thumb-status-dot {
  position: absolute; bottom: 2px; right: 2px;
  width: 8px; height: 8px; border-radius: 50%;
  border: 1.5px solid white;
  box-shadow: 0 0 0 1px rgba(0,0,0,0.2);
}
.dot-reviewed { background: #3e7b59; }
.dot-ai_prelabel { background: #E47630; }
.dot-unlabeled { background: #999; }

/* 顶部栏 */
.annotation-topbar {
  display: flex; align-items: center; gap: 10px;
  padding: 6px 12px; background: var(--card);
  border-bottom: 1px solid var(--line-soft);
}
.topbar-version-select {
  padding: 3px 8px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--line-soft); border-radius: 5px;
  background: var(--card); min-width: 200px;
}
.annotation-page {
  grid-template-rows: auto 1fr;
}
.annotation-page > .annotation-topbar {
  grid-column: 1 / -1;
}

/* ── 类别管理面板 ── */
.class-manager {
  padding-bottom: 8px; border-bottom: 1px solid var(--line-soft);
  margin-bottom: 4px;
}
.class-manager-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px;
}
.class-manager-header strong { font-size: 12px; }
.class-shortcut-hint {
  margin: -2px 0 7px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.4;
}
.class-chips {
  display: flex; flex-wrap: wrap; gap: 4px;
  max-height: 140px; overflow-y: auto; margin-bottom: 6px;
}
.class-chip-btn {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 6px; font-size: 11px;
  border: 1.5px solid var(--line-soft); border-radius: 6px;
  background: var(--card); cursor: pointer;
  transition: border-color 0.1s, background 0.1s;
}
.class-chip-btn:hover { border-color: var(--primary); }
.class-chip-btn.active {
  border-color: var(--primary); background: var(--primary-light);
  font-weight: 600;
}
.class-chip-color {
  width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0;
}
.class-chip-name {
  max-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.class-chip-del {
  font-size: 14px; color: var(--muted); line-height: 1; padding: 0 2px;
  opacity: 0; transition: opacity 0.1s;
}
.class-chip-btn:hover .class-chip-del { opacity: 1; }
.class-chip-del:hover { color: var(--danger, #D4556B); }
.class-add-row {
  display: flex; gap: 4px;
}
.class-add-input {
  flex: 1; padding: 4px 8px; font-size: 11px;
  border: 1px solid var(--line-soft); border-radius: 5px;
  background: var(--card);
}
.class-add-input:focus { border-color: var(--primary); outline: none; }

/* ── 当前图片状态 ── */
.current-image-status {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 0;
}

/* ── 标注框列表 ── */
.box-section { margin-top: 4px; }
.box-section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 4px;
}
.box-section-header strong { font-size: 12px; }

/* ── 操作按钮区 ── */
.inspector-actions {
  display: flex; flex-direction: column; gap: 4px;
  margin-top: auto; padding-top: 8px;
  border-top: 1px solid var(--line-soft);
}

/* ── Canvas 工具栏增强 ── */
.toolbar-sep {
  width: 1px; height: 20px; background: var(--line-soft);
}
.toolbar-spacer { flex: 1; }
.current-class-badge {
  padding: 3px 10px; font-size: 11px; font-weight: 600;
  color: #fff; border-radius: 5px; white-space: nowrap;
}
.canvas-status {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  align-items: center;
}
.canvas-status kbd,
.class-shortcut-hint kbd {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border: 1px solid var(--line-soft);
  border-bottom-color: var(--muted-2);
  border-radius: 4px;
  background: var(--card);
  color: var(--text);
  font-family: inherit;
  font-size: 10px;
  font-weight: 700;
}
.unsaved-indicator {
  padding: 2px 7px;
  border-radius: 5px;
  background: #FFF3E0;
  border: 1px solid #FFB74D;
  color: #C25E2E;
  font-size: 11px;
  font-weight: 600;
}

.prelabel-map-dialog {
  width: min(720px, calc(100vw - 32px));
  max-height: min(760px, calc(100vh - 48px));
  display: flex;
  flex-direction: column;
}
.prelabel-map-toolbar {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 100px auto;
  gap: 8px;
  align-items: end;
  margin-bottom: 10px;
}
.prelabel-map-toolbar label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
}
.prelabel-map-toolbar input,
.prelabel-map-toolbar select,
.prelabel-map-row select {
  border: 1px solid var(--line-soft);
  border-radius: 5px;
  background: var(--card);
  padding: 6px 8px;
  font-size: 12px;
}
.prelabel-map-list {
  overflow: auto;
  border: 1px solid var(--line-soft);
  border-radius: 6px;
  max-height: 430px;
}
.prelabel-map-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 10px;
  align-items: center;
  padding: 7px 10px;
  border-bottom: 1px solid var(--line-soft);
}
.prelabel-map-row:last-child { border-bottom: 0; }
.model-class-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
</style>
