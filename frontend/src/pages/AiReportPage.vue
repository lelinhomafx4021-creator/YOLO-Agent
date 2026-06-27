<!--
 * @component AiReportPage
 * @description AI 分析报告页面。支持训练报告和评估报告两种类型。
 * 用户可通过切换标签和下拉框选择任务，查看 AI Agent 生成的分析报告。
-->
<template>
  <section class="page">
    <PageHeader title="AI 分析报告" subtitle="AI Agent 对训练/评估结果、数据质量和下一轮计划的分析">
      <div class="report-type-tabs">
        <button :class="['tab-btn', { active: reportType === 'training' }]" @click="switchType('training')">训练报告</button>
        <button :class="['tab-btn', { active: reportType === 'evaluation' }]" @click="switchType('evaluation')">评估报告</button>
      </div>
      <select v-model="selectedRunId" @change="loadReport">
        <option :value="null" disabled>{{ reportType === 'training' ? '选择训练任务' : '选择评估任务' }}</option>
        <option v-for="r in selectableRuns" :key="r.id" :value="r.id">{{ r.run_id }}</option>
      </select>
      <button class="secondary-action" @click="regenerate" :disabled="!selectedRunId"><AppIcon name="refresh" /> 重新生成</button>
    </PageHeader>

    <div v-if="loading" class="loading">加载中...</div>

    <template v-else-if="report">
      <div class="report-layout">
        <article class="card report-doc">
          <h2>{{ reportType === 'training' ? 'AI 训练复盘报告' : 'AI 评估分析报告' }}</h2>
          <p class="report-meta" v-if="report.record">
            Run ID：{{ report.record.run_id || report.record.evaluation_run_id || '-' }} · 报告类型：{{ reportType === 'training' ? '训练' : '评估' }}
          </p>
          <div class="report-body" v-html="renderedContent"></div>
        </article>

        <aside class="report-side">
          <MetricCard v-if="metrics.precision != null" title="Precision" :value="Number(metrics.precision).toFixed(3)" />
          <MetricCard v-if="metrics.recall != null" title="Recall" :value="Number(metrics.recall).toFixed(3)" />
          <MetricCard v-if="metrics.map50 != null" title="mAP50" :value="Number(metrics.map50).toFixed(3)" highlight />
          <MetricCard v-if="metrics.map50_95 != null" title="mAP50-95" :value="Number(metrics.map50_95).toFixed(3)" />
          <section class="card">
            <CardTitle title="行动清单" />
            <ActionItem text="查看训练日志定位问题" />
            <ActionItem text="对比历史模型指标" />
            <ActionItem text="打开标注质检修复数据" />
          </section>
        </aside>
      </div>
    </template>

    <p v-else class="loading">请选择一个任务查看 AI 报告</p>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import PageHeader from '../components/PageHeader.vue'
import MetricCard from '../components/MetricCard.vue'
import CardTitle from '../components/CardTitle.vue'
import ActionItem from '../components/ActionItem.vue'
import { listRuns } from '../api/training'
import { getReport, regenerateReport, getEvaluationReport, regenerateEvaluationReport } from '../api/reports'
import { listModels } from '../api/models'

const loading = ref(false)
const reportType = ref('training')  // 'training' | 'evaluation'
const trainingRuns = ref([])
const evaluationRuns = ref([])
const selectedRunId = ref(null)
const report = ref(null)
const metrics = ref({})

const selectableRuns = computed(() => reportType.value === 'training' ? trainingRuns.value : evaluationRuns.value)

onMounted(async () => {
  try {
    trainingRuns.value = (await listRuns()).items || []
  } catch (e) { console.error(e) }
})

async function switchType(type) {
  reportType.value = type
  selectedRunId.value = null
  report.value = null
  metrics.value = {}
  if (type === 'evaluation' && !evaluationRuns.value.length) {
    try {
      // 通过项目 API 获取评估列表需要先有项目，这里用现有 API
      const { get } = await import('../api/client.js')
      evaluationRuns.value = await get('/projects/1/evaluation-runs').catch(() => [])
    } catch { /* 无项目时忽略 */ }
  }
}

async function loadReport() {
  if (!selectedRunId.value) return
  loading.value = true
  try {
    if (reportType.value === 'training') {
      report.value = await getReport(selectedRunId.value)
      try {
        const models = (await listModels()).items || []
        const model = models.find(m => m.training_run_id === selectedRunId.value)
        if (model) {
          metrics.value = {
            precision: model.precision,
            recall: model.recall,
            map50: model.map50,
            map50_95: model.map50_95,
          }
        }
      } catch (e) { /* ignore */ }
    } else {
      report.value = await getEvaluationReport(selectedRunId.value)
      // 评估的指标从后端返回的 record 中获取（如果有的话）
    }
  } catch (e) {
    console.error(e)
    report.value = null
  } finally {
    loading.value = false
  }
}

async function regenerate() {
  if (!selectedRunId.value) return
  loading.value = true
  try {
    if (reportType.value === 'training') {
      report.value = await regenerateReport(selectedRunId.value)
    } else {
      report.value = await regenerateEvaluationReport(selectedRunId.value)
    }
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const renderedContent = computed(() => {
  if (!report.value || !report.value.content) return '<p>暂无内容</p>'
  let md = report.value.content
  md = md.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  md = md.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  md = md.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  md = md.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  md = md.replace(/`([^`]+)`/g, '<code>$1</code>')
  md = md.replace(/^- (.+)$/gm, '<li>$1</li>')
  md = md.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
  md = md.replace(/\n\n/g, '</p><p>')
  return '<p>' + md + '</p>'
})
</script>
