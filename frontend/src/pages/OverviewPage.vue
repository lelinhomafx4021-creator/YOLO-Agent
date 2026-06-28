<template>
  <section class="page compact-page">
    <PageHeader title="全局概览" subtitle="先看平台当前状态，再决定去训练、整理数据还是处理模型。" />

    <div v-if="loading" class="loading">加载中...</div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else>
      <section class="card overview-hero">
        <div class="overview-hero-main">
          <span class="overview-hero-kicker">平台状态</span>
          <h2>{{ heroTitle }}</h2>
          <p>{{ heroSubtitle }}</p>

          <div class="overview-hero-actions">
            <RouterLink to="/projects" class="primary-action small-action">
              <AppIcon name="projects" />
              <span>进入项目</span>
            </RouterLink>
            <RouterLink to="/datasets" class="secondary-action small-action">
              <AppIcon name="database" />
              <span>整理数据</span>
            </RouterLink>
            <RouterLink to="/training" class="secondary-action small-action">
              <AppIcon name="train" />
              <span>查看训练</span>
            </RouterLink>
          </div>
          </div>

        <div class="overview-hero-side">
          <div class="overview-hero-signal">
            <span>{{ isMultiProject ? '当前高点模型' : '最佳模型' }}</span>
            <strong>{{ bestModel ? displayModelName(bestModel) : '暂无' }}</strong>
            <small>{{ bestModelSignalText }}</small>
          </div>
          <div class="overview-hero-signal">
            <span>{{ isMultiProject ? '最活跃项目' : '最新训练' }}</span>
            <strong>{{ isMultiProject ? (topProject?.name || '-') : displayTrainingName(latestRun) }}</strong>
            <small>{{ isMultiProject ? topProjectSignalText : latestRunSignalText }}</small>
          </div>
          <div class="overview-hero-signal">
            <span>待处理图片</span>
            <strong>{{ fmt(totalPendingImages) }}</strong>
            <small>{{ annotationCoverage != null ? `已复核覆盖 ${annotationCoverage}%` : '当前没有标注进度统计' }}</small>
          </div>
        </div>
      </section>

      <div class="metric-grid five compact-metric-grid">
        <div class="metric-card">
          <span>项目</span>
          <strong>{{ overview.project_count || 0 }}</strong>
          <small>{{ projectScaleText }}</small>
        </div>
        <div class="metric-card">
          <span>数据集</span>
          <strong>{{ overview.dataset_count }}</strong>
          <small>{{ largestVersion ? `最大 ${largestVersion.dataset_name} / ${largestVersion.version}` : '还没有版本记录' }}</small>
        </div>
        <div class="metric-card highlight">
          <span>图片</span>
          <strong>{{ fmt(overview.total_images) }}</strong>
          <small>{{ avgImagesPerDataset ? `平均每集 ${fmt(avgImagesPerDataset)}` : '等待数据导入' }}</small>
        </div>
        <div class="metric-card">
          <span>训练</span>
          <strong>{{ overview.training_count }}</strong>
          <small>{{ runningRunCount ? `${runningRunCount} 个任务运行中` : '当前没有运行中的任务' }}</small>
        </div>
        <div class="metric-card">
          <span>模型</span>
          <strong>{{ overview.model_count || 0 }}</strong>
          <small>{{ bestModel ? `最佳 ${percent(bestModel.map50_95)}` : '还没有模型指标' }}</small>
        </div>
      </div>

      <div class="overview-main-grid">
        <section class="card section-pad">
          <CardTitle title="当前关注" right="优先处理有影响的信号" />
          <div class="overview-focus-list">
            <RouterLink
              v-for="item in focusItems"
              :key="item.label"
              :to="item.to"
              class="overview-focus-item"
            >
              <span class="overview-focus-icon" :class="`tone-${item.tone}`">
                <AppIcon :name="item.icon" />
              </span>
              <div class="overview-focus-copy">
                <strong>{{ item.label }}</strong>
                <span>{{ item.description }}</span>
              </div>
              <em>{{ item.value }}</em>
            </RouterLink>
          </div>
        </section>

        <section class="card section-pad">
          <CardTitle title="数据资产" right="规模与标注进度" />
          <div class="overview-asset-grid">
            <div class="overview-asset-card">
              <span>最大数据集</span>
              <strong>{{ largestVersion ? `${largestVersion.dataset_name} / ${largestVersion.version}` : '-' }}</strong>
              <small>{{ largestVersion ? `${fmt(largestVersion.image_count)} 张图片` : '等待导入' }}</small>
            </div>
            <div class="overview-asset-card">
              <span>待处理标注</span>
              <strong>{{ fmt(totalPendingImages) }}</strong>
              <small>{{ totalPendingDatasets }} 个数据集仍有未完成图片</small>
            </div>
            <div class="overview-asset-card">
              <span>已复核图片</span>
              <strong>{{ fmt(totalReviewedImages) }}</strong>
              <small>{{ annotationCoverage != null ? `覆盖率 ${annotationCoverage}%` : '暂无可计算进度' }}</small>
            </div>
            <div class="overview-asset-card">
              <span>平均规模</span>
              <strong>{{ avgImagesPerDataset ? fmt(avgImagesPerDataset) : '-' }}</strong>
              <small>每个数据集平均图片数</small>
            </div>
          </div>
        </section>
      </div>

      <div class="overview-panels overview-panels--split">
        <section class="card section-pad">
          <CardTitle title="最近训练" :right="recentRuns.length ? `${recentRuns.length} 条记录` : ''" />
          <div v-if="recentRuns.length" class="table-card compact-table">
            <table>
              <thead>
                <tr>
                  <th>任务</th>
                  <th>数据集</th>
                  <th>状态</th>
                  <th>mAP50</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in recentRuns.slice(0, 5)" :key="r.run_id">
                  <td>
                    <RouterLink :to="`/training/${r.id}`">
                      <strong>{{ displayTrainingName(r) }}</strong>
                    </RouterLink>
                    <div class="table-subtext">{{ r.output_model_display_name || r.technical_run_id || '未注册模型' }}</div>
                  </td>
                  <td>{{ r.dataset_display_name || r.dataset_name || '-' }}</td>
                  <td><span :class="['chip', statusChip(r.status)]">{{ statusLabel(r.status) }}</span></td>
                  <td>{{ percent(r.map50) }}</td>
                  <td class="table-action-cell">
                    <RouterLink :to="`/training/${r.id}`" class="secondary-action small-action">详情</RouterLink>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state compact-empty"><span>还没有训练记录</span></div>
        </section>

        <section class="card section-pad">
          <CardTitle title="模型看板" :right="recentModels.length ? `近 ${recentModels.length} 个模型` : ''" />
          <div v-if="recentModels.length" class="overview-model-board">
            <RouterLink
              v-for="(model, index) in rankedModels"
              :key="`${model.run_id}-${index}`"
              to="/registry"
              class="overview-model-row"
            >
              <div class="overview-model-rank">{{ index + 1 }}</div>
              <div class="overview-model-copy">
                <strong>{{ displayModelName(model) }}</strong>
                <span>{{ model.project_name || '未关联项目' }}</span>
              </div>
              <div class="overview-model-metric">
                <b>{{ percent(model.map50_95) }}</b>
                <small>{{ model.is_production ? '生产' : '归档' }}</small>
              </div>
            </RouterLink>
          </div>
          <div v-else class="empty-state compact-empty"><span>还没有模型记录</span></div>
        </section>
      </div>

      <div class="quick-entry-row">
        <RouterLink to="/datasets" class="quick-entry"><AppIcon name="database" /> 数据管理</RouterLink>
        <RouterLink to="/projects" class="quick-entry"><AppIcon name="projects" /> 项目工作台</RouterLink>
        <RouterLink to="/registry" class="quick-entry"><AppIcon name="model" /> 模型仓库</RouterLink>
        <RouterLink to="/agent" class="quick-entry"><AppIcon name="agent" /> Agent</RouterLink>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onActivated, onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import CardTitle from '../components/CardTitle.vue'
import AppIcon from '../components/AppIcon.vue'
import { getOverview, listVersions } from '../api/datasets'
import { listProjects } from '../api/projects'
import { displayModelName, displayTrainingName } from '../utils.js'

const loading = ref(true)
const error = ref('')
const overview = ref({
  project_count: 0,
  dataset_count: 0,
  total_images: 0,
  training_count: 0,
  model_count: 0,
  recent_runs: [],
  recent_models: [],
})
const datasetVersions = ref([])
const projects = ref([])

onMounted(() => load())
onActivated(() => load({ silent: true }))

async function load(options = {}) {
  const { silent = false } = options
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [overviewResult, versionResult, projectRows] = await Promise.all([
      getOverview(),
      listVersions(1, 200),
      listProjects(),
    ])
    overview.value = { ...overview.value, ...overviewResult }
    datasetVersions.value = versionResult.items || []
    projects.value = projectRows || []
  } catch (e) {
    error.value = e?.message || '加载概览数据失败'
  } finally {
    if (!silent) loading.value = false
  }
}

const recentRuns = computed(() => overview.value.recent_runs || [])
const recentModels = computed(() => overview.value.recent_models || [])
const rankedModels = computed(() => (
  [...recentModels.value].sort((a, b) => Number(b.map50_95 ?? -1) - Number(a.map50_95 ?? -1)).slice(0, 5)
))
const latestRun = computed(() => recentRuns.value[0] || null)
const bestModel = computed(() => rankedModels.value[0] || null)
const isMultiProject = computed(() => Number(overview.value.project_count || 0) > 1)
const topProject = computed(() => {
  if (!projects.value.length) return null
  return [...projects.value].sort((a, b) => {
    const aWeight = Number(a.training_count || 0) * 3 + Number(a.model_count || 0) * 2 + Number(a.evaluation_count || 0)
    const bWeight = Number(b.training_count || 0) * 3 + Number(b.model_count || 0) * 2 + Number(b.evaluation_count || 0)
    return bWeight - aWeight
  })[0]
})
const runningRunCount = computed(() => recentRuns.value.filter(item => item.status === 'running').length)
const totalPendingImages = computed(() => datasetVersions.value.reduce((sum, item) => sum + Number(item.pending_count || 0), 0))
const totalReviewedImages = computed(() => datasetVersions.value.reduce((sum, item) => sum + Number(item.reviewed_count || 0), 0))
const totalPendingDatasets = computed(() => datasetVersions.value.filter(item => Number(item.pending_count || 0) > 0).length)
const avgImagesPerDataset = computed(() => {
  if (!overview.value.dataset_count) return 0
  return Math.round(Number(overview.value.total_images || 0) / Number(overview.value.dataset_count || 1))
})
const largestVersion = computed(() => {
  if (!datasetVersions.value.length) return null
  return [...datasetVersions.value].sort((a, b) => Number(b.image_count || 0) - Number(a.image_count || 0))[0]
})
const annotationCoverage = computed(() => {
  const total = totalPendingImages.value + totalReviewedImages.value
  if (!total) return null
  return Math.round((totalReviewedImages.value / total) * 100)
})
const projectScaleText = computed(() => {
  const count = Number(overview.value.project_count || 0)
  if (!count) return '等待创建项目'
  if (count === 1) return '当前集中在 1 个项目'
  return `当前分布在 ${count} 个项目`
})
const heroTitle = computed(() => {
  if (isMultiProject.value) return `当前有 ${overview.value.project_count || 0} 个项目并行运行`
  if (bestModel.value) return `当前最佳模型是 ${displayModelName(bestModel.value)}`
  if (latestRun.value) return `最近训练已更新到 ${displayTrainingName(latestRun.value)}`
  return '平台还在初始化阶段'
})
const heroSubtitle = computed(() => {
  if (isMultiProject.value) {
    const bestText = bestModel.value
      ? `当前最高模型来自 ${bestModel.value.project_name || '未关联项目'}，mAP50-95 为 ${percent(bestModel.value.map50_95)}`
      : '当前还没有形成可比较的模型高点'
    const activeText = topProject.value
      ? `最活跃项目是 ${topProject.value.name}`
      : '项目活跃度还在累积'
    return `${bestText}。${activeText}。当前仍有 ${fmt(totalPendingImages.value)} 张图片待继续处理。`
  }
  if (bestModel.value && latestRun.value) {
    return `最新训练 ${statusLabel(latestRun.value.status)}，最佳模型 mAP50-95 为 ${percent(bestModel.value.map50_95)}。当前仍有 ${fmt(totalPendingImages.value)} 张图片待继续处理。`
  }
  if (latestRun.value) {
    return `最近一次训练来自 ${latestRun.value.project_name || '未关联项目'}，状态为 ${statusLabel(latestRun.value.status)}。`
  }
  return '建议先整理一个可训练数据集，再开始训练和模型归档。'
})
const bestModelSignalText = computed(() => {
  if (!bestModel.value) return '还没有可比较的模型记录'
  const scope = bestModel.value.project_name ? `来自 ${bestModel.value.project_name}` : '未关联项目'
  return `${scope} / mAP50-95 ${percent(bestModel.value.map50_95)}`
})
const latestRunSignalText = computed(() => {
  if (!latestRun.value) return '还没有训练记录'
  return `${statusLabel(latestRun.value.status)} / ${percent(latestRun.value.map50)}`
})
const topProjectSignalText = computed(() => {
  if (!topProject.value) return '还没有项目活跃度数据'
  return `${topProject.value.training_count || 0} 次训练 / ${topProject.value.model_count || 0} 个模型 / ${topProject.value.evaluation_count || 0} 次验证`
})
const focusItems = computed(() => {
  const items = [
    {
      icon: runningRunCount.value ? 'activity' : 'train',
      tone: runningRunCount.value ? 'info' : 'neutral',
      label: '训练状态',
      description: runningRunCount.value ? '有任务正在占用算力，适合先观察结果。' : '当前没有运行中的训练任务。',
      value: runningRunCount.value ? `${runningRunCount.value} 个运行中` : '空闲',
      to: '/training',
    },
    {
      icon: totalPendingImages.value ? 'warning' : 'check',
      tone: totalPendingImages.value ? 'warning' : 'success',
      label: '标注处理',
      description: totalPendingImages.value ? '仍有图片未复核，训练前建议先收敛数据质量。' : '当前标注进度比较干净。',
      value: totalPendingImages.value ? `${fmt(totalPendingImages.value)} 张待处理` : '已处理完成',
      to: '/datasets',
    },
    {
      icon: 'model',
      tone: 'info',
      label: '模型状态',
      description: bestModel.value
        ? `${isMultiProject.value ? '当前最高模型仅代表对应项目的上限，可继续到模型库按项目查看。' : '可以直接从这里继续验证、导出或部署。'}`
        : '还没有形成可用模型版本。',
      value: bestModel.value ? `${percent(bestModel.value.map50_95)}${bestModel.value.project_name ? ` / ${bestModel.value.project_name}` : ''}` : '暂无模型',
      to: '/registry',
    },
    {
      icon: 'agent',
      tone: 'neutral',
      label: 'Agent 分析',
      description: '让 Agent 结合最近训练和模型结果给出下一步建议。',
      value: latestRun.value ? displayTrainingName(latestRun.value) : '就绪',
      to: '/agent',
    },
  ]
  return items
})

function fmt(v) {
  return v == null ? '-' : Number(v).toLocaleString()
}

function percent(v) {
  return v == null ? '-' : `${(Number(v) * 100).toFixed(1)}%`
}

function statusLabel(s) {
  return {
    created: '等待中',
    running: '运行中',
    completed: '已完成',
    failed: '失败',
  }[s] || s
}

function statusChip(s) {
  return {
    running: 'info',
    completed: 'success',
    failed: 'danger',
  }[s] || ''
}

</script>

<style scoped>
.overview-hero {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(320px, 0.95fr);
  gap: 18px;
  padding: 18px 20px;
  margin-bottom: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 252, 255, 0.98)),
    radial-gradient(circle at top right, rgba(126, 188, 255, 0.14), transparent 32%);
}

.overview-hero-main {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.overview-hero-kicker {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(105, 183, 255, 0.12);
  color: var(--primary-ink);
  font-size: 11px;
  font-weight: 600;
}

.overview-hero-main h2 {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  color: var(--heading);
}

.overview-hero-main p {
  margin: 0;
  max-width: 720px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.65;
}

.overview-hero-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 2px;
}

.overview-hero-side {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.overview-hero-signal {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(105, 183, 255, 0.18);
  box-shadow: 0 10px 24px rgba(105, 183, 255, 0.08);
}

.overview-hero-signal span {
  font-size: 11px;
  color: var(--muted);
}

.overview-hero-signal strong {
  font-size: 14px;
  color: var(--heading);
  line-height: 1.35;
}

.overview-hero-signal small {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.45;
}

.overview-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 12px;
  margin-bottom: 12px;
}

.overview-focus-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.overview-focus-item {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.76);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.overview-focus-item:hover {
  border-color: rgba(105, 183, 255, 0.34);
  box-shadow: 0 12px 22px rgba(105, 183, 255, 0.1);
  transform: translateY(-1px);
}

.overview-focus-icon {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(105, 183, 255, 0.18);
  color: var(--primary-ink);
}

.overview-focus-icon.tone-warning {
  color: #B57718;
  background: #FFF8E8;
  border-color: #F5D9A8;
}

.overview-focus-icon.tone-success {
  color: #226B4B;
  background: #EFFAF4;
  border-color: #CBE9D6;
}

.overview-focus-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.overview-focus-copy strong {
  font-size: 13px;
  color: var(--heading);
}

.overview-focus-copy span {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.45;
}

.overview-focus-item em {
  font-style: normal;
  color: var(--primary-ink);
  font-weight: 700;
  font-size: 12px;
  white-space: nowrap;
}

.overview-asset-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.overview-asset-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.76);
  border: 1px solid var(--line-soft);
}

.overview-asset-card span {
  font-size: 11px;
  color: var(--muted);
}

.overview-asset-card strong {
  font-size: 14px;
  color: var(--heading);
  line-height: 1.35;
}

.overview-asset-card small {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.45;
}

.overview-panels--split {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  gap: 12px;
  margin-bottom: 12px;
}

.table-subtext {
  margin-top: 2px;
  font-size: 11px;
  color: var(--muted);
}

.table-action-cell {
  width: 72px;
  text-align: right;
}

.overview-model-board {
  display: grid;
  grid-template-columns: 1fr;
  gap: 8px;
}

.overview-model-row {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 11px 12px;
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.78);
  transition: border-color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
}

.overview-model-row:hover {
  border-color: rgba(105, 183, 255, 0.34);
  box-shadow: 0 12px 22px rgba(105, 183, 255, 0.1);
  transform: translateY(-1px);
}

.overview-model-rank {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(105, 183, 255, 0.12);
  color: var(--primary-ink);
  font-size: 12px;
  font-weight: 700;
}

.overview-model-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.overview-model-copy strong {
  font-size: 13px;
  color: var(--heading);
  line-height: 1.35;
}

.overview-model-copy span {
  font-size: 11px;
  color: var(--muted);
}

.overview-model-metric {
  text-align: right;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.overview-model-metric b {
  font-size: 14px;
  color: var(--primary-ink);
}

.overview-model-metric small {
  font-size: 11px;
  color: var(--muted);
}

@media (max-width: 1180px) {
  .overview-hero,
  .overview-main-grid,
  .overview-panels--split {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .overview-asset-grid {
    grid-template-columns: 1fr;
  }

  .overview-focus-item,
  .overview-model-row {
    grid-template-columns: 30px minmax(0, 1fr);
  }

  .overview-focus-item em,
  .overview-model-metric {
    grid-column: 2;
    text-align: left;
  }
}
</style>
