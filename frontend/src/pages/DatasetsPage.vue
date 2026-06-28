<template>
  <ConfirmDialog
    :visible="confirmDialog.visible"
    :title="confirmDialog.title"
    :message="confirmDialog.message"
    @confirm="confirmDialog.onConfirm()"
    @cancel="confirmDialog.visible = false"
  />
  <section class="page dataset-workbench">
    <PageHeader title="数据管理" subtitle="标注图集 → 标注导出 → 训练 / 测试 / 推理">
      <div class="header-actions">
        <button class="secondary-action" @click="openDatasetDialog('labeled')"><AppIcon name="upload" /> 上传完整数据集</button>
        <button class="primary-action" @click="openDatasetDialog('annotation')"><AppIcon name="add" /> 创建标注图集</button>
      </div>
    </PageHeader>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="uploadMsg" class="upload-msg">{{ uploadMsg }}</p>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else-if="!versions.length" class="empty-state compact-empty">
      <strong>还没有数据集</strong>
      <span>创建标注图集上传图片，或上传完整 YOLO 数据集。</span>
      <button class="primary-action mt-12" @click="openDatasetDialog('annotation')">创建第一个数据集</button>
    </div>

    <template v-else>
      <!-- dtype 筛选条 -->
      <div class="asset-toolbar">
        <label class="inline-filter">
          <span>类型筛选</span>
          <select v-model="dtypeFilter">
            <option value="">全部</option>
            <option value="train">训练集</option>
            <option value="val">验证集</option>
            <option value="test">测试/推理集</option>
            <option value="annotation">标注中</option>
            <option value="_none">未分类</option>
          </select>
        </label>
        <span class="toolbar-count-pill">当前结果 <strong>{{ filteredVersions.length }}</strong></span>
      </div>

      <!-- 卡片网格 -->
      <div class="dataset-card-grid">
        <div
          v-for="item in filteredVersions"
          :key="item.id"
          class="dataset-card"
          :class="'dsc-dtype--' + (item.dtype || 'none')"
        >
          <!-- dtype 色条 -->
          <div class="dsc-accent-bar"></div>

          <!-- 卡片头部 -->
          <div class="dsc-head">
            <div class="dsc-title-row">
              <strong class="dsc-name">{{ item.dataset_name }}</strong>
              <span class="dsc-subline">{{ datasetSummary(item) }}</span>
              <div class="dsc-meta">
                <span class="version-chip">{{ item.version }}</span>
                <select
                  class="dtype-pill"
                  :value="item.dtype || ''"
                  @change.stop="setDtype(item, $event.target.value)"
                >
                  <option value="">未分类</option>
                  <option value="train">训练集</option>
                  <option value="val">验证集</option>
                  <option value="test">测试/推理集</option>
                  <option value="annotation">标注中</option>
                </select>
              </div>
            </div>
          </div>

          <!-- 统计数字 — 统一 4 列，标注中多一行进度条 -->
          <div class="dsc-stats">
            <div class="dsc-stat">
              <span class="dsc-stat-label">图像总数</span>
              <b class="dsc-stat-value">{{ fmt(item.image_count) }}</b>
            </div>
            <div class="dsc-stat">
              <span class="dsc-stat-label">类别数</span>
              <b class="dsc-stat-value">{{ item.class_count || 0 }}</b>
            </div>
            <div class="dsc-stat">
              <span class="dsc-stat-label">标签总数</span>
              <b class="dsc-stat-value">{{ fmt(item.instance_count || item.label_file_count || 0) }}</b>
            </div>
            <div class="dsc-stat">
              <span class="dsc-stat-label">{{ isAnnotation(item) ? '已复核' : '含框图像' }}</span>
              <b class="dsc-stat-value">{{ isAnnotation(item) ? (item.reviewed_count || 0) : (item.label_file_count || 0) }}</b>
            </div>
          </div>

          <!-- 标注进度条 -->
          <div v-if="isAnnotation(item)" class="dsc-progress">
            <div class="dsc-progress-header">
              <span>标注进度</span>
              <span>{{ progressPct(item) }}%</span>
            </div>
            <div class="progress-bar-wrap">
              <div class="progress-bar" :style="{ width: progressPct(item) + '%' }"></div>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="dsc-actions">
            <RouterLink class="secondary-action small-action" :to="`/dataset/${item.id}`">预览</RouterLink>
            <button v-if="isAnnotation(item)" class="primary-action small-action" @click="continueUpload(item)">续传</button>
            <button v-if="canSplit(item)" class="secondary-action small-action" @click="openSplitDialog(item)">拆分</button>
            <button class="secondary-action small-action" @click="showDataYaml(item)">data.yaml</button>
            <button class="secondary-action small-action" @click="openRenameDialog(item)">改名</button>
            <button class="secondary-action small-action danger-action" @click="confirmDeleteVersion(item)">删除</button>
          </div>
        </div>

        <div v-if="!filteredVersions.length" class="empty-state compact-empty" style="grid-column:1/-1">
          <strong>没有符合条件的数据集</strong>
          <span>调整筛选条件或创建新数据集。</span>
        </div>
      </div>
    </template>

    <div v-if="showDatasetDialog" class="dialog-overlay" @click.self="closeDialog">
      <div class="dialog import-dialog">
        <h3>{{ dialogMode === 'labeled' ? '上传已标注数据集' : '创建新标注图集' }}</h3>

        <!-- 步骤指示器 -->
        <div class="upload-steps">
          <div class="upload-step" :class="{ active: dialogStep === 1, done: dialogStep > 1 }">
            <span class="step-number">1</span>
            <span class="step-label">基本信息</span>
          </div>
          <div class="step-divider" :class="{ done: dialogStep > 1 }"></div>
          <div class="upload-step" :class="{ active: dialogStep === 2, done: dialogStep > 2 }">
            <span class="step-number">2</span>
            <span class="step-label">{{ dialogMode === 'labeled' ? '上传数据' : '上传图片' }}</span>
          </div>
        </div>

        <!-- 步骤 1：基本信息 -->
        <div v-show="dialogStep === 1" class="step-content">
          <p class="step-desc">
            {{ dialogMode === 'labeled'
              ? '导入一个已有的 YOLO 格式数据集（包含 images、labels 和 data.yaml），可直接用于训练。'
              : '从一个图片文件夹开始标注项目，系统会自动创建空白标注文件，标注完成后可导出用于训练。' }}
          </p>
          <label>数据集名称
            <input v-model="form.name" :placeholder="dialogMode === 'labeled' ? '例如：安全帽公开数据集' : '例如：校园安全帽检测图集'" />
          </label>
          <label>说明（选填）
            <input v-model="form.description" placeholder="数据来源、采集场景、用途或标注规范说明" />
          </label>

          <template v-if="dialogMode === 'annotation'">
            <label>目标类别名称 <span class="muted-text">（选填，可在标注工作台中随时修改）</span>
              <textarea v-model="form.classText" rows="5" placeholder="每行一个类别名称，例如：&#10;helmet&#10;vest&#10;person&#10;不填则后续在标注工作台中创建"></textarea>
            </label>
            <p class="helper-text">建议使用英文名称。留空则进入标注工作台后再创建类别。</p>
          </template>
        </div>

        <!-- 步骤 2：上传文件 -->
        <div v-show="dialogStep === 2" class="step-content">
          <p class="step-desc">
            {{ dialogMode === 'labeled'
              ? '请选择包含 data.yaml 的 YOLO 数据集目录，或上传 ZIP 压缩包。'
              : '请选择仅包含图片文件的文件夹。系统会为每张图片创建空白标注（txt），后续可在标注工作台中逐张标注。' }}
          </p>

          <template v-if="dialogMode === 'labeled'">
            <div class="segmented" style="margin-bottom:12px">
              <button :class="{ active: uploadMode === 'folder' }" @click="uploadMode = 'folder'">选择文件夹</button>
              <button :class="{ active: uploadMode === 'zip' }" @click="uploadMode = 'zip'">上传 ZIP</button>
            </div>
            <div v-if="uploadMode === 'folder'" class="upload-box">
              <input ref="labeledFolderInput" type="file" webkitdirectory directory multiple hidden @change="onLabeledFolder" />
              <button class="secondary-action" @click="$refs.labeledFolderInput.click()">
                <AppIcon name="upload" /> 选择 YOLO 数据目录
              </button>
              <strong>{{ labeledFiles.length ? `已选择 ${labeledFiles.length} 个文件` : '请选择包含 data.yaml、images/、labels/ 的目录' }}</strong>
              <span>支持 YOLO 标准目录结构。导入后可直接绑定到项目参与训练、验证或测试。</span>
            </div>
            <div v-else class="upload-box" @dragover.prevent @drop.prevent="onZipDrop">
              <input ref="zipInput" type="file" accept=".zip" hidden @change="onZipSelected" />
              <button class="secondary-action" @click="$refs.zipInput.click()">
                <AppIcon name="upload" /> 选择 ZIP 文件
              </button>
              <strong>{{ zipFile?.name || '将 YOLO 数据集 ZIP 文件拖放到此处' }}</strong>
              <span>压缩包根目录中需包含 data.yaml 文件。</span>
            </div>
          </template>

          <template v-else>
            <div class="upload-box" @dragover.prevent @drop.prevent="onAnnotationDrop">
              <input ref="annotationFolderInput" type="file" webkitdirectory directory multiple hidden @change="onAnnotationFolder" />
              <button class="secondary-action" @click="$refs.annotationFolderInput.click()">
                <AppIcon name="upload" /> 选择图片文件夹
              </button>
              <strong>{{ annotationFiles.length ? `已选择 ${annotationFiles.length} 张图片` : '请选择仅包含图片文件的文件夹' }}</strong>
              <span>支持的格式：JPG、PNG、BMP、GIF、WebP、TIFF</span>
            </div>
          </template>
        </div>

        <div class="dialog-actions">
          <button v-if="dialogStep === 2" class="secondary-action" @click="dialogStep = 1">上一步</button>
          <button class="secondary-action" @click="closeDialog">取消</button>
          <button v-if="dialogStep === 1" class="primary-action" @click="goToStep2">
            下一步
          </button>
          <button v-if="dialogStep === 2" class="primary-action" :disabled="submitting" @click="submitImport">
            {{ submitting ? '处理中...' : dialogMode === 'labeled' ? '开始导入' : '开始创建' }}
          </button>
        </div>
        <p v-if="dialogError" class="error">{{ dialogError }}</p>
      </div>
    </div>

    <!-- data.yaml 弹窗 -->
    <div v-if="yamlDialog.visible" class="dialog-overlay" @click.self="yamlDialog.visible = false">
      <div class="dialog" style="max-width:560px">
        <h3>data.yaml — {{ yamlDialog.name }}</h3>
        <pre class="yaml-viewer"><code>{{ yamlDialog.content || '（文件不存在或为空）' }}</code></pre>
        <div class="dialog-actions">
          <button class="secondary-action" @click="yamlDialog.visible = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- 拆分对话框 -->
    <div v-if="showSplitDialog" class="dialog-overlay" @click.self="closeSplitDialog">
      <div class="dialog import-dialog">
        <h3>拆分为独立数据集</h3>
        <p class="helper-text">
          将「{{ splitTarget?.dataset_name }} / {{ splitTarget?.version }}」
          （共 <strong>{{ splitImageCount }}</strong> 张）拆成 3 个独立数据集
          <span v-if="isAnnotation(splitTarget)" style="color:var(--primary);font-weight:600">
            — 标注中数据集，仅导出已复核的 {{ splitTarget?.reviewed_count || 0 }} 张
          </span>
        </p>

        <div class="segmented" style="margin-bottom:10px">
          <button :class="{ active: splitMode === 'count' }" @click="splitMode = 'count'">按数量</button>
          <button :class="{ active: splitMode === 'ratio' }" @click="splitMode = 'ratio'">按比例</button>
        </div>

        <template v-if="splitMode === 'count'">
          <div class="split-ratio-row">
            <label>Train 张数
              <input v-model.number="splitCount.train" type="number" min="0" :max="splitImageCount" />
            </label>
            <label>Val 张数
              <input v-model.number="splitCount.val" type="number" min="0" :max="splitImageCount" />
            </label>
            <label>Test 张数
              <input v-model.number="splitCount.test" type="number" min="0" :max="splitImageCount" />
            </label>
          </div>
          <div class="split-summary">
            <span>共 {{ splitImageCount }} 张{{ isAnnotation(splitTarget) ? '已复核图片' : '' }}，使用 <strong>{{ splitCountTotal }}</strong> 张，剩余 {{ Math.max(0, splitImageCount - splitCountTotal) }} 张不使用</span>
          </div>
          <p class="helper-text">不填 = 0 = 不使用该类型。例如：1754 张图只要 train=200, val=50, test=20，剩余 1484 张不会被拆出去。</p>
        </template>
        <template v-else>
          <div class="split-ratio-row">
            <label>Train %
              <input v-model.number="splitRatio.train" type="number" min="10" max="90" step="5" />
            </label>
            <label>Val %
              <input v-model.number="splitRatio.val" type="number" min="0" max="80" step="5" />
            </label>
            <label>Test %
              <input v-model.number="splitRatio.test" type="number" min="0" max="80" step="5" />
            </label>
          </div>
        </template>

        <p v-if="splitError" class="error">{{ splitError }}</p>
        <div class="dialog-actions">
          <button class="secondary-action" @click="closeSplitDialog">取消</button>
          <button class="primary-action" :disabled="splitting" @click="submitSplitInto">
            {{ splitting ? '处理中...' : '确认拆分' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import PageHeader from '../components/PageHeader.vue'
import {
  appendImagesToVersion,
  createDataset,
  deleteDatasetVersion,
  listVersions,
  uploadAnnotationFolder,
  uploadFolderVersion,
  uploadVersion,
  changeDatasetDtype,
  splitIntoIndependent,
  updateDataset,
  getDataYaml,
} from '../api/datasets.js'

const router = useRouter()
const confirmDialog = reactive({ visible: false, title: '', message: '', onConfirm: () => {} })
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const dialogError = ref('')
const uploadMsg = ref('')
const versions = ref([])
const showDatasetDialog = ref(false)
const dialogMode = ref('labeled')
const dialogStep = ref(1)
const uploadMode = ref('folder')
const labeledFiles = ref([])
const annotationFiles = ref([])
const zipFile = ref(null)

const form = reactive({ name: '', description: '', classText: '' })
const showSplitDialog = ref(false)
const splitTarget = ref(null)
const splitting = ref(false)
const splitError = ref('')
const splitRatio = reactive({ train: 70, val: 20, test: 10 })
const splitCount = reactive({ train: 0, val: 0, test: 0 })
const splitMode = ref('count')
const yamlDialog = reactive({ visible: false, name: '', content: '' })

async function showDataYaml(item) {
  yamlDialog.name = item.dataset_name
  yamlDialog.content = '加载中...'
  yamlDialog.visible = true
  try {
    const res = await getDataYaml(item.id)
    yamlDialog.content = res.content || '(文件为空)'
  } catch (err) {
    yamlDialog.content = '加载失败: ' + (err?.message || String(err))
  }
}

const splitCountTotal = computed(() => (splitCount.train || 0) + (splitCount.val || 0) + (splitCount.test || 0))
const splitImageCount = computed(() => {
  if (!splitTarget.value) return 0
  // 标注中数据集：只显示已复核数量
  if (isAnnotation(splitTarget.value)) return splitTarget.value.reviewed_count || 0
  return splitTarget.value.image_count || 0
})

const dtypeFilter = ref('')
const filteredVersions = computed(() => {
  if (!dtypeFilter.value) return versions.value
  if (dtypeFilter.value === '_none') return versions.value.filter(v => !(v.dtype || '').trim())
  return versions.value.filter(v => (v.dtype || '').trim() === dtypeFilter.value)
})

function hasLabels(item) { return Number(item.label_file_count || 0) > 0 }
function isAnnotation(item) { return (item.dtype || '') === 'annotation' }
function canSplit(item) {
  const dt = (item.dtype || '').trim()
  // 只有未分类全集 和 标注完成的数据集才能拆分
  // train/val/test 已经拆分过，不再拆分
  if (!dt && hasLabels(item)) return true
  if (dt === 'annotation' && (item.reviewed_count || 0) > 0) return true
  return false
}
function progressPct(item) {
  if (!item.image_count) return 0
  return Math.round(((item.reviewed_count || 0) / item.image_count) * 100)
}
function dtypeText(item) {
  const dt = (item.dtype || '').trim()
  return {
    train: '训练集',
    val: '验证集',
    test: '测试/推理集',
    annotation: '标注中',
  }[dt] || '未分类'
}
function datasetSummary(item) {
  if (isAnnotation(item)) {
    return `标注工作流 · 已复核 ${item.reviewed_count || 0} / ${item.image_count || 0} 张`
  }
  if ((item.dtype || '').trim() === 'train') return '训练数据 · 可直接用于训练和验证'
  if ((item.dtype || '').trim() === 'val') return '验证数据 · 建议用于评估训练收敛'
  if ((item.dtype || '').trim() === 'test') return '测试数据 · 适合离线评估与推理抽检'
  if (hasLabels(item)) return '未分类全集 · 已有标注，可拆分或直接绑定'
  return '未分类数据 · 当前无标注，适合继续上传或补标'
}

async function setDtype(item, newDtype) {
  try {
    await changeDatasetDtype(item.id, newDtype || '')
    item.dtype = newDtype
  } catch (err) { alert(err?.message || '设置类型失败') }
}


onMounted(() => load())
onActivated(() => load({ silent: true }))
async function load(options = {}) {
  const { silent = false } = options
  if (!silent) loading.value = true
  error.value = ''
  try {
    versions.value = (await listVersions()).items
  } catch (err) {
    error.value = err?.message || '加载数据集列表失败，请检查后端服务是否正常运行'
  } finally {
    if (!silent) loading.value = false
  }
}

function openDatasetDialog(mode) {
  dialogMode.value = mode
  dialogStep.value = 1
  uploadMode.value = 'folder'
  form.name = ''
  form.description = ''
  form.classText = ''
  labeledFiles.value = []
  annotationFiles.value = []
  zipFile.value = null
  dialogError.value = ''
  showDatasetDialog.value = true
}

function goToStep2() {
  dialogError.value = ''
  if (!form.name.trim()) { dialogError.value = '请输入数据集名称'; return }
  // 类别名称选填，可在标注工作台中创建
  dialogStep.value = 2
}

function closeDialog() { showDatasetDialog.value = false; dialogStep.value = 1; submitting.value = false }

async function submitImport() {
  dialogError.value = ''
  if (dialogMode.value === 'labeled') {
    if (uploadMode.value === 'zip' && !zipFile.value) { dialogError.value = '请先选择 ZIP 文件或将文件拖放到虚线区域'; return }
    if (uploadMode.value === 'folder' && !labeledFiles.value.length) { dialogError.value = '请先选择包含 data.yaml 的 YOLO 数据目录'; return }
  } else {
    if (!annotationFiles.value.length) { dialogError.value = '请先选择包含图片文件的文件夹'; return }
  }
  try {
    submitting.value = true
    const dataset = await createDataset(form.name.trim(), form.description.trim())
    if (dialogMode.value === 'labeled') {
      if (uploadMode.value === 'zip') {
        await uploadVersion(dataset.id, zipFile.value)
      } else {
        await uploadFolderVersion(dataset.id, labeledFiles.value)
      }
    } else {
      const result = await uploadAnnotationFolder(dataset.id, annotationFiles.value, form.classText,
        (progress) => {
          if (progress.errors) {
            dialogError.value = `上传中 ${progress.done}/${progress.total}（${progress.added} 张已保存`
            if (progress.errors > 0) dialogError.value += `，${progress.errors} 个错误`
            dialogError.value += `）`
          } else {
            dialogError.value = `上传中 ${progress.done}/${progress.total}...`
          }
        })
      if (result.errors?.length) {
        dialogError.value = `上传完成：${result.added}/${annotationFiles.value.length} 张成功，${result.errors.length} 个批次失败`
      } else {
        dialogError.value = ''
      }
    }
    showDatasetDialog.value = false
    await load({ silent: true })
  } catch (err) {
    const msg = err?.message || String(err)
    if (msg.includes('already exists') || msg.includes('已存在') || msg.includes('UNIQUE')) {
      dialogError.value = '该数据集名称已存在，请更换名称'
    } else if (msg.includes('not found') || msg.includes('找不到')) {
      dialogError.value = '未找到所需文件，请检查上传内容是否完整'
    } else if (msg.includes('data.yaml')) {
      dialogError.value = '未在目录中找到 data.yaml 文件，请确认所选的文件夹是有效的 YOLO 数据集'
    } else if (msg.includes('timeout') || msg.includes('超时')) {
      dialogError.value = '上传超时，请检查网络连接或减小文件大小'
    } else {
      dialogError.value = msg
    }
  } finally { submitting.value = false }
}


function confirmDeleteVersion(item) {
  confirmDialog.title = '删除版本'
  confirmDialog.message = `确认删除「${item.dataset_name} / ${item.version}」？`
  confirmDialog.onConfirm = async () => {
    confirmDialog.visible = false
    try { await deleteDatasetVersion(item.id); await load({ silent: true }) } catch (err) { alert(err?.message || '删除失败') }
  }
  confirmDialog.visible = true
}

async function openRenameDialog(item) {
  const newName = prompt('请输入新数据集名称：', item.dataset_name)
  if (!newName || newName === item.dataset_name) return
  try {
    await updateDataset(item.dataset_id, { name: newName, description: '' })
    await load({ silent: true })
  } catch (err) { alert(err?.message || '改名失败') }
}

function openSplitDialog(item) {
  splitTarget.value = item
  splitRatio.train = 70
  splitRatio.val = 20
  splitRatio.test = 10
  splitCount.train = 0
  splitCount.val = 0
  splitCount.test = 0
  splitMode.value = 'count'
  splitError.value = ''
  showSplitDialog.value = true
}
function closeSplitDialog() { showSplitDialog.value = false; splitting.value = false }

async function submitSplitInto() {
  splitError.value = ''
  if (!splitTarget.value) return
  const totalImages = splitImageCount.value
  if (totalImages <= 0) {
    splitError.value = '当前没有可拆分的已复核图片'
    return
  }
  try {
    splitting.value = true
    if (splitMode.value === 'count') {
      const total = (splitCount.train || 0) + (splitCount.val || 0) + (splitCount.test || 0)
      if (total <= 0) { splitError.value = '请至少指定一个拆分数量（train、val 或 test）'; return }
      if (total > totalImages) { splitError.value = `拆分张数总和（${total}）超过了数据集总数（${totalImages} 张），请调整数量`; return }
      await splitIntoIndependent(splitTarget.value.id, {
        train_count: splitCount.train,
        val_count: splitCount.val,
        test_count: splitCount.test,
        only_reviewed: isAnnotation(splitTarget.value),
      })
    } else {
      const sum = splitRatio.train + splitRatio.val + splitRatio.test
      if (Math.abs(sum - 100) > 1) { splitError.value = `比例之和必须为 100%，当前为 ${sum}%`; return }
      await splitIntoIndependent(splitTarget.value.id, {
        train_ratio: splitRatio.train / 100,
        val_ratio: splitRatio.val / 100,
        test_ratio: splitRatio.test / 100,
        only_reviewed: isAnnotation(splitTarget.value),
      })
    }
    showSplitDialog.value = false
    await load({ silent: true })
  } catch (err) {
    splitError.value = err?.message || '拆分失败'
  } finally { splitting.value = false }
}

function continueUpload(item) {
  const input = document.createElement('input')
  input.type = 'file'
  input.multiple = true
  input.accept = 'image/jpeg,image/png,image/bmp,image/webp,image/gif,image/tiff'
  input.onchange = async () => {
    const files = Array.from(input.files || [])
    if (!files.length) return
    uploadMsg.value = `正在续传 ${files.length} 张到「${item.dataset_name}」...`
    try {
      const result = await appendImagesToVersion(item.id, files, (progress) => {
        uploadMsg.value = `续传中 ${progress.done}/${progress.total}（${progress.added} 张已保存）`
      })
      if (result.errors?.length) {
        uploadMsg.value = `续传完成：${result.added}/${files.length} 张成功，${result.errors.length} 个批次失败`
      } else {
        uploadMsg.value = `续传完成：成功 ${result.added} 张`
        setTimeout(() => { uploadMsg.value = '' }, 3000)
      }
      await load({ silent: true })
    } catch (err) {
      uploadMsg.value = ''
      error.value = '续传失败：' + (err?.message || String(err))
    }
  }
  input.click()
}

function fmt(value) { return value === null || value === undefined ? '-' : Number(value).toLocaleString() }
function onLabeledFolder(e) { labeledFiles.value = Array.from(e.target.files || []) }
function onAnnotationFolder(e) {
  // 只保留图片文件，过滤掉 txt/yaml 等
  const imageExts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff']
  annotationFiles.value = Array.from(e.target.files || []).filter(f => {
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    return imageExts.includes(ext)
  })
}
function onZipSelected(e) { zipFile.value = e.target.files?.[0] || null }
function onZipDrop(e) { zipFile.value = Array.from(e.dataTransfer.files || []).find(f => f.name.endsWith('.zip')) || null }
function onAnnotationDrop(e) {
  e.preventDefault()
  const imageExts = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff']
  annotationFiles.value = Array.from(e.dataTransfer.files || []).filter(f => {
    const ext = '.' + f.name.split('.').pop().toLowerCase()
    return imageExts.includes(ext)
  })
}
</script>
