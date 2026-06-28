<template>
  <ConfirmDialog
    :visible="confirmDialog.visible"
    :title="confirmDialog.title"
    :message="confirmDialog.message"
    @confirm="confirmDialog.onConfirm()"
    @cancel="confirmDialog.visible = false"
  />
  <section class="page">
    <PageHeader :title="workspaceName" subtitle="工作台详情">
      <div class="header-actions">
        <RouterLink class="secondary-action" to="/datasets">← 返回列表</RouterLink>
      </div>
    </PageHeader>

    <div v-if="loading" class="loading">加载中...</div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else>
      <div v-if="!versions.length" class="empty-state compact-empty">
        <strong>该合集中没有数据集</strong>
        <span>请先在「数据管理」中上传数据集。如果数据集名称符合命名规范（如 helmet_train、helmet_val），系统会自动归入合集。</span>
        <button class="primary-action mt-12" @click="router.push('/datasets')">前往数据管理</button>
      </div>
      <template v-else>
      <div class="workspace-summary">
        <div><span>数据集</span><strong>{{ versions.length }} 个</strong></div>
        <div><span>总图片</span><strong>{{ totalImages }} 张</strong></div>
        <div><span>类别数</span><strong>{{ versions[0]?.class_count || 0 }} 类</strong></div>
        <div>
          <span>标注状态</span>
          <strong v-if="allAnnotated">✓ 全部已标注</strong>
          <strong v-else class="annotation-progress">标注 {{ totalReviewed }}/{{ totalImages }}</strong>
        </div>
      </div>

      <div v-if="missingDtypes.length" class="missing-dtype-bar">
        <span v-for="m in missingDtypes" :key="m.dtype">⚠ 还没有<b>{{ m.label }}</b>，训练前请先指定一个</span>
      </div>

      <div class="workspace-dataset-grid">
        <div v-for="item in latestVersions" :key="item.id" class="workspace-dataset-card">
          <div class="wd-card-head">
            <template v-if="editingId === item.id">
              <input v-model="editingName" class="inline-rename-input" @keyup.enter="saveRename(item)" @keyup.escape="cancelRename" @blur="saveRename(item)" />
            </template>
            <template v-else>
              <strong class="dataset-name" @click.stop="startRename(item)">{{ item.dataset_name }}</strong>
              <button class="icon-btn-sm" title="重命名" @click.stop="startRename(item)">✎</button>
            </template>
            <div class="card-badge-row">
              <ChipBadge :tone="typeTone(item)">{{ typeLabel(item) }}</ChipBadge>
              <ChipBadge v-if="item.latest_export_id" tone="info">已导出</ChipBadge>
            </div>
          </div>
          <div class="wd-card-stats">
            <div><span>版本</span><b>{{ item.version }}</b></div>
            <div><span>图片</span><b>{{ item.image_count }}</b></div>
            <div><span>类别</span><b>{{ item.class_count }}</b></div>
            <div v-if="item.instance_count"><span>实例</span><b>{{ item.instance_count }}</b></div>
          </div>
          <div class="wd-card-dtype">
            <label class="dtype-label">用途</label>
            <select class="dtype-select" :value="item.dtype || ''" @change.stop="changeDtype(item, $event.target.value)">
              <option value="">全量</option>
              <option value="train">训练集</option>
              <option value="val">验证集</option>
              <option value="predict">推理集</option>
            </select>
            <span v-if="dtypeChanging === item.id" class="muted-text">保存中...</span>
          </div>
          <div v-if="isAnnotation(item) && Number(item.pending_count) > 0" class="annotation-progress" style="margin-bottom:6px">
            待标注 {{ Number(item.pending_count) }} 张 / 已标注 {{ Number(item.reviewed_count || 0) }} 张 — 共 {{ item.image_count }} 张
          </div>
          <div v-if="isAnnotation(item) && Number(item.pending_count) === 0 && Number(item.image_count) > 0" class="annotation-done" style="margin-bottom:6px">✓ 全部已标注（{{ item.image_count }} 张）</div>
          <div class="wd-card-actions">
            <button class="secondary-action small-action" @click.stop="openPreview(item)">预览</button>
            <RouterLink v-if="isAnnotation(item)" class="secondary-action small-action" :to="{ path: '/annotation', query: { version: item.id } }" @click.stop>标注</RouterLink>
            <button v-if="isAnnotation(item) && splitEligibleCount(item) > 0" class="secondary-action small-action" @click.stop="openSplitDialog(item)">拆分已标注</button>
            <button class="secondary-action small-action danger-action" @click.stop="confirmDeleteVersion(item)">删除</button>
          </div>
        </div>
      </div>
      </template>
    </template>

    <!-- 拆分对话框 -->
    <div v-if="showSplitDialog" class="dialog-overlay" @click.self="closeSplitDialog">
      <div class="dialog import-dialog">
        <h3>拆分为独立数据集</h3>
        <p class="helper-text">
          将「{{ splitTarget?.dataset_name }} / {{ splitTarget?.version }}」中可训练的 {{ splitAvailableCount }} 张已复核图片拆成独立 train / val / test 数据集。
        </p>
        <div class="segmented" style="margin-bottom:10px">
          <button :class="{ active: splitMode === 'count' }" @click="splitMode = 'count'">按数量</button>
          <button :class="{ active: splitMode === 'ratio' }" @click="splitMode = 'ratio'">按比例</button>
        </div>
        <template v-if="splitMode === 'count'">
          <div class="split-ratio-row">
            <label>Train 张数 <input v-model.number="splitCount.train" type="number" min="0" /></label>
            <label>Val 张数 <input v-model.number="splitCount.val" type="number" min="0" /></label>
            <label>Test 张数 <input v-model.number="splitCount.test" type="number" min="0" /></label>
          </div>
          <div class="split-summary">
            <span>可用 {{ splitAvailableCount }} 张，使用 <strong>{{ splitCountTotal }}</strong> 张，剩余 {{ Math.max(0, splitAvailableCount - splitCountTotal) }} 张继续留在标注集</span>
          </div>
        </template>
        <template v-else>
          <div class="split-ratio-row">
            <label>Train % <input v-model.number="splitRatio.train" type="number" min="10" max="90" step="5" /></label>
            <label>Val % <input v-model.number="splitRatio.val" type="number" min="0" max="80" step="5" /></label>
            <label>Test % <input v-model.number="splitRatio.test" type="number" min="0" max="80" step="5" /></label>
          </div>
        </template>
        <p v-if="splitError" class="error">{{ splitError }}</p>
        <div class="dialog-actions">
          <button class="secondary-action" @click="closeSplitDialog">取消</button>
          <button class="primary-action" :disabled="splitting" @click="submitSplitInto">{{ splitting ? '处理中...' : '确认拆分' }}</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChipBadge from '../components/ChipBadge.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import PageHeader from '../components/PageHeader.vue'
import { listVersions, updateDataset, deleteDatasetVersion, splitIntoIndependent, changeDatasetDtype } from '../api/datasets.js'

const route = useRoute()
const router = useRouter()
const workspaceName = decodeURIComponent(route.params.name || '')

const confirmDialog = reactive({ visible: false, title: '', message: '', onConfirm: () => {} })
const loading = ref(true)
const error = ref('')
const versions = ref([])
const editingId = ref(null)
const editingName = ref('')
const showSplitDialog = ref(false)
const splitTarget = ref(null)
const splitting = ref(false)
const splitError = ref('')
const splitMode = ref('count')
const splitRatio = reactive({ train: 70, val: 20, test: 10 })
const splitCount = reactive({ train: 0, val: 0, test: 0 })
const splitCountTotal = computed(() => (splitCount.train || 0) + (splitCount.val || 0) + (splitCount.test || 0))
const splitAvailableCount = computed(() => splitTarget.value ? splitEligibleCount(splitTarget.value) : 0)
const dtypeChanging = ref(null)

async function changeDtype(item, newDtype) {
  if (!newDtype) {
    // 清空 dtype
    try {
      dtypeChanging.value = item.id
      await changeDatasetDtype(item.id, '')
      await load()
    } catch (err) {
      alert(err?.message || '清除类型失败')
    } finally {
      dtypeChanging.value = null
    }
    return
  }
  try {
    dtypeChanging.value = item.id
    await changeDatasetDtype(item.id, newDtype)
    await load()
  } catch (err) {
    alert(err?.message || '设置类型失败')
  } finally {
    dtypeChanging.value = null
  }
}

const latestVersions = computed(() => {
  // 按 dataset_name 分组，每组只保留最新版本
  const map = {}
  for (const v of versions.value) {
    const key = v.dataset_name
    if (!map[key] || v.id > map[key].id) map[key] = v
  }
  // 排序：原始数据在前，然后 train/val/test
  const order = { '': 0, '_train': 1, '_val': 2, '_test': 3, '_inference': 4 }
  return Object.values(map).sort((a, b) => {
    const sa = Object.keys(order).find(k => a.dataset_name.endsWith(k)) || ''
    const sb = Object.keys(order).find(k => b.dataset_name.endsWith(k)) || ''
    return (order[sa] || 0) - (order[sb] || 0)
  })
})

const totalImages = computed(() => versions.value.reduce((s, v) => s + Number(v.image_count || 0), 0))
const totalReviewed = computed(() => versions.value.reduce((s, v) => s + Number(v.reviewed_count || 0), 0))
const allAnnotated = computed(() => versions.value.every(v => !isAnnotation(v) || v.pending_count === 0))

const DTYPE_NEEDED = ['train', 'val']
const DTYPE_LABELS_MAP = { train: '训练集', val: '验证集' }
const missingDtypes = computed(() => {
  const present = new Set()
  for (const v of versions.value) {
    let dt = (v.dtype || '').trim()
    if (!dt) {
      const n = v.dataset_name || ''
      if (n.endsWith('_train')) dt = 'train'
      else if (n.endsWith('_val')) dt = 'val'
    }
    if (dt) present.add(dt)
  }
  return DTYPE_NEEDED.filter(d => !present.has(d)).map(d => ({ dtype: d, label: DTYPE_LABELS_MAP[d] }))
})

function typeLabel(item) {
  const dt = item.dtype
  const map = { train: '训练集', val: '验证集', predict: '推理集' }
  if (map[dt]) return map[dt]
  const name = item.dataset_name || ''
  if (name.endsWith('_train')) return '训练集'
  if (name.endsWith('_val')) return '验证集'
  if (name.endsWith('_predict')) return '推理集'
  return '全量'
}
function typeTone(item) {
  const dt = item.dtype
  if (dt === 'train') return 'info'
  if (dt === 'val') return 'success'
  if (dt === 'test') return 'warning'
  if (dt === 'inference') return 'danger'
  if (dt === 'annotation') return 'warning'
  const name = item.dataset_name || ''
  if (name.endsWith('_train')) return 'info'
  if (name.endsWith('_val')) return 'success'
  if (name.endsWith('_test')) return 'warning'
  if (name.endsWith('_inference')) return 'danger'
  return 'default'
}
function isAnnotation(item) {
  return (item.dtype || item.status) === 'annotation'
}

function splitEligibleCount(item) {
  return isAnnotation(item) ? Number(item.reviewed_count || 0) : Number(item.image_count || 0)
}

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const all = (await listVersions()).items
    // 优先通过 collection_name 匹配（与 DatasetsPage 的分组逻辑一致），
    // 没有 collection_name 时回退到名称去后缀匹配
    versions.value = all.filter(v => {
      const collName = (v.collection_name || '').trim()
      if (collName) return collName === workspaceName
      const baseName = (v.dataset_name || '').replace(/_(train|val|test|inference)$/, '')
      // 也支持完整名称匹配（如 dataset 名字就直接是合集名）
      return baseName === workspaceName || v.dataset_name === workspaceName
    })
  } catch (err) {
    error.value = err?.message || '加载工作台数据失败，请检查后端服务是否正常运行'
  } finally {
    loading.value = false
  }
}

function openPreview(item) {
  window.location.href = '/dataset/' + item.id
}

function startRename(item) {
  editingId.value = item.id
  editingName.value = item.dataset_name
  nextTick(() => {
    const input = document.querySelector('.inline-rename-input')
    if (input) { input.focus(); input.select() }
  })
}
function cancelRename() { editingId.value = null; editingName.value = '' }
async function saveRename(item) {
  const name = editingName.value.trim()
  if (!name || name === item.dataset_name) { cancelRename(); return }
  try {
    console.log('Renaming:', item.dataset_id, 'to', name)
    await updateDataset(item.dataset_id, { name, description: '' })
    console.log('Rename success, reloading...')
    await load()
  } catch (err) {
    console.error('Rename failed:', err)
    alert(err?.message || '重命名失败')
  }
  editingId.value = null
}

function confirmDeleteVersion(item) {
  confirmDialog.title = '删除版本'
  confirmDialog.message = `确认删除「${item.dataset_name} / ${item.version}」？`
  confirmDialog.onConfirm = async () => {
    confirmDialog.visible = false
    try { await deleteDatasetVersion(item.id); await load() } catch {}
  }
  confirmDialog.visible = true
}

function openSplitDialog(item) {
  splitTarget.value = item
  splitCount.train = 0; splitCount.val = 0; splitCount.test = 0
  splitMode.value = 'count'
  splitError.value = ''
  showSplitDialog.value = true
}
function closeSplitDialog() { showSplitDialog.value = false; splitting.value = false }

async function submitSplitInto() {
  splitError.value = ''
  if (!splitTarget.value) return
  const totalImages = splitAvailableCount.value
  if (totalImages <= 0) {
    splitError.value = '当前没有已复核图片可拆分，请先在标注工作台保存/复核一部分图片'
    return
  }
  try {
    splitting.value = true
    if (splitMode.value === 'count') {
      const total = (splitCount.train || 0) + (splitCount.val || 0) + (splitCount.test || 0)
      if (total <= 0) { splitError.value = '请至少指定一个拆分数量（train、val 或 test）'; return }
      if (total > totalImages) { splitError.value = `拆分张数总和（${total}）超过了数据集总数（${totalImages} 张），请调整数量`; return }
      await splitIntoIndependent(splitTarget.value.id, { train_count: splitCount.train, val_count: splitCount.val, test_count: splitCount.test, only_reviewed: isAnnotation(splitTarget.value) })
    } else {
      const sum = splitRatio.train + splitRatio.val + splitRatio.test
      if (Math.abs(sum - 100) > 1) { splitError.value = `比例之和必须为 100%，当前为 ${sum}%`; return }
      await splitIntoIndependent(splitTarget.value.id, { train_ratio: splitRatio.train / 100, val_ratio: splitRatio.val / 100, test_ratio: splitRatio.test / 100, only_reviewed: isAnnotation(splitTarget.value) })
    }
    showSplitDialog.value = false
    await load()
  } catch (err) { splitError.value = err?.message || '拆分失败' }
  finally { splitting.value = false }
}
</script>
