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
          <span><span class="dot prelabel"></span>AI预标 {{ annotationProgress.ai_prelabel }}</span>
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
      </div>

      <div class="filter-row">
        <span :class="['filter', { active: filter === '' }]" @click="setFilter('')">全部</span>
        <span :class="['filter', { active: filter === 'unlabeled' }]" @click="setFilter('unlabeled')">未标注</span>
        <span :class="['filter', { active: filter === 'ai_prelabel' }]" @click="setFilter('ai_prelabel')">AI 预标注</span>
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
        <button :class="{ active: mode === 'select' }" @click="mode = 'select'">选择</button>
        <button :class="{ active: mode === 'draw' }" @click="mode = 'draw'">画框</button>
        <button :class="{ active: mode === 'delete' }" @click="mode = 'delete'">删除</button>
        <span class="toolbar-sep"></span>
        <button @click="canvasRef?.fitToScreen()">适应屏幕</button>
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
        A/D 上一张/下一张 · B 画框 · V 选择 · Delete 删除 · 共 {{ images.length }} 张
      </div>
    </div>

    <div class="annotation-inspector">
      <!-- 类别管理 -->
      <div class="class-manager">
        <div class="class-manager-header">
          <strong>类别管理</strong>
          <span class="muted-text">{{ classes.length }} 类</span>
        </div>
        <div class="class-chips">
          <button
            v-for="(name, idx) in classes"
            :key="idx"
            :class="['class-chip-btn', { active: idx === drawClassId }]"
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
        <button class="primary-action full" @click="doSave" :disabled="saving || !currentImageId">
          {{ saving ? '保存中...' : '保存' }}
        </button>
        <button class="secondary-action full" @click="doPrelabel" :disabled="prelabeling || !currentImageId">
          {{ prelabeling ? 'AI 推理中...' : 'AI 预标注' }}
        </button>
        <button class="secondary-action full" @click="doMarkReviewed" :disabled="!currentImageId">标记已复核</button>
      </div>
      <p v-if="actionMsg" :class="actionOk ? 'action-msg' : 'error'">{{ actionMsg }}</p>
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
import { getAnnotation, prelabel, updateAnnotation } from '../api/annotations.js'
import { setActiveDatasetContext } from '../state/workspaceContext.js'

const COLORS = ['#D4783C', '#3e7b59', '#667ea2', '#b65246', '#7c5ce0', '#0f8b8d', '#5b8def', '#9b6b3f']

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

const currentImageUrl = computed(() => currentImage.value ? imageUrl(currentImage.value.image_path) : '')
const currentImageStatus = computed(() => currentImage.value?.annotation_status || 'unlabeled')

onMounted(async () => {
  try {
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
    const result = await listImages(selectedVersionId.value, { status: filter.value || undefined, pageSize: 500 })
    images.value = result.items || []
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
  nextTick(() => canvasRef.value?.fitToScreen())
}

function onBoxSelect(index) {
  selectedBoxIndex.value = index
}

function onBoxCreate(box) {
  const clsId = drawClassId.value >= 0 ? drawClassId.value : 0
  currentBoxes.value = [...currentBoxes.value, { ...box, class_id: clsId }]
  selectedBoxIndex.value = currentBoxes.value.length - 1
  mode.value = 'select'
}

function onBoxUpdate({ index, box }) {
  const next = [...currentBoxes.value]
  next[index] = box
  currentBoxes.value = next
}

function onBoxDelete(index) {
  currentBoxes.value = currentBoxes.value.filter((_, i) => i !== index)
  selectedBoxIndex.value = -1
}

async function doSave() {
  if (!currentImageId.value) return
  saving.value = true
  try {
    const result = await updateAnnotation(currentImageId.value, currentBoxes.value, 'reviewed')
    currentImage.value = { ...currentImage.value, annotation_status: result.status }
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
  prelabeling.value = true
  try {
    const result = await prelabel(currentImageId.value, 'yolo11n.pt', 0.25)
    currentBoxes.value = result.boxes || []
    currentImage.value = { ...currentImage.value, annotation_status: result.status }
    showAction('AI 预标注完成', true)
  } catch (err) {
    showAction('AI 预标注失败：' + err.message, false)
  } finally {
    prelabeling.value = false
  }
}

async function doMarkReviewed() {
  if (!currentImageId.value) return
  try {
    await updateAnnotation(currentImageId.value, currentBoxes.value, 'reviewed')
    currentImage.value = { ...currentImage.value, annotation_status: 'reviewed' }
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
  if (!confirm(`确认删除类别「${name}」？已有标注框的 class_id 会受影响。`)) return
  const updated = classes.value.filter((_, i) => i !== idx)
  try {
    await updateClassConfig(selectedVersionId.value, { class_text: updated.join('\n') })
    classes.value = updated
    if (drawClassId.value >= updated.length) drawClassId.value = Math.max(0, updated.length - 1)
    showAction(`已删除类别「${name}」`, true)
  } catch (err) {
    showAction('删除失败：' + err.message, false)
  }
}

function showAction(message, ok) {
  actionMsg.value = message
  actionOk.value = ok
  setTimeout(() => {
    actionMsg.value = ''
  }, 2200)
}

function navigateImage(dir) {
  const index = images.value.findIndex(item => item.id === currentImageId.value)
  const next = images.value[index + dir]
  if (next) selectImage(next)
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
    ai_prelabel: 'AI 预标注',
  }[status] || status || '未标注'
}

function classColor(classId) {
  return COLORS[classId % COLORS.length]
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
.dot-ai_prelabel { background: #D4783C; }
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
</style>
