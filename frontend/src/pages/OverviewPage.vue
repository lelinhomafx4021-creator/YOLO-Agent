<template>
  <section class="page compact-page">
    <PageHeader title="全局概览" subtitle="平台数据、训练任务、模型仓库的整体状态" />

    <div v-if="loading" class="loading">加载中...</div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else>
      <!-- 核心数据 -->
      <div class="overview-stats">
        <div class="overview-stat"><em>项目</em><b>{{ overview.project_count || 0 }}</b></div>
        <div class="overview-stat"><em>数据集</em><b>{{ overview.dataset_count }}</b></div>
        <div class="overview-stat"><em>图片</em><b>{{ fmt(overview.total_images) }}</b></div>
        <div class="overview-stat"><em>训练</em><b>{{ overview.training_count }}</b></div>
        <div class="overview-stat"><em>模型</em><b>{{ overview.model_count || 0 }}</b></div>
      </div>

      <div class="overview-panels">
        <!-- 最近训练 -->
        <section class="card">
          <CardTitle title="最近训练" />
          <div v-if="recentRuns.length" class="table-card section-pad compact-table">
            <table>
              <thead><tr><th>产出模型</th><th>Run ID</th><th>项目</th><th>数据</th><th>状态</th><th>mAP50</th></tr></thead>
              <tbody>
                <tr v-for="r in recentRuns" :key="r.run_id">
                  <td><RouterLink :to="`/training/${r.id}`"><strong>{{ r.model_name || r.run_id }}</strong></RouterLink></td>
                  <td class="mono muted-text" style="font-size:10px">{{ r.run_id }}</td>
                  <td>{{ r.project_name || '-' }}</td>
                  <td>{{ r.dataset_name || '-' }}</td>
                  <td><span :class="['chip', statusChip(r.status)]">{{ statusLabel(r.status) }}</span></td>
                  <td>{{ percent(r.map50) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state compact-empty"><span>还没有训练记录</span></div>
        </section>

        <!-- 最近模型 -->
        <section class="card">
          <CardTitle title="最近模型" />
          <div v-if="(overview.recent_models || []).length" class="table-card section-pad compact-table">
            <table>
              <thead><tr><th>模型名</th><th>Run ID</th><th>项目</th><th>mAP50-95</th><th>状态</th></tr></thead>
              <tbody>
                <tr v-for="m in overview.recent_models" :key="m.run_id">
                  <td><RouterLink to="/registry"><strong>{{ m.model_name || m.run_id }}</strong></RouterLink></td>
                  <td class="mono muted-text">{{ m.run_id }}</td>
                  <td>{{ m.project_name || '-' }}</td>
                  <td>{{ percent(m.map50_95) }}</td>
                  <td><span :class="['chip', m.is_production ? 'success' : '']">{{ m.is_production ? '生产' : '归档' }}</span></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-state compact-empty"><span>还没有模型记录</span></div>
        </section>
      </div>

      <!-- 快捷入口 -->
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
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../components/PageHeader.vue'
import CardTitle from '../components/CardTitle.vue'
import AppIcon from '../components/AppIcon.vue'
import { getOverview } from '../api/datasets'

const loading = ref(true)
const error = ref('')
const overview = ref({ project_count:0, dataset_count:0, total_images:0, training_count:0, model_count:0, recent_runs:[], recent_models:[] })

onMounted(async () => {
  try { overview.value = { ...overview.value, ...(await getOverview()) } }
  catch (e) { error.value = e?.message || '加载概览数据失败' }
  finally { loading.value = false }
})

const recentRuns = computed(() => overview.value.recent_runs || [])

function fmt(v) { return v == null ? '-' : Number(v).toLocaleString() }
function percent(v) { return v == null ? '-' : `${(Number(v)*100).toFixed(1)}%` }
function statusLabel(s) { return { created:'等待中', running:'运行中', completed:'已完成', failed:'失败' }[s] || s }
function statusChip(s) { return { running:'info', completed:'success', failed:'danger' }[s] || '' }
</script>
