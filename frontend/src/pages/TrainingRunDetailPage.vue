<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>训练详情</h1>
        <p>集中看参数、指标、图表产物、权重文件和 AI 训练报告。</p>
      </div>
      <div class="header-actions">
        <RouterLink class="secondary-action" :to="detail?.run?.project_id ? `/projects/${detail.run.project_id}` : '/projects'">
          返回项目
        </RouterLink>
      </div>
    </div>

    <div v-if="loading" class="loading">正在加载训练详情...</div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else-if="detail">
      <div class="metric-grid five compact-metric-grid">
        <div class="metric-card highlight">
          <span>状态</span>
          <strong>{{ statusText(detail.run.status) }}</strong>
          <template v-if="isRunning">
            <div class="progress-bar-wrap" style="width:100%;margin-top:6px">
              <div class="progress-bar" :style="{ width: (liveEpochs / Math.max(detail.run.epochs, 1) * 100) + '%' }"></div>
            </div>
            <small class="progress-text">{{ liveEpochs }}/{{ detail.run.epochs }} epochs</small>
          </template>
        </div>
        <div class="metric-card"><span>Precision</span><strong>{{ liveMetric('precision') }}</strong></div>
        <div class="metric-card"><span>Recall</span><strong>{{ liveMetric('recall') }}</strong></div>
        <div class="metric-card"><span>mAP50</span><strong>{{ liveMetric('map50') }}</strong></div>
        <div class="metric-card"><span>mAP50-95</span><strong>{{ liveMetric('map50_95') }}</strong></div>
      </div>

      <div class="project-summary-strip dense-strip four-cols">
        <div class="project-summary-card">
          <span>训练数据</span>
          <strong>{{ detail.dataset_version?.dataset_name }} / {{ detail.dataset_version?.version }}</strong>
          <small>{{ detail.dataset_version?.image_count || 0 }} 张图 / {{ detail.dataset_version?.class_count || 0 }} 类</small>
        </div>
        <div class="project-summary-card">
          <span>当前主权重</span>
          <strong>{{ bestWeightArtifact?.file_name || '未生成 best.pt' }}</strong>
          <small>{{ detail.model ? `最佳 Epoch ${detail.model.best_epoch ?? '-'}` : '还没有模型记录' }}</small>
        </div>
        <div class="project-summary-card">
          <span>图像产物</span>
          <strong>{{ imageArtifacts.length }} 项</strong>
          <small>{{ imageArtifacts.length ? '结果图、曲线图、混淆矩阵都在这里' : '还没有图表产物' }}</small>
        </div>
        <div class="project-summary-card">
          <span>文本产物</span>
          <strong>{{ fileArtifacts.length }} 项</strong>
          <small>{{ fileArtifacts.length ? 'metrics、日志、报告和配置都可直接打开' : '还没有文本产物' }}</small>
        </div>
      </div>

      <div class="detail-workbench">
        <section class="card section-pad compact-detail-section">
          <div class="detail-grid">
            <div class="info-item"><span>Run ID</span><strong>{{ detail.run.run_id }}</strong></div>
            <div class="info-item"><span>基础模型</span><strong>{{ cleanModel(detail.run.base_model) }}</strong></div>
            <div class="info-item"><span>数据批次</span><strong>{{ detail.dataset_version?.dataset_name }} / {{ detail.dataset_version?.version }}</strong></div>
            <div class="info-item"><span>训练轮数</span><strong>{{ detail.run.epochs }}</strong></div>
            <div class="info-item"><span>图像尺寸</span><strong>{{ detail.run.imgsz }}</strong></div>
            <div class="info-item"><span>Batch</span><strong>{{ detail.run.batch }}</strong></div>
            <div class="info-item"><span>优化器</span><strong>{{ detail.run.optimizer || 'auto' }}</strong></div>
            <div class="info-item"><span>学习率 lr0</span><strong>{{ detail.run.lr0 || '默认' }}</strong></div>
            <div class="info-item"><span>设备</span><strong>{{ detail.run.device || '自动' }}</strong></div>
            <div class="info-item"><span>最佳 Epoch</span><strong>{{ detail.model?.best_epoch ?? '-' }}</strong></div>
            <div class="info-item wide"><span>运行目录</span><strong>{{ detail.run.run_path || '-' }}</strong></div>
          </div>

          <div class="notes-inline" style="margin-bottom:12px">
            <span style="font-size:11px;color:var(--muted)">备注</span>
            <input
              class="inline-notes"
              :value="detail.run.notes || ''"
              placeholder="记录训练目的、参数调整、效果评价..."
              @blur="saveDetailNotes($event.target.value)"
              @keyup.enter="$event.target.blur()"
              style="font-size:12px;padding:6px 10px"
            />
          </div>

          <div class="card-title inner-title">
            <strong>每轮指标</strong>
            <span>{{ liveMetrics.length }} 轮</span>
          </div>
          <div class="table-card">
            <table>
              <thead>
                <tr>
                  <th>Epoch</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>mAP50</th>
                  <th>mAP50-95</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="metric in liveMetrics" :key="metric.epoch" :class="{ 'live-row': isRunning && metric.epoch === liveMetrics.length }">
                  <td>{{ metric.epoch }}</td>
                  <td>{{ fmtMetric(metric.precision) }}</td>
                  <td>{{ fmtMetric(metric.recall) }}</td>
                  <td>{{ fmtMetric(metric.map50) }}</td>
                  <td>{{ fmtMetric(metric.map50_95) }}</td>
                </tr>
                <tr v-if="!liveMetrics.length">
                  <td colspan="5">{{ isRunning ? '等待第一轮完成...' : '当前还没有逐轮指标。' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- 实时日志终端 -->
        <section class="card section-pad compact-detail-section">
          <div class="card-title inner-title">
            <strong>训练日志</strong>
            <span v-if="progress">{{ progress.epochs_completed }}/{{ progress.epochs_total }} epochs</span>
          </div>
          <LogTerminal
            :logApi="fetchLogApi"
            :progressApi="fetchProgressApi"
            :pollInterval="3000"
            :externalStatus="detail?.run?.status || ''"
            :sseUrl="(detail?.run?.status === 'running' || detail?.run?.status === 'created') ? `/api/training-runs/${detail.run.id}/log/stream` : ''"
            @status-change="onLogStatusChange"
          />
        </section>

        <section class="card section-pad compact-detail-section">
          <div class="card-title inner-title">
            <strong>训练图表</strong>
            <span>{{ imageArtifacts.length }} 张</span>
          </div>
          <div v-if="imageArtifacts.length" class="artifact-gallery">
            <div v-for="art in imageArtifacts" :key="art.name" class="chart-card" @click="openLightbox(art.url)">
              <div class="chart-img-wrap"><img :src="art.url" :alt="art.name" loading="lazy" /></div>
              <span class="chart-label">{{ chartLabel(art.file_name) }}</span>
            </div>
          </div>
          <div v-else class="empty-inline">训练完成后这里会展示 results.png、混淆矩阵、PR 曲线等。</div>

          <div class="card-title inner-title" style="margin-top:16px">
            <strong>权重文件</strong>
          </div>
          <div class="weight-downloads">
            <a v-if="bestWeightArtifact" class="weight-card highlight" :href="bestWeightArtifact.url" target="_blank">
              <AppIcon name="model" />
              <div><strong>best.pt</strong><span class="muted-text">最佳权重 — 建议部署使用</span></div>
            </a>
            <a v-if="lastWeightArtifact" class="weight-card" :href="lastWeightArtifact.url" target="_blank">
              <AppIcon name="model" />
              <div><strong>last.pt</strong><span class="muted-text">最后一轮权重 — 可继续训练</span></div>
            </a>
            <span v-if="!bestWeightArtifact && !lastWeightArtifact" class="empty-inline">训练完成后 YOLO 会自动生成 best.pt 和 last.pt。</span>
          </div>

          <div class="card-title inner-title" style="margin-top:12px">
            <strong>数据与日志文件</strong>
            <span>{{ dataFileArtifacts.length }} 个</span>
          </div>
          <div v-if="dataFileArtifacts.length" class="table-card">
            <table>
              <thead><tr><th>文件</th><th>路径</th><th></th></tr></thead>
              <tbody>
                <tr v-for="art in dataFileArtifacts" :key="art.name">
                  <td><strong>{{ art.file_name }}</strong></td>
                  <td class="mono muted-text">{{ art.name }}</td>
                  <td><a class="secondary-action small-action" :href="art.url" target="_blank">打开</a></td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty-inline">训练完成后会生成 results.csv、args.yaml、metrics.json 等文件。</div>

          <!-- Agent 快捷分析 -->
          <div class="agent-quick-section">
            <div class="card-title inner-title">
              <strong>AI 分析</strong>
              <span>让 Agent 帮你分析这次训练</span>
            </div>
            <div class="agent-quick-prompts">
              <button class="agent-prompt-btn" @click="askAgent('分析这次训练的结果，包括过拟合判断和改进建议')">
                <AppIcon name="chart" /> 分析训练结果
              </button>
              <button class="agent-prompt-btn" @click="askAgent('检查这次训练是否过拟合，precision 和 recall 的差距说明什么')">
                <AppIcon name="warning" /> 检查过拟合
              </button>
              <button class="agent-prompt-btn" @click="askAgent('基于当前训练结果，推荐下一步应该做什么')">
                <AppIcon name="activity" /> 推荐下一步
              </button>
              <button class="agent-prompt-btn" @click="askAgent('对比这次训练和之前的结果，分析趋势')">
                <AppIcon name="chart" /> 对比历史
              </button>
            </div>
          </div>

          <div v-if="detail.report_content" class="report-section">
            <div class="card-title inner-title"><AppIcon name="chart" /> <strong>AI 训练报告</strong></div>
            <div class="report-body" v-html="renderMarkdown(detail.report_content)"></div>
          </div>
        </section>
      </div>
    </template>

    <!-- 图片灯箱 -->
    <div v-if="lightboxSrc" class="lightbox-overlay" @click="closeLightbox">
      <button class="lightbox-close" @click="closeLightbox">✕</button>
      <img :src="lightboxSrc" class="lightbox-img" @click.stop />
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import LogTerminal from '../components/LogTerminal.vue'
import { getRunDetail, getProgress, getLog, updateRun } from '../api/training.js'
import { fmtMetric, statusText } from '../utils.js'

const route = useRoute()
const router = useRouter()
const detail = ref(null)
const loading = ref(true)
const error = ref('')
const progress = ref(null)
const lightboxSrc = ref('')
let pollTimer = null

function openLightbox(src) { lightboxSrc.value = src }
function closeLightbox() { lightboxSrc.value = '' }

const imageArtifacts = computed(() => {
  const items = detail.value?.artifacts || []
  return items.filter(item => /\.(png|jpg|jpeg|webp)$/i.test(item.file_name || item.name))
})

const fileArtifacts = computed(() => {
  const items = detail.value?.artifacts || []
  return items.filter(item => !/\.(png|jpg|jpeg|webp)$/i.test(item.file_name || item.name))
})

// 排除权重和报告，只留下数据文件
const dataFileArtifacts = computed(() => {
  const items = detail.value?.artifacts || []
  return items.filter(item => {
    const n = item.name || ''
    if (/\.(png|jpg|jpeg|webp)$/i.test(item.file_name || item.name)) return false
    if (/weights\/(best|last)\.pt$/i.test(n)) return false
    if (/ai_training_report/i.test(n)) return false
    return true
  })
})

const bestWeightArtifact = computed(() => (detail.value?.artifacts || []).find(item => /weights\/best\.pt$/i.test(item.name)) || null)
const lastWeightArtifact = computed(() => (detail.value?.artifacts || []).find(item => /weights\/last\.pt$/i.test(item.name)) || null)

// 实时数据：训练中用 progress 的 metrics，完成后用 detail 的
const isRunning = computed(() => detail.value?.run?.status === 'running' || detail.value?.run?.status === 'created')
const liveMetrics = computed(() => {
  const pm = progress.value?.metrics || []
  return pm.length > 0 ? pm : detail.value?.metrics || []
})
const liveEpochs = computed(() => progress.value?.epochs_completed ?? liveMetrics.value.length)

function liveMetric(key) {
  const all = liveMetrics.value
  if (!all.length) return fmtMetric(detail.value?.model?.[key])
  const last = all[all.length - 1]
  return fmtMetric(last?.[key])
}

function cleanModel(path) {
  if (!path) return '-'
  const n = String(path).replace(/\\/g, '/')
  const last = n.split('/').pop()
  return last.length > 4 ? last : n
}

function chartLabel(filename) {
  const map = {
    'results.png': '训练曲线',
    'confusion_matrix.png': '混淆矩阵',
    'PR_curve.png': 'P-R 曲线',
    'F1_curve.png': 'F1 曲线',
    'labels.jpg': '标签分布',
    'train_batch0.jpg': '训练批次',
    'val_batch0_pred.jpg': '验证预测',
  }
  return map[filename] || filename
}

onMounted(load)
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function load() {
  loading.value = true
  error.value = ''
  try {
    detail.value = await getRunDetail(route.params.id)
    if (detail.value?.run?.status === 'running' || detail.value?.run?.status === 'created') {
      startPolling()
    }
  } catch (err) {
    error.value = err?.message || '训练详情加载失败'
  } finally {
    loading.value = false
  }
}

function startPolling() {
  pollTimer = setInterval(pollProgress, 3000)
  pollProgress()
}

async function pollProgress() {
  try {
    const p = await getProgress(route.params.id)
    progress.value = p
    if (p.status === 'completed' || p.status === 'failed') {
      detail.value.run.status = p.status
      clearInterval(pollTimer)
      pollTimer = null
      detail.value = await getRunDetail(route.params.id)
    }
  } catch {}
}

// LogTerminal 用的 API 函数
function fetchLogApi() {
  return getLog(route.params.id)
}
function fetchProgressApi() {
  return getProgress(route.params.id)
}

async function saveDetailNotes(value) {
  const notes = (value || '').trim()
  if (notes === (detail.value?.run?.notes || '')) return
  try {
    await updateRun(route.params.id, { notes })
    detail.value.run.notes = notes
  } catch {}
}

function onLogStatusChange(newStatus) {
  if (newStatus === 'completed' || newStatus === 'failed') {
    detail.value.run.status = newStatus
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
    getRunDetail(route.params.id).then(d => { detail.value = d }).catch(() => {})
  }
}

function askAgent(question) {
  // 跳转到 Agent 页面，带上训练 run_id 和问题
  router.push({ path: '/agent', query: { run: route.params.id, q: question } })
}

function renderMarkdown(text) {
  if (!text) return ''
  let html = text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  // 代码块
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => `<pre><code class="${lang}">${code.trim()}</code></pre>`)
  // 表格
  html = html.replace(/^\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)+)/gm, (m, header, rows) => {
    const h = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('')
    const r = rows.trim().split('\n').map(row => {
      const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('')
      return `<tr>${cells}</tr>`
    }).join('')
    return `<table>${h}${r}</table>`
  })
  // 标题
  html = html.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  html = html.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^# (.+)$/gm, '<h2>$1</h2>')
  // 粗体/斜体
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  // 链接
  html = html.replace(/(https?:\/\/\S+)/g, '<a href="$1" target="_blank">$1</a>')
  // 列表
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/gs, '<ul>$&</ul>')
  // 分割线
  html = html.replace(/^---$/gm, '<hr>')
  // 段落
  html = html.replace(/\n{2,}/g, '</p><p>')
  html = html.replace(/\n/g, '<br>')
  return '<div class="report-wrap">' + html + '</div>'
}
</script>
