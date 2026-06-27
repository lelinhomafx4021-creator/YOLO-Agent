<!--
 * @component LabelAuditPage
 * @description 标注质检页面。用于对 YOLO 数据集版本进行质量审查，
 * 统计缺失 txt / 孤儿 txt / 异常 bbox / 空标注文件 / 类别不均衡等指标，
 * 展示 AI 质检建议及问题明细表格，帮助用户快速定位标注数据中的异常。
-->
<template>
  <!-- ====== 未选择版本：展示版本卡片网格 ====== -->
  <section v-if="!selectedVersionId" class="page">
    <PageHeader title="标注质检" subtitle="检查图片、YOLO txt、bbox 坐标和类别分布" />

    <div v-if="versions.length === 0" class="loading">暂无可用图集版本。</div>
    <p v-else-if="error" class="error">{{ error }}</p>
    <div v-else class="version-grid">
      <div
        v-for="version in versions"
        :key="version.id"
        class="version-card audit-card"
        @click="selectVersion(version)"
      >
        <div class="version-card-head">
          <strong>{{ version.dataset_name }}</strong>
          <ChipBadge :tone="versionStatusTone(version.status)">{{
            versionStatusLabel(version.status)
          }}</ChipBadge>
        </div>
        <div class="audit-card-strip">
          <span class="audit-stat" :class="{ danger: (version.missing_labels||0) > 0 }">
            <b>缺失</b> {{ version.missing_labels||0 }}
          </span>
          <span class="audit-stat" :class="{ danger: (version.orphan_labels||0) > 0 }">
            <b>孤立</b> {{ version.orphan_labels||0 }}
          </span>
          <span class="audit-stat" :class="{ danger: (version.invalid_bboxes||0) > 0 }">
            <b>异常</b> {{ version.invalid_bboxes||0 }}
          </span>
          <span class="audit-stat">
            <b>空标</b> {{ version.empty_labels||0 }}
          </span>
          <span class="audit-stat">
            <b>图片</b> {{ version.image_count||0 }}
          </span>
        </div>
        <div class="audit-health">
          <span class="health-score" :class="healthClass(version)">{{ healthScore(version) }}分</span>
        </div>
      </div>
    </div>
  </section>

  <!-- ====== 已选择版本：展示质检报告 ====== -->
  <section v-else class="page">
    <!-- 紧凑头部栏：返回按钮 + 版本名称 + 重新运行 -->
    <div class="audit-header-bar">
      <button class="back-btn" @click="clearSelection">&larr; 返回选择</button>
      <span class="audit-version-name">{{ selectedVersionName }}</span>
      <button class="primary-action" @click="loadAudit">重新运行质检</button>
    </div>

    <!-- 加载中状态 -->
    <div v-if="loading" class="loading">加载中...</div>

    <!-- 质检报告内容 -->
    <template v-else-if="audit">
      <!-- 五项核心指标卡片 -->
      <div class="metric-grid five">
        <MetricCard title="缺失 txt" :value="audit.missing_labels" :danger="audit.missing_labels > 0" />
        <MetricCard title="孤儿 txt" :value="audit.orphan_labels" :danger="audit.orphan_labels > 0" />
        <MetricCard title="异常 bbox" :value="audit.invalid_bboxes" :danger="audit.invalid_bboxes > 0" />
        <MetricCard title="空标注文件" :value="audit.empty_labels" />
        <MetricCard title="类别不均衡" :value="imbalanceLabel" :highlight="imbalanceLabel !== '均衡'" />
      </div>

      <!-- 图表与建议双栏布局 -->
      <div class="dashboard-grid">
        <!-- 左侧：类别分布柱状图 -->
        <section class="card">
          <CardTitle title="类别分布" right="实例数" />
          <BarChart v-if="chartData" :data="chartData" />
          <p v-else>无类别数据</p>
        </section>

        <!-- 右侧：AI 质检建议 -->
        <section class="card">
          <CardTitle title="AI 质检建议" :right="(audit.suggestions || []).length + ' 条建议'" />
          <div class="action-list spacious">
            <ActionItem v-for="(s, i) in audit.suggestions" :key="i" :text="s" />
          </div>
        </section>
      </div>

      <!-- 问题明细表格 -->
      <DataTableCard
        title="问题明细"
        :headers="['严重程度', '文件路径', '问题类型', '详情', '操作']"
        :rows="issueRows"
      />
    </template>

    <!-- 审计加载失败或无数据 -->
    <p v-else class="loading">该版本暂无质检数据，请点击「重新运行质检」生成报告。</p>
  </section>
</template>

<script setup>
// ============================================================
// 导入依赖
// ============================================================
import { ref, computed, onMounted, defineComponent } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import MetricCard from '../components/MetricCard.vue'
import CardTitle from '../components/CardTitle.vue'
import ActionItem from '../components/ActionItem.vue'
import DataTableCard from '../components/DataTableCard.vue'
import ChipBadge from '../components/ChipBadge.vue'
import { listVersions, getAudit } from '../api/datasets'

// ============================================================
// 响应式状态
// ============================================================
const loading = ref(false)
const error = ref('')
const versions = ref([])
const selectedVersionId = ref(null)
const audit = ref(null)

// ============================================================
// 生命周期
// ============================================================
onMounted(async () => {
  try {
    versions.value = (await listVersions()).items
  } catch (e) {
    error.value = e?.message || '加载版本列表失败'
  }
})

// ============================================================
// 计算属性
// ============================================================
const selectedVersionName = computed(() => {
  if (!selectedVersionId.value) return ''
  const v = versions.value.find(v => v.id === selectedVersionId.value)
  return v ? v.dataset_name + ' / ' + v.version : ''
})

const imbalanceLabel = computed(() => {
  if (!audit.value) return '-'
  const dist = audit.value.class_distribution || {}
  const values = Object.values(dist).filter(v => v > 0)
  if (values.length < 2) return '-'
  const maxVal = Math.max(...values)
  const minVal = Math.min(...values)
  return maxVal / Math.max(1, minVal) >= 5 ? '高' : '均衡'
})

const chartData = computed(() => {
  if (!audit.value) return null
  const dist = audit.value.class_distribution || {}
  const labels = Object.keys(dist)
  const values = Object.values(dist)
  if (!labels.length) return null
  const warns = []
  if (values.length > 1) {
    const maxVal = Math.max(...values)
    const minVal = Math.min(...values)
    if (maxVal / Math.max(1, minVal) >= 5) {
      labels.forEach((label, i) => {
        if (values[i] === minVal) warns.push(label)
      })
    }
  }
  return { labels, values, warns }
})

const issueRows = computed(() => {
  if (!audit.value) return []
  const rows = []
  for (const item of audit.value.invalid_items || []) {
    for (const err of item.errors) {
      rows.push(['高', item.label_path, '异常 bbox', err, '修复'])
    }
  }
  for (const path of audit.value.missing_label_images || []) {
    rows.push(['中', path, '缺失 txt', '没有对应标注文件', '去标注'])
  }
  for (const path of audit.value.orphan_label_files || []) {
    rows.push(['低', path, '孤儿 txt', '找不到对应图片', '删除'])
  }
  return rows.slice(0, 200)
})

// ============================================================
// 方法
// ============================================================

/** 点击版本卡片：选中版本并加载质检报告 */
function selectVersion(version) {
  selectedVersionId.value = version.id
  loadAudit()
}

/** 返回版本选择网格 */
function clearSelection() {
  selectedVersionId.value = null
  audit.value = null
}

/** 加载质检报告 */
async function loadAudit() {
  if (!selectedVersionId.value) return
  loading.value = true
  error.value = ''
  try {
    const result = await getAudit(selectedVersionId.value)
    audit.value = result.artifact || result
  } catch (e) {
    error.value = e?.message || '加载质检报告失败'
    audit.value = null
  } finally {
    loading.value = false
  }
}

/** 版本状态 → ChipBadge 色调映射 */
function versionStatusTone(status) {
  return (
    {
      imported: 'info',
      completed: 'success',
      failed: 'danger',
      running: 'warning',
    }[status] || 'info'
  )
}

/** 版本状态 → 中文标签映射 */
function versionStatusLabel(status) {
  return (
    {
      imported: '已导入',
      completed: '已完成',
      failed: '已失败',
      running: '进行中',
      annotation: '标注中',
    }[status] || status || '已导入'
  )
}

function healthScore(v) {
  const issues = (v.missing_labels||0) + (v.orphan_labels||0) + (v.invalid_bboxes||0) + (v.empty_labels||0)
  return Math.max(0, 100 - issues * 20)
}
function healthClass(v) {
  const s = healthScore(v)
  return s >= 80 ? 'good' : s >= 50 ? 'warn' : 'bad'
}

// ============================================================
// 内联柱状图组件（BarChart）
// ============================================================
const BarChart = defineComponent({
  props: {
    data: { type: Object, default: null },
  },
  setup(props) {
    const bars = computed(() => {
      if (!props.data) return []
      const { labels = [], values = [], warns = [] } = props.data
      return labels.map((label, i) => ({
        label,
        value: values[i] ?? 0,
        warn: warns.includes(label),
      }))
    })

    function barPercent(value) {
      const max = Math.max(...(props.data?.values || [1]), 1)
      return Math.max(3, Math.round((value / max) * 100))
    }

    return { bars, barPercent }
  },
})
</script>

<style scoped>
/* ===== 紧凑头部栏 ===== */
.audit-header-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 0 0 12px;
  border-bottom: 1px solid var(--border-light, #D4E0D4);
}

.back-btn {
  background: none;
  border: none;
  font-size: 14px;
  color: var(--primary, #5B7553);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
  white-space: nowrap;
}

.back-btn:hover {
  background: var(--bg-soft, #EFF3ED);
}

.audit-version-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text, #1e1b19);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===== 柱状图容器 ===== */
.bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.bars > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bars span {
  width: 80px;
  text-align: right;
  font-size: 13px;
  color: #555;
  flex-shrink: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bars b {
  display: inline-block;
  height: 14px;
  background: var(--green);
  border-radius: 99px;
  transition: width 0.3s ease;
  min-width: 4px;
}

.bars b.warn {
  background: var(--primary);
}

.bars em {
  font-size: 13px;
  color: #333;
  font-style: normal;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
