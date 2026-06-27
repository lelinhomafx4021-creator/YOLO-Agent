<template>
  <section class="preview-shell">
    <div class="preview-topbar">
      <RouterLink class="secondary-action small-action" to="/datasets">← 返回</RouterLink>
      <strong>{{ version?.dataset_name }} {{ version?.version }}</strong>
      <span class="muted-text">{{ images.length }} 张 · {{ version?.class_count }} 类</span>
      <span v-if="annotationProgress" class="muted-text">
        已标注 {{ annotationProgress.annotated }}/{{ annotationProgress.total }}
      </span>
      <span class="muted-text" style="margin-left:auto">{{ currentIdx + 1 }} / {{ filteredImages.length }}</span>
      <RouterLink v-if="isAnnotationType" class="secondary-action small-action" :to="`/annotation?version=${route.params.id}`">标注 →</RouterLink>
    </div>

    <div class="preview-body">
      <!-- 左侧缩略图列表 -->
      <div class="preview-sidebar">
        <div class="preview-filter">
          <button :class="{ active: filter === '' }" @click="setFilter('')">全部</button>
          <button :class="{ active: filter === 'unlabeled' }" @click="setFilter('unlabeled')">未标注</button>
          <button :class="{ active: filter === 'reviewed' }" @click="setFilter('reviewed')">已标注</button>
        </div>
        <div class="preview-thumbs">
          <div
            v-for="(item, i) in filteredImages"
            :key="item.id"
            :class="['thumb-item', { active: item.id === currentId }]"
            @click="selectImage(item, i)"
          >
            <img :src="imageUrl(item.image_path)" loading="lazy" @error="onThumbError($event)" />
            <div class="thumb-label">{{ basename(item.image_path) }}</div>
            <span class="thumb-dot" :class="'dot-' + (item.annotation_status || 'unlabeled')"></span>
          </div>
          <div v-if="loading" class="empty-inline" style="padding:12px">加载中...</div>
          <div v-else-if="!filteredImages.length" class="empty-inline" style="padding:12px">暂无图片</div>
        </div>
      </div>

      <!-- 右侧大图 + 标注渲染 -->
      <div class="preview-stage" @click="nextImage">
        <div v-if="loading" class="preview-placeholder">加载中...</div>
        <div v-else-if="!currentImage" class="preview-placeholder">← 选择一张图片查看</div>
        <template v-else>
          <button class="stage-nav stage-prev" @click.stop="prevImage">‹</button>
          <div class="stage-center">
            <div class="stage-canvas-wrap">
              <img
                :src="imageUrl(currentImage.image_path)"
                class="stage-img"
                ref="stageImg"
                @load="drawBoxes"
                @error="onStageError"
              />
              <canvas ref="boxCanvas" class="stage-canvas"></canvas>
            </div>
            <div class="stage-info">
              <span>{{ basename(currentImage.image_path) }}</span>
              <span :class="['chip', currentImage.annotation_status === 'reviewed' ? 'success' : 'warning']">
                {{ currentImage.annotation_status === 'reviewed' ? '已标注' : '未标注' }}
              </span>
              <span v-if="boxes.length" class="chip info">{{ boxes.length }} 个目标</span>
              <span class="muted-text">{{ currentImage.width || '?' }}×{{ currentImage.height || '?' }}</span>
            </div>
          </div>
          <button class="stage-nav stage-next" @click.stop="nextImage">›</button>
        </template>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getAnnotationProgress, listImages, listVersions } from '../api/datasets.js'
import { getAnnotation } from '../api/annotations.js'

const COLORS = [
  '#E47630', '#3E7B59', '#667EA2', '#B65246', '#7C5CE0',
  '#0F8B8D', '#5B8DEF', '#9B6B3F', '#E04E8B', '#4CAF50',
]

const route = useRoute()
const version = ref(null)
const images = ref([])
const currentId = ref(null)
const currentImage = ref(null)
const currentIdx = ref(0)
const loading = ref(true)
const filter = ref('')
const boxes = ref([])
const annotationProgress = ref(null)
const stageImg = ref(null)
const boxCanvas = ref(null)
const stageError = ref(false)

const isAnnotationType = computed(() => (version.value?.dtype || '') === 'annotation')
const filteredImages = computed(() => {
  if (!filter.value) return images.value
  return images.value.filter(i => i.annotation_status === filter.value)
})

onMounted(load)
onMounted(() => { window.addEventListener('keydown', onKey); window.addEventListener('resize', drawBoxes) })
onUnmounted(() => { window.removeEventListener('keydown', onKey); window.removeEventListener('resize', drawBoxes) })

async function load() {
  loading.value = true
  try {
    const versionId = Number(route.params.id)
    if (!versionId) { loading.value = false; return }

    const all = (await listVersions()).items
    version.value = all.find(v => Number(v.id) === versionId)
    if (!version.value) { loading.value = false; return }

    if (isAnnotationType.value) {
      try { annotationProgress.value = await getAnnotationProgress(versionId) } catch {}
    }

    // 分页加载：超过 1000 张时分两次
    let allItems = []
    const pg1 = await listImages(versionId, { pageSize: 1000 })
    allItems = pg1.items || []
    if (pg1.total > 1000) {
      const pg2 = await listImages(versionId, { page: 2, pageSize: 1000 })
      allItems = allItems.concat(pg2.items || [])
    }
    images.value = allItems
    if (images.value.length) selectImage(images.value[0], 0)
  } catch (e) { console.error('预览加载失败:', e) }
  finally { loading.value = false }
}

async function selectImage(item, idx) {
  currentId.value = item.id
  currentImage.value = item
  currentIdx.value = idx ?? filteredImages.value.findIndex(i => i.id === item.id)
  boxes.value = []
  stageError.value = false
  clearCanvas()
  try { const r = await getAnnotation(item.id); boxes.value = r.boxes || [] } catch {}
  await nextTick()
  if (stageImg.value?.complete && !stageError.value) drawBoxes()
}

function setFilter(val) {
  filter.value = val
  if (filteredImages.value.length && !filteredImages.value.find(i => i.id === currentId.value)) {
    selectImage(filteredImages.value[0], 0)
  }
}

function clearCanvas() {
  const c = boxCanvas.value; if (!c) return
  c.getContext('2d').clearRect(0, 0, c.width, c.height)
}

function drawBoxes() {
  const img = stageImg.value; const canvas = boxCanvas.value
  if (!img || !canvas || !img.complete || stageError.value) return
  const rect = img.getBoundingClientRect()
  const wrap = img.parentElement; if (!wrap) return
  const wr = wrap.getBoundingClientRect()
  canvas.width = rect.width; canvas.height = rect.height
  canvas.style.width = rect.width + 'px'; canvas.style.height = rect.height + 'px'
  canvas.style.left = (rect.left - wr.left) + 'px'; canvas.style.top = (rect.top - wr.top) + 'px'
  const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height)
  if (!boxes.value.length) return
  const dw = rect.width; const dh = rect.height
  for (const box of boxes.value) {
    const x = (box.x_center - box.width / 2) * dw
    const y = (box.y_center - box.height / 2) * dh
    const w = box.width * dw; const h = box.height * dh
    const color = COLORS[box.class_id % COLORS.length]
    ctx.strokeStyle = color; ctx.fillStyle = color + '20'; ctx.lineWidth = 2
    ctx.fillRect(x, y, w, h); ctx.strokeRect(x, y, w, h)
    const label = `#${box.class_id}`; const fs = Math.max(10, Math.min(14, h * 0.4))
    ctx.font = `${fs}px system-ui, sans-serif`
    const tw = ctx.measureText(label).width
    ctx.fillStyle = color; ctx.fillRect(x, y - fs - 4, tw + 6, fs + 4)
    ctx.fillStyle = '#fff'; ctx.fillText(label, x + 3, y - 3)
  }
}

function prevImage() {
  if (currentIdx.value > 0) selectImage(filteredImages.value[currentIdx.value - 1], currentIdx.value - 1)
}
function nextImage() {
  if (currentIdx.value < filteredImages.value.length - 1) selectImage(filteredImages.value[currentIdx.value + 1], currentIdx.value + 1)
}
function onKey(e) {
  if (e.key === 'ArrowLeft') prevImage(); if (e.key === 'ArrowRight') nextImage()
}
function onThumbError(e) { e.target.style.display = 'none' }
function onStageError() { stageError.value = true }

function imageUrl(path) {
  const n = String(path || '').replace(/\\/g, '/')
  const idx = n.indexOf('datasets/')
  return idx >= 0 ? '/images/' + n.slice(idx + 9) : ''
}
function basename(path) { return String(path || '').replace(/\\/g, '/').split('/').pop() }
</script>

<style scoped>
.preview-shell { display:flex; flex-direction:column; height:calc(100vh - 44px); overflow:hidden; }
.preview-topbar {
  display:flex; align-items:center; gap:10px; padding:6px 12px;
  border-bottom:1px solid var(--line-soft); background:var(--card); flex-shrink:0;
}
.preview-body { display:grid; grid-template-columns:200px 1fr; flex:1; min-height:0; overflow:hidden; }
.preview-sidebar {
  border-right:1px solid var(--line-soft); display:flex; flex-direction:column; overflow:hidden;
}
.preview-filter { display:flex; padding:4px; flex-shrink:0; border-bottom:1px solid var(--line-soft); }
.preview-filter button {
  flex:1; padding:3px 0; border:none; background:none; font-size:10px; cursor:pointer;
  color:var(--muted); border-radius:4px;
}
.preview-filter button.active { background:var(--primary-light); color:var(--primary); font-weight:600; }
.preview-thumbs { flex:1; overflow-y:auto; padding:4px; }
.thumb-item {
  display:flex; align-items:center; gap:6px; padding:4px 6px; border-radius:6px;
  cursor:pointer; transition:background 0.1s; margin-bottom:2px; position:relative;
}
.thumb-item:hover { background:var(--bg-warm); }
.thumb-item.active { background:var(--primary-light); }
.thumb-item img { width:40px; height:30px; object-fit:cover; border-radius:3px; flex-shrink:0; background:#e0d8d0; }
.thumb-label { font-size:10px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; flex:1; min-width:0; }
.thumb-dot { width:6px; height:6px; border-radius:50%; flex-shrink:0; }
.dot-reviewed { background:#3e7b59; } .dot-ai_prelabel { background:#E47630; } .dot-unlabeled { background:#bbb; }
.preview-stage {
  display:flex; align-items:center; justify-content:center;
  background:#1a1715; position:relative; min-height:0; cursor:pointer;
}
.preview-placeholder { color:#666; font-size:13px; }
.stage-center { display:flex; flex-direction:column; align-items:center; gap:8px; }
.stage-canvas-wrap { position:relative; display:inline-block; }
.stage-img { max-width:88vw; max-height:72vh; object-fit:contain; display:block; }
.stage-canvas { position:absolute; top:0; left:0; pointer-events:none; }
.stage-info { display:flex; gap:6px; align-items:center; font-size:11px; color:#999; }
.stage-nav {
  position:absolute; top:50%; transform:translateY(-50%); width:48px; height:48px;
  border:none; background:rgba(255,255,255,0.08); color:white; font-size:28px;
  cursor:pointer; border-radius:50%; display:flex; align-items:center; justify-content:center;
  z-index:1; transition:background 0.15s;
}
.stage-nav:hover { background:rgba(255,255,255,0.18); }
.stage-prev { left:12px; } .stage-next { right:12px; }
</style>
