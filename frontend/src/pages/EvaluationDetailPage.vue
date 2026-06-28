<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>验证详情</h1>
        <p>查看正式验证结果、验证产物和逐图预测样本。</p>
      </div>
      <div class="header-actions">
        <RouterLink class="secondary-action" :to="run ? `/projects/${run.project_id}` : '/projects'">返回项目</RouterLink>
      </div>
    </div>

    <div v-if="loading" class="loading">正在加载验证详情...</div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else-if="run">
      <div class="metric-grid five compact-metric-grid">
        <div class="metric-card highlight">
          <span>状态</span>
          <strong>{{ statusText(run.status) }}</strong>
          <template v-if="run.status === 'running'">
            <div class="progress-bar-wrap" style="width:100%;margin-top:6px">
              <div class="progress-bar progress-bar-animated"></div>
            </div>
          </template>
        </div>
        <div class="metric-card"><span>Precision</span><strong>{{ fmtMetric(run.precision) }}</strong></div>
        <div class="metric-card"><span>Recall</span><strong>{{ fmtMetric(run.recall) }}</strong></div>
        <div class="metric-card"><span>mAP50</span><strong>{{ fmtMetric(run.map50) }}</strong></div>
        <div class="metric-card"><span>mAP50-95</span><strong>{{ fmtMetric(run.map50_95) }}</strong></div>
      </div>

      <section class="card section-pad compact-detail-section">
        <div class="detail-grid">
          <div class="info-item"><span>验证任务</span><strong>{{ run.run_id }}</strong></div>
          <div class="info-item"><span>来源训练</span><strong>{{ run.source_training_display_name || '无关联训练' }}</strong></div>
          <div class="info-item"><span>模型来源</span><strong>{{ displayModelName(run) }}</strong></div>
          <div class="info-item"><span>验证数据</span><strong>{{ displayDatasetName(run) }}</strong></div>
          <div class="info-item"><span>最佳权重</span><strong>{{ basename(run.best_pt_path) }}</strong></div>
          <div class="info-item wide"><span>运行目录</span><strong :title="run.run_path || ''">{{ basename(run.run_path) }}</strong></div>
        </div>
      </section>

      <!-- 验证日志 -->
      <section class="card section-pad compact-detail-section">
        <div class="card-title inner-title">
          <strong>验证日志</strong>
          <span>{{ statusText(run.status) }}</span>
        </div>
        <LogTerminal
          :logApi="fetchLogApi"
          :progressApi="fetchProgressApi"
          :pollInterval="2000"
          :externalStatus="run.status"
          @status-change="onLogStatusChange"
        />
      </section>

      <section class="card section-pad compact-detail-section">
        <div class="card-title"><strong>验证图表</strong><span>{{ imageArtifacts.length }}</span></div>
        <div v-if="imageArtifacts.length" class="eval-chart-grid">
          <a v-for="a in imageArtifacts" :key="a.relative_path" :href="a.url" target="_blank" class="eval-chart-item">
            <img :src="a.url" loading="lazy" /><span>{{ a.name }}</span>
          </a>
        </div>
        <div v-else class="empty-inline">暂无图表</div>

        <div class="card-title" style="margin-top:10px"><strong>数据文件</strong><span>{{ fileArtifacts.length }}</span></div>
        <div v-if="fileArtifacts.length" class="table-card compact-table">
          <table>
            <thead><tr><th>文件名</th><th>路径</th></tr></thead>
            <tbody>
              <tr v-for="a in fileArtifacts" :key="a.relative_path">
                <td><a :href="a.url" target="_blank" class="mono">{{ a.name }}</a></td>
                <td class="mono muted-text">{{ a.relative_path }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty-inline">暂无数据文件</div>

        <!-- Agent 快捷分析 -->
        <div class="agent-quick-section">
          <div class="card-title inner-title">
            <strong>AI 分析</strong>
            <span>让 Agent 帮你分析这次评估</span>
          </div>
          <div class="agent-quick-prompts">
            <button class="agent-prompt-btn" @click="askAgent('分析这次评估的结果，判断模型是否适合部署')">
              <AppIcon name="chart" /> 分析评估结果
            </button>
            <button class="agent-prompt-btn" @click="askAgent('检查评估中的漏检和误检模式，给出改进方向')">
              <AppIcon name="warning" /> 检查预测问题
            </button>
            <button class="agent-prompt-btn" @click="askAgent('基于评估指标，对比训练时的指标，判断是否有过拟合')">
              <AppIcon name="activity" /> 判断过拟合
            </button>
          </div>
        </div>

        <!-- AI 评估报告 -->
        <div v-if="reportContent" class="report-section">
          <div class="card-title inner-title">
            <AppIcon name="chart" /> <strong>AI 评估报告</strong>
            <button class="secondary-action small-action" @click="regenerateReport" :disabled="regenerating">
              {{ regenerating ? '生成中...' : '重新生成' }}
            </button>
          </div>
          <div class="report-body" v-html="renderMarkdown(reportContent)"></div>
        </div>
        <div v-else-if="run?.status === 'completed'" class="empty-inline" style="margin-top:16px">
          还没有 AI 评估报告。
          <button class="secondary-action small-action" @click="regenerateReport" :disabled="regenerating">
            {{ regenerating ? '生成中...' : '生成报告' }}
          </button>
        </div>
      </section>

      <section class="card section-pad">
        <div class="card-title"><strong>逐图预测</strong><span>{{ samples.total }} 张</span></div>
        <div v-if="samples.items.length === 0" class="empty-inline">当前没有逐图结果。</div>
        <div v-else class="eval-sample-grid">
          <div v-for="s in samples.items" :key="s.id" class="eval-sample-item">
            <img v-if="s.prediction_image_url || s.image_url" :src="s.prediction_image_url || s.image_url" loading="lazy" />
            <div class="eval-sample-name">{{ basename(s.image_path) }}</div>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import LogTerminal from '../components/LogTerminal.vue'
import { getEvaluationRun, listEvaluationSamples, getEvaluationLog, getEvaluationProgress } from '../api/projects.js'
import { getEvaluationReport, regenerateEvaluationReport } from '../api/reports.js'
import { basename, displayDatasetName, displayModelName, fmtMetric, statusText } from '../utils.js'

const route = useRoute()
const router = useRouter()
const run = ref(null)
const samples = ref({ items: [], total: 0, page: 1, page_size: 48 })
const reportContent = ref('')
const regenerating = ref(false)

const imageArtifacts = computed(() => {
  return (run.value?.artifacts || []).filter(a => /\.(png|jpg|jpeg|webp)$/i.test(a.name))
})
const fileArtifacts = computed(() => {
  return (run.value?.artifacts || []).filter(a => !/\.(png|jpg|jpeg|webp)$/i.test(a.name))
})
const loading = ref(true)
const error = ref('')
let pollTimer = null

onMounted(load)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function load() {
  loading.value = true
  error.value = ''
  try {
    run.value = await getEvaluationRun(route.params.id)
    // 如果正在运行，启动轮询
    if (run.value?.status === 'running' || run.value?.status === 'created') {
      startPolling()
    }
    // 如果已完成，直接加载样本
    if (run.value?.status === 'completed') {
      samples.value = await listEvaluationSamples(route.params.id)
      if (run.value?.report_content) reportContent.value = run.value.report_content
      else loadEvaluationReport()
    }
  } catch (err) {
    error.value = err?.message || '验证详情加载失败'
  } finally {
    loading.value = false
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    try {
      const p = await getEvaluationProgress(route.params.id)
      if (p.status === 'completed' || p.status === 'failed') {
        run.value.status = p.status
        run.value.precision = p.precision ?? run.value.precision
        run.value.recall = p.recall ?? run.value.recall
        run.value.map50 = p.map50 ?? run.value.map50
        run.value.map50_95 = p.map50_95 ?? run.value.map50_95
        clearInterval(pollTimer)
        pollTimer = null
        // 重新加载完整数据
        run.value = await getEvaluationRun(route.params.id)
        samples.value = await listEvaluationSamples(route.params.id)
      }
    } catch { /* ignore */ }
  }, 2000)
}

function fetchLogApi() {
  return getEvaluationLog(route.params.id)
}
function fetchProgressApi() {
  return getEvaluationProgress(route.params.id)
}

function onLogStatusChange(newStatus) {
  // 评估完成时自动加载报告
  if (newStatus === 'completed' || newStatus === 'failed') {
    run.value.status = newStatus
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    getEvaluationRun(route.params.id).then(d => { run.value = d; if (d?.report_content) reportContent.value = d.report_content }).catch(() => {})
    listEvaluationSamples(route.params.id).then(d => { samples.value = d }).catch(() => {})
    if (newStatus === 'completed') loadEvaluationReport()
  }
}

async function loadEvaluationReport() {
  try {
    const r = await getEvaluationReport(route.params.id)
    reportContent.value = r.content || ''
  } catch { /* 报告尚未生成 */ }
}

async function regenerateReport() {
  regenerating.value = true
  try {
    const r = await regenerateEvaluationReport(route.params.id)
    reportContent.value = r.content || ''
  } catch (e) {
    alert('报告生成失败: ' + (e?.message || '未知错误'))
  } finally {
    regenerating.value = false
  }
}

function askAgent(question) {
  router.push({ path: '/agent', query: { eval: route.params.id, q: question } })
}

function renderMarkdown(text) {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => `<pre><code class="${lang}">${code.trim()}</code></pre>`)
  html = html.replace(/^\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)+)/gm, (m, header, rows) => {
    const h = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('')
    const r = rows.trim().split('\n').map(row => {
      const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('')
      return `<tr>${cells}</tr>`
    }).join('')
    return `<table>${h}${r}</table>`
  })
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/(https?:\/\/\S+)/g, '<a href="$1" target="_blank">$1</a>')
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/gs, '<ul>$&</ul>')
  html = html.replace(/^---$/gm, '<hr>')
  html = html.replace(/\n{2,}/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  return '<div class="report-wrap">' + html + '</div>'
}

</script>
