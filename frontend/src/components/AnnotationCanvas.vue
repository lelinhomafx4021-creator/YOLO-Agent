<!--
  组件名称: AnnotationCanvas（标注画布）
  组件用途: 提供 YOLO 图像标注的核心画布功能，支持图片的缩放/平移、
           边界框（Bounding Box）的创建、选中、拖拽移动和删除，
           以及标注框的视觉渲染与交互操作。
  使用场景: 数据集标注工具的主编辑区域，配合图片加载、类别选择和标注列表使用。
-->

<template>
  <!-- ===== 画布容器 ===== -->
  <!-- 容器元素：负责捕获鼠标事件（滚轮缩放、拖拽平移、绘制框、选中框），
       内部包含图片层、Canvas 覆盖层和占位提示文本。 -->
  <div
    class="canvas-container"
    ref="containerRef"
    @wheel.prevent="onWheel"
    @mousedown="onMouseDown"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseleave="onMouseUp"
  >
    <!-- 图片层：加载并显示待标注的原始图片 -->
    <img
      v-show="imageUrl && !imgError"
      ref="imageRef"
      :src="imageUrl"
      :style="imageStyle"
      @load="onImageLoad"
      @error="onImageError"
      draggable="false"
      class="canvas-image"
    />
    <!-- Canvas 覆盖层：在图片之上绘制边界框、标签及绘制中的预览框 -->
    <canvas ref="canvasRef" class="canvas-overlay" />
    <!-- 图片加载失败时的占位提示 -->
    <div v-if="imgError" class="canvas-placeholder">图片加载失败</div>
    <!-- 未选择图片时的占位提示 -->
    <div v-if="!imageUrl" class="canvas-placeholder">请选择一张图片</div>
  </div>
</template>

<script setup>
/**
 * Vue 3 Composition API 组件
 * 本组件集中处理 YOLO 格式标注的可视化与交互，包括：
 * - 图片自适应缩放与居中展示
 * - 鼠标滚轮缩放（以鼠标位置为锚点）
 * - 拖拽平移画布
 * - 绘制新边界框（draw 模式）
 * - 选中并拖拽移动已有边界框（select 模式）
 * - 点击删除已有边界框（delete 模式）
 * - Canvas 实时重绘全部标注信息
 */
import { ref, computed, watch, nextTick } from 'vue'

/* ==================== Props（父组件传入的属性） ==================== */
const props = defineProps({
  /** 当前要加载和标注的图片 URL */
  imageUrl: { type: String, default: '' },
  /** 所有标注框的数组，每个元素为 YOLO 格式：{ class_id, x_center, y_center, width, height, confidence? } */
  boxes: { type: Array, default: () => [] },
  /** 类别名称列表，下标对应 class_id */
  classes: { type: Array, default: () => [] },
  /** 当前选中框的索引（-1 表示未选中） */
  selectedBoxIndex: { type: Number, default: -1 },
  /** 交互模式：'select'（选择/拖拽）| 'draw'（绘制）| 'delete'（删除） */
  mode: { type: String, default: 'select' },
})

/* ==================== Emits（子组件向外触发的事件） ==================== */
const emit = defineEmits([
  'box-select',    // 选中某个框时触发，参数为框的索引
  'box-create',    // 绘制完成新框时触发，参数为新框的 YOLO 数据
  'box-update',    // 拖拽移动框后触发，参数为 { index, box }
  'box-delete',    // 删除某个框时触发，参数为框的索引
])

/* ==================== 响应式变量（模板引用与状态） ==================== */
/** 画布容器 DOM 的引用 */
const containerRef = ref(null)
/** 图片 DOM 的引用 */
const imageRef = ref(null)
/** Canvas 覆盖层 DOM 的引用 */
const canvasRef = ref(null)
/** 图片是否加载失败 */
const imgError = ref(false)

/** 图片原始宽度（px），由 onImageLoad 在图片加载成功后赋值 */
const naturalW = ref(0)
/** 图片原始高度（px），由 onImageLoad 在图片加载成功后赋值 */
const naturalH = ref(0)
/** 当前缩放比例（受滚轮控制，范围 0.1 ~ 8），初始由 fitToScreen 根据容器尺寸计算 */
const scale = ref(1)
/** 图片在容器中的水平偏移量（px），用于居中与拖拽平移 */
const offsetX = ref(0)
/** 图片在容器中的垂直偏移量（px），用于居中与拖拽平移 */
const offsetY = ref(0)

/* ==================== 非响应式状态（绘制与拖拽的中间过程变量） ==================== */
/**
 * 以下变量不声明为 ref，因为它们仅用于鼠标事件临时状态，
 * 不需要触发 Vue 的响应式更新，减少不必要的性能开销。
 */
/** 是否正在绘制新边界框（draw 模式下鼠标按下时为 true，松开时重置） */
let drawing = false
/** 绘制起点（屏幕坐标系下的像素坐标），在 mousedown 时记录 */
let drawStart = null
/** 绘制当前鼠标位置（屏幕坐标系下的像素坐标），在 mousemove 时持续更新 */
let drawCurrent = null
/** 是否正在拖拽（选中框或平移画布），select 模式下鼠标按下时为 true */
let dragging = false
/** 拖拽起始鼠标位置（全局坐标系 clientX/clientY） */
let dragStart = null
/** 拖拽开始时画布的偏移量快照，用于计算平移差值 */
let dragOffsetStart = null

/* ==================== 计算属性 ==================== */
/**
 * 图片的绝对定位样式：根据缩放和偏移确定图片在容器中的位置与尺寸。
 * 当图片尚未加载（naturalW / naturalH 为 0）时隐藏图片，避免显示错误尺寸。
 */
const imageStyle = computed(() => {
  if (!naturalW.value || !naturalH.value) return { display: 'none' }
  return {
    position: 'absolute',
    left: offsetX.value + 'px',
    top: offsetY.value + 'px',
    width: Math.round(naturalW.value * scale.value) + 'px',
    height: Math.round(naturalH.value * scale.value) + 'px',
  }
})

/* ==================== 颜色工具 ==================== */
/** 各类别的固定颜色面板，按 class_id 循环取色，共 10 种高饱和度颜色 */
const COLORS = [
  '#1F6FA5', '#2F7A64', '#3B82F6', '#D4556B', '#7C5CE0',
  '#0F8B8D', '#14B8A6', '#5B8DEF', '#6366F1', '#84CC16',
]
/**
 * 根据 class_id 返回对应的标注框颜色
 * @param {number} id - 类别 ID
 * @returns {string} 十六进制颜色值
 */
function classColor(id) { return COLORS[id % COLORS.length] }

/* ==================== 图片加载回调 ==================== */
/**
 * 图片加载成功后：重置错误状态、记录原始尺寸、自适应缩放居中。
 * 由 <img> 的 @load 事件触发。
 */
function onImageLoad() {
  imgError.value = false
  const img = imageRef.value
  if (!img) return
  naturalW.value = img.naturalWidth
  naturalH.value = img.naturalHeight
  fitToScreen()
}

/**
 * 图片加载失败时：设置错误标志，显示占位提示。
 * 由 <img> 的 @error 事件触发。
 */
function onImageError() { imgError.value = true }

/* ==================== 坐标变换 ==================== */
/**
 * 将图片坐标转换为屏幕坐标
 * 公式：屏幕坐标 = 图片坐标 × 缩放比例 + 画布偏移量
 * @param {number} ix - 图片坐标系下的 X（像素值）
 * @param {number} iy - 图片坐标系下的 Y（像素值）
 * @returns {{ x: number, y: number }} 屏幕坐标（相对于画布容器左上角）
 */
function imageToScreen(ix, iy) {
  return { x: ix * scale.value + offsetX.value, y: iy * scale.value + offsetY.value }
}

/**
 * 将屏幕坐标转换为图片坐标
 * 公式：图片坐标 = (屏幕坐标 - 容器偏移 - 画布偏移量) / 缩放比例
 * @param {number} sx - 屏幕坐标系下的 X（相对于视口的 clientX）
 * @param {number} sy - 屏幕坐标系下的 Y（相对于视口的 clientY）
 * @returns {{ x: number, y: number }} 图片坐标（像素值）
 */
function screenToImage(sx, sy) {
  const rect = containerRef.value?.getBoundingClientRect()
  if (!rect) return { x: 0, y: 0 }
  return {
    x: (sx - rect.left - offsetX.value) / scale.value,
    y: (sy - rect.top - offsetY.value) / scale.value,
  }
}

/**
 * 将图片自适应缩放并居中显示在容器内。
 * - 缩放比例取容器宽/高与图片宽/高比值中的较小者
 * - 限制最大缩放为 1（避免放大导致图片模糊）
 * - 计算水平和垂直的偏移量使图片居中
 * - 完成后触发重绘
 */
function fitToScreen() {
  const c = containerRef.value
  if (!c || !naturalW.value || !naturalH.value) return
  scale.value = Math.min(c.clientWidth / naturalW.value, c.clientHeight / naturalH.value, 1)
  offsetX.value = (c.clientWidth - naturalW.value * scale.value) / 2
  offsetY.value = (c.clientHeight - naturalH.value * scale.value) / 2
  nextTick(() => drawAll())
}

/* ==================== 绘制逻辑（Canvas 渲染） ==================== */
/**
 * 清空 Canvas 并重绘所有边界框、标签以及正在绘制的预览框。
 * 此函数是核心渲染入口，在每次需要更新画布时调用。
 * 步骤：
 *   1. 调整 Canvas 尺寸以匹配容器
 *   2. 遍历所有标注框，将 YOLO 归一化坐标转为图片像素坐标再转为屏幕坐标
 *   3. 绘制每个框的边框、半透明填充和标签文字
 *   4. 如果正在绘制新框，用橙色虚线绘制预览矩形
 */
function drawAll() {
  const cv = canvasRef.value
  const c = containerRef.value
  if (!cv || !c) return
  cv.width = c.clientWidth
  cv.height = c.clientHeight
  const ctx = cv.getContext('2d')
  ctx.clearRect(0, 0, cv.width, cv.height)

  // 遍历所有标注框，逐一绘制
  for (let i = 0; i < props.boxes.length; i++) {
    const box = props.boxes[i]
    // YOLO 格式（归一化坐标）转换为图片像素坐标
    const x = box.x_center * naturalW.value
    const y = box.y_center * naturalH.value
    const w = box.width * naturalW.value
    const h = box.height * naturalH.value
    const left = x - w / 2
    const top = y - h / 2
    // 图片像素坐标再转换为屏幕坐标
    const s = imageToScreen(left, top)
    const sw = w * scale.value
    const sh = h * scale.value
    const color = classColor(box.class_id)
    const sel = i === props.selectedBoxIndex

    // 绘制框的边框：选中时使用金色高亮（#FFD700），未选中使用类别颜色
    ctx.strokeStyle = sel ? '#FFD700' : color
    ctx.lineWidth = sel ? 3 : 2
    ctx.strokeRect(s.x, s.y, sw, sh)
    // 绘制框的半透明填充：选中时金色半透明，未选中时类别颜色 12.5% 不透明度
    ctx.fillStyle = sel ? 'rgba(255,215,0,0.15)' : color + '20'
    ctx.fillRect(s.x, s.y, sw, sh)

    // 绘制标签文字（类别名 + 置信度），放在框的上方
    const label = (props.classes[box.class_id] || 'cls' + box.class_id) +
      (box.confidence != null ? ' ' + box.confidence.toFixed(2) : '')
    ctx.font = '12px sans-serif'
    const tw = ctx.measureText(label).width + 4
    const ty = s.y - 6
    if (ty > 12) {
      ctx.fillStyle = sel ? 'rgba(0,0,0,0.8)' : 'rgba(0,0,0,0.6)'
      ctx.fillRect(s.x, ty - 12, tw, 14)        // 标签背景
      ctx.fillStyle = '#fff'
      ctx.fillText(label, s.x + 2, ty)           // 标签文字
    }
  }

  // 绘制模式下：用主色虚线预览当前正在绘制的矩形
  if (drawing && drawStart && drawCurrent) {
    ctx.strokeStyle = '#1F6FA5'
    ctx.lineWidth = 2
    ctx.setLineDash([4, 4])
    const x = Math.min(drawStart.x, drawCurrent.x)
    const y = Math.min(drawStart.y, drawCurrent.y)
    const w = Math.abs(drawCurrent.x - drawStart.x)
    const h = Math.abs(drawCurrent.y - drawStart.y)
    ctx.strokeRect(x, y, w, h)
    ctx.setLineDash([])
  }
}

/* ==================== 命中检测 ==================== */
/**
 * 检测屏幕坐标 (sx, sy) 是否落在某个已有标注框内。
 * 遍历顺序为从后往前（上层优先，即后绘制的框优先被检测到）。
 * @param {number} sx - 屏幕坐标系下的 X（clientX）
 * @param {number} sy - 屏幕坐标系下的 Y（clientY）
 * @returns {number} 命中框的索引，未命中返回 -1
 */
function hitTest(sx, sy) {
  const img = screenToImage(sx, sy)
  for (let i = props.boxes.length - 1; i >= 0; i--) {
    const b = props.boxes[i]
    const bx = b.x_center * naturalW.value
    const by = b.y_center * naturalH.value
    const bw = b.width * naturalW.value
    const bh = b.height * naturalH.value
    if (img.x >= bx - bw / 2 && img.x <= bx + bw / 2 &&
        img.y >= by - bh / 2 && img.y <= by + bh / 2) return i
  }
  return -1
}

/* ==================== 鼠标事件处理 ==================== */
/**
 * 鼠标按下事件处理函数。
 * 根据当前交互模式（props.mode）执行不同操作：
 * - draw 模式：在鼠标位置开始绘制新边界框，记录起点
 * - select 模式：检测是否点中某个框，若命中则准备拖拽移动；否则准备平移画布
 * - delete 模式：检测鼠标位置，若在框内则直接触发删除事件
 * @param {MouseEvent} e - 原生鼠标事件对象
 */
function onMouseDown(e) {
  if (!naturalW.value) return
  if (props.mode === 'draw') {
    // 绘制模式：记录绘制起点（屏幕坐标），开始绘制
    const rect = containerRef.value.getBoundingClientRect()
    drawing = true
    drawStart = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    drawCurrent = { ...drawStart }
  } else if (props.mode === 'select') {
    // 选择模式：先检测是否点中某个框，若选中则进入拖拽移动；否则准备平移画布
    const hit = hitTest(e.clientX, e.clientY)
    emit('box-select', hit)
    dragging = true
    dragStart = { x: e.clientX, y: e.clientY }
    if (hit < 0) dragOffsetStart = { x: offsetX.value, y: offsetY.value }
  } else if (props.mode === 'delete') {
    // 删除模式：检测点击位置，若在某个框内则触发删除事件
    const hit = hitTest(e.clientX, e.clientY)
    if (hit >= 0) emit('box-delete', hit)
  }
}

/**
 * 鼠标移动事件处理函数。
 * 根据当前交互状态执行不同操作：
 * - 绘制中（drawing = true）：更新绘制预览框坐标，触发重绘
 * - 拖拽中（dragging = true）且有选中框：计算移动距离并更新框的位置
 * - 拖拽中（dragging = true）且无选中框：平移整个画布
 * @param {MouseEvent} e - 原生鼠标事件对象
 */
function onMouseMove(e) {
  if (drawing && props.mode === 'draw') {
    // 绘制中：更新当前鼠标位置，触发重绘以更新虚线预览框
    const rect = containerRef.value.getBoundingClientRect()
    drawCurrent = { x: e.clientX - rect.left, y: e.clientY - rect.top }
    nextTick(() => drawAll())
  } else if (dragging && props.mode === 'select') {
    if (props.selectedBoxIndex >= 0) {
      // 有选中框：计算鼠标移动距离（图片坐标），更新框的中心位置
      const dx = (e.clientX - dragStart.x) / scale.value
      const dy = (e.clientY - dragStart.y) / scale.value
      dragStart = { x: e.clientX, y: e.clientY }
      const box = { ...props.boxes[props.selectedBoxIndex] }
      box.x_center = Math.max(0, Math.min(1, box.x_center + dx / naturalW.value))
      box.y_center = Math.max(0, Math.min(1, box.y_center + dy / naturalH.value))
      emit('box-update', { index: props.selectedBoxIndex, box })
    } else if (dragOffsetStart) {
      // 没有选中框：平移整个画布
      offsetX.value = dragOffsetStart.x + (e.clientX - dragStart.x)
      offsetY.value = dragOffsetStart.y + (e.clientY - dragStart.y)
      nextTick(() => drawAll())
    }
  }
}

/**
 * 鼠标松开（或离开画布）事件处理函数。
 * - 如果正在绘制且面积大于 5x5 像素，将绘制的矩形转换为 YOLO 格式并触发 box-create 事件
 * - 重置所有拖拽/绘制中间状态变量
 * - 触发 Canvas 重绘
 */
function onMouseUp() {
  if (drawing && props.mode === 'draw' && drawStart && drawCurrent) {
    // 计算绘制矩形的起止屏幕坐标
    const x1 = Math.min(drawStart.x, drawCurrent.x)
    const y1 = Math.min(drawStart.y, drawCurrent.y)
    const x2 = Math.max(drawStart.x, drawCurrent.x)
    const y2 = Math.max(drawStart.y, drawCurrent.y)
    // 仅当绘制面积大于 5x5 像素时才视为有效绘制，防止误触产生过小框
    if (x2 - x1 > 5 && y2 - y1 > 5) {
      // 将屏幕坐标转换为图片坐标，再归一化为 YOLO 格式（值范围 0~1）
      const img1 = screenToImage(
        x1 + containerRef.value.getBoundingClientRect().left,
        y1 + containerRef.value.getBoundingClientRect().top)
      const img2 = screenToImage(
        x2 + containerRef.value.getBoundingClientRect().left,
        y2 + containerRef.value.getBoundingClientRect().top)
      emit('box-create', {
        class_id: 0,
        x_center: (img1.x + img2.x) / 2 / naturalW.value,
        y_center: (img1.y + img2.y) / 2 / naturalH.value,
        width: (img2.x - img1.x) / naturalW.value,
        height: (img2.y - img1.y) / naturalH.value,
      })
    }
  }
  // 重置所有拖拽/绘制状态
  drawing = false
  dragging = false
  drawStart = null
  drawCurrent = null
  dragStart = null
  dragOffsetStart = null
  nextTick(() => drawAll())
}

/* ==================== 滚轮缩放 ==================== */
/**
 * 鼠标滚轮事件处理函数。
 * 以鼠标当前位置为锚点进行缩放，确保鼠标下方的图片内容在缩放后位置不变。
 * - 滚轮向上（deltaY < 0）：放大至 1.1 倍
 * - 滚轮向下（deltaY > 0）：缩小至 0.9 倍
 * - 缩放范围限制在 0.1 ~ 8 倍之间
 * @param {WheelEvent} e - 原生滚轮事件对象
 */
function onWheel(e) {
  const factor = e.deltaY < 0 ? 1.1 : 0.9
  const ns = Math.max(0.1, Math.min(8, scale.value * factor))
  const rect = containerRef.value.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  // 保持鼠标下方的图片内容位置不变
  offsetX.value = mx - (mx - offsetX.value) * (ns / scale.value)
  offsetY.value = my - (my - offsetY.value) * (ns / scale.value)
  scale.value = ns
  nextTick(() => drawAll())
}

/* ==================== 暴露给父组件的方法 ==================== */
/**
 * 供父组件通过模板 ref 调用的自适应缩放方法。
 * 使用 defineExpose 暴露后，父组件可通过 `canvasRef.fitToScreen()` 调用。
 */
function fitToScreenPublic() { fitToScreen() }
defineExpose({ fitToScreen: fitToScreenPublic })

/* ==================== 响应式监听 ==================== */
/**
 * 监听标注框列表、选中索引或图片 URL 的变化，自动触发 Canvas 重绘。
 * 使用 deep: true 以检测数组内部元素的变更。
 */
watch(() => [props.boxes, props.selectedBoxIndex, props.imageUrl],
  () => { nextTick(() => drawAll()) },
  { deep: true })
</script>

<style scoped>
/* ===== 画布容器样式 ===== */
/* 相对定位的容器，占据全部可用空间，包含图片和 Canvas 覆盖层 */
.canvas-container {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
  background:
    radial-gradient(circle at top left, rgba(72, 129, 180, 0.14), transparent 24%),
    linear-gradient(180deg, #f5f8fc 0%, #edf3f8 100%);
  overflow: hidden;              /* 裁剪超出容器范围的图片内容 */
  cursor: crosshair;             /* 十字准星指针，提示可交互 */
}

/* ===== 图片样式 ===== */
/* 阻止图片自身捕获鼠标事件，将所有交互委托给上层的 Canvas 覆盖层处理 */
.canvas-image {
  pointer-events: none;
}

/* ===== Canvas 覆盖层样式 ===== */
/* 绝对定位覆盖在图片之上，负责绘制所有标注图形（边界框、标签、预览线） */
.canvas-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 2;                   /* 确保位于图片上方 */
}

/* ===== 占位提示文字样式 ===== */
/* 居中显示在容器内的提示信息（图片加载失败 / 未选择图片时的引导文案） */
.canvas-placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6a7d92;
  font-size: 14px;
}
</style>
