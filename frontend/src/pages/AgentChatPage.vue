<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>Agent 对话</h1>
        <p>
          <span v-if="activeProject" class="mode-badge mode-project">📌 {{ activeProject.name }}</span>
          <span v-else class="mode-badge mode-global">🌐 全局模式</span>
          分析训练、测试、模型和数据集，直接问问题，结果可以保存为计划。
        </p>
      </div>
      <div class="header-actions">
        <select v-model="selectedProjectId" @change="switchProject" class="project-select">
          <option :value="null">🌐 全局（所有项目）</option>
          <option v-for="p in projects" :key="p.id" :value="p.id">{{ p.name || `项目 ${p.id}` }}</option>
        </select>
        <button class="secondary-action" @click="createNewSession" :disabled="sending"><AppIcon name="add" /> 新建会话</button>
        <button class="primary-action" @click="sendQuickPrompt(primaryPrompt)" :disabled="sending || !primaryPrompt">
          <AppIcon name="agent" /> 分析最近结果
        </button>
      </div>
    </div>

    <div class="agent-layout">
      <aside class="agent-sidebar" :class="{ collapsed: sidebarCollapsed }">
        <div class="sidebar-head">
          <strong v-if="!sidebarCollapsed">会话列表</strong>
          <button class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'">
            {{ sidebarCollapsed ? '▶' : '◀' }}
          </button>
        </div>
        <div v-if="!sidebarCollapsed" class="sidebar-body">
          <!-- 项目上下文摘要 -->
          <div v-if="contextSummary" class="context-summary">
            <div class="context-title">
              {{ activeProject ? '📋 ' + activeProject.name : '🌐 全局状态' }}
            </div>
            <div v-if="contextSummary.datasets" class="context-row clickable" @click="composer = '分析当前数据集的质量和分布'; submitMessage()">
              <span>📦</span> <span>{{ contextSummary.datasets }} 个数据集</span>
            </div>
            <div v-if="contextSummary.trainings" class="context-row clickable" @click="composer = '分析最近一次训练'; submitMessage()">
              <span>🏋️</span> <span>{{ contextSummary.trainings }} 次训练</span>
            </div>
            <div v-if="contextSummary.evaluations" class="context-row clickable" @click="composer = '分析最近一次评估的结果'; submitMessage()">
              <span>📊</span> <span>{{ contextSummary.evaluations }} 次评估</span>
            </div>
            <div v-if="contextSummary.models" class="context-row clickable" @click="composer = '当前模型是否适合部署？'; submitMessage()">
              <span>🧠</span> <span>{{ contextSummary.models }} 个模型</span>
            </div>
            <div v-if="contextSummary.latestRun" class="context-latest">
              <small>最新训练: {{ contextSummary.latestRun }}</small>
            </div>
            <div v-if="contextSummary.bestMap" class="context-latest">
              <small>最佳 mAP50-95: {{ contextSummary.bestMap }}</small>
            </div>
            <div v-if="!contextSummary.datasets && !contextSummary.trainings" class="context-latest">
              <small class="muted-text">{{ activeProject ? '项目暂无数据，先导入数据集' : '暂无数据，先创建项目并导入数据集' }}</small>
            </div>
            <button v-if="!activeProject" class="secondary-action small-action" style="width:100%;margin-top:8px" @click="goToProjects">
              📁 管理项目
            </button>
          </div>

          <div v-if="sessionsLoading" class="session-list">
            <div class="skeleton skeleton-text" style="width:80%"></div>
            <div class="skeleton skeleton-text" style="width:65%"></div>
          </div>
          <div v-else class="session-list">
            <div
              v-for="session in sessions"
              :key="session.id"
              :class="['session-item-row', { active: session.id === currentSessionId }]"
              @click="selectSession(session)"
            >
              <div class="session-item-main">
                <template v-if="renamingSession?.id === session.id">
                  <input
                    v-model="renameTitle"
                    class="inline-rename-input"
                    @keyup.enter="confirmRename"
                    @keyup.escape="cancelRename"
                    @click.stop
                    @blur="confirmRename"
                    autofocus
                  />
                </template>
                <template v-else>
                  <span class="session-item-title">{{ session.title || `会话 ${session.id}` }}</span>
                  <small class="muted-text">{{ shortTime(session.created_at) }}</small>
                </template>
              </div>
              <div class="session-item-actions">
                <button class="session-action-btn" title="重命名" @click.stop="startRename(session)">✎</button>
                <button class="session-action-btn" title="删除" @click.stop="confirmDelete(session)">✕</button>
              </div>
            </div>
            <div v-if="!sessions.length" class="empty-inline">暂无会话</div>
          </div>

          <!-- ── 计划列表（与选中会话关联） ── -->
          <div v-if="allPlans.length" class="sidebar-plans">
            <div class="sidebar-plans-head">
              <span>📋 计划</span>
              <select v-model="planFilter" class="dtype-select-inline" style="width:auto;font-size:11px">
                <option value="active">活跃</option>
                <option value="archived">已归档</option>
                <option value="all">全部</option>
              </select>
            </div>
            <div class="sidebar-plans-list">
              <div v-if="!filteredPlans.length" class="empty-inline">暂无</div>
              <div
                v-for="plan in filteredPlans"
                :key="plan.id"
                :class="['sidebar-plan-item', { expanded: expandedPlanId === plan.id }]"
              >
                <div class="sidebar-plan-row" @click="togglePlanExpand(plan)">
                  <span v-if="!plan.is_read" class="plan-unread-dot" title="未读"></span>
                  <span class="sidebar-plan-title">{{ plan.title || '未命名' }}</span>
                  <span v-if="plan.training_run_id" class="plan-linked-model" :title="'关联训练 #' + plan.training_run_id">🔗</span>
                  <span :class="['chip', planStatusChip(plan.status)]" style="font-size:10px">{{ planStatusLabel(plan.status) }}</span>
                </div>
                <div v-if="expandedPlanId === plan.id" class="sidebar-plan-detail">
                  <div v-if="plan.training_run_id" class="plan-linked-info">
                    🔗 {{ getLinkedTrainingName(plan.training_run_id) }}
                  </div>
                  <div v-if="getPlanItems(plan).length">
                    <div v-for="(item, i) in getPlanItems(plan)" :key="i" class="plan-item-mini">
                      <span class="plan-mini-prio">{{ item.priority }}</span>
                      <span class="plan-mini-action">{{ item.action }}</span>
                    </div>
                  </div>
                  <div class="sidebar-plan-actions">
                    <button class="secondary-action small-action" @click.stop="applySavedPlan(plan)" :disabled="plan.status === 'executed'" style="font-size:11px">应用</button>
                    <button v-if="plan.status === 'archived'" class="secondary-action small-action" @click.stop="unarchivePlan(plan)" style="font-size:11px">恢复</button>
                    <button v-else-if="plan.status !== 'deleted'" class="secondary-action small-action" @click.stop="archivePlan(plan)" style="font-size:11px">归档</button>
                    <button class="secondary-action small-action" @click.stop="deletePlan(plan)" style="font-size:11px;color:var(--danger)">删除</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <section class="agent-main">
        <div v-if="messagesLoading" class="chat-empty">
          <p>正在加载对话...</p>
        </div>

        <div v-else-if="!normalizedMessages.length" class="chat-empty">
          <h3>直接开始提问</h3>
          <p>可以问训练掉点、数据质量、模型选择，或者让 Agent 直接给出下一轮计划。</p>
          <div class="quick-prompts">
            <button v-for="prompt in quickPrompts" :key="prompt" class="prompt-btn" @click="composer = prompt">{{ prompt }}</button>
          </div>
        </div>

        <div v-else ref="chatContainer" class="chat-messages">
          <template v-for="message in normalizedMessages" :key="message.key">
            <div v-if="message.role === 'tool'" class="tool-call-bubble">
              <span class="tool-icon">🔧</span>
              <span class="tool-text">{{ message.content }}</span>
            </div>
            <ChatBubble
              v-else
              :role="message.role"
              :content="message.content"
              :time="message.time"
              @save-plan="handleInlinePlanSave"
            />
          </template>
          <div v-if="sending" class="chat-typing">
            <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
          </div>
        </div>

        <div v-if="error && !sending" class="error-bar">{{ error }}</div>

        <div class="composer-area">
          <div class="composer-ref-row" v-if="composerRef">
            <span class="ref-chip">{{ composerRef.label }}</span>
            <button class="ref-chip-remove" @click="composerRef = null; composer.value = ''">✕</button>
          </div>
          <div class="composer-input-row">
            <button class="ref-picker-btn" @click.stop="showRefPicker = !showRefPicker" :disabled="sending" title="引用项目数据">+</button>
            <div class="composer-textarea-wrap">
              <textarea
                ref="composerEl"
                v-model="composer"
                :placeholder="composerRef ? '输入你想了解的问题...' : '输入问题，Enter 发送，Shift+Enter 换行'"
                @keydown="onComposerKey"
                @input="autoResize"
                rows="1"
              />
            </div>
            <button class="send-btn" @click="submitMessage" :disabled="sending || !composer.trim()" title="发送 (Enter)">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>
            </button>
          </div>
          <div class="composer-hint">
            <span class="muted-text">Enter 发送 · Shift+Enter 换行</span>
            <button v-if="error && !sending && lastSentText" class="secondary-action small-action" @click="retryLastMessage">重试</button>
          </div>
        </div>

        <!-- 数据选择面板 (弹出) -->
        <Teleport to="body">
          <div v-if="showRefPicker" class="ref-picker-overlay" @click.self="showRefPicker = false">
            <div class="ref-picker-panel">
              <div class="ref-picker-head">
                <strong>选择要分析的数据</strong>
                <span class="muted-text">Agent 将基于你选择的数据回答</span>
                <button class="ref-picker-close" @click="showRefPicker = false">✕</button>
              </div>
              <div class="ref-picker-body">
                <div v-if="!hasContextRefs" class="ref-picker-empty">
                  <p>暂无数据</p>
                  <small>{{ contextLoaded ? '当前项目没有数据集或训练记录' : '数据加载中...' }}</small>
                  <button class="secondary-action small-action" style="margin-top:8px" @click="reloadContext(); showRefPicker = true">🔄 重新加载</button>
                </div>
                <div v-for="group in refGroups" :key="group.key" class="ref-card-group">
                  <div class="ref-card-group-title">{{ group.icon }} {{ group.label }}</div>
                  <div v-if="!group.items.length" class="ref-card-empty">{{ group.emptyText }}</div>
                  <div class="ref-card-grid">
                    <button
                      v-for="item in group.items"
                      :key="group.key + '-' + item.id"
                      :class="['ref-card', { active: composerRef?.id === item.id && composerRef?.type === group.key }]"
                      @click="pickRef(group.key, item)"
                    >
                      <div class="ref-card-name">{{ item.run_id || item.dataset_name }}</div>
                      <div class="ref-card-meta">
                        <!-- 训练: 参数 + 数据集 + 验证指标 -->
                        <template v-if="group.key === 'training'">
                          <span :class="['dot', item.status === 'completed' ? 'ok' : 'warn']"></span>
                          {{ item.epochs }}轮·{{ item.imgsz }}px
                          <span v-if="item.map50_95" class="ref-card-metric">val mAP {{ item.map50_95 }}</span>
                        </template>
                        <!-- 评估: 数据集 + 指标 -->
                        <template v-else-if="group.key === 'evaluation'">
                          <span :class="['dot', item.status === 'completed' ? 'ok' : 'warn']"></span>
                          {{ item.eval_dataset?.name || '未知数据集' }}
                          <span v-if="item.map50_95" class="ref-card-metric">mAP {{ item.map50_95 }}</span>
                        </template>
                        <!-- 数据集 -->
                        <template v-else-if="group.key === 'dataset'">
                          <span v-if="item.dtype" :class="['ref-card-badge', 'dtype-' + item.dtype]">{{ item.dtype === 'train' ? '训练' : item.dtype === 'val' ? '验证' : item.dtype === 'test' ? '测试' : item.dtype }}</span>
                          {{ item.image_count }} 张 · {{ item.class_count }} 类
                        </template>
                        <!-- 模型: 精确率/召回率 + 部署状态 -->
                        <template v-else-if="group.key === 'model'">
                          <span v-if="item.precision">P {{ item.precision }}</span>
                          <span v-if="item.recall">· R {{ item.recall }}</span>
                          <span v-if="item.map50">· mAP50 {{ item.map50 }}</span>
                          <span v-if="item.best_epoch" class="ref-card-metric">best@{{ item.best_epoch }}</span>
                          <span v-if="item.is_production" class="ref-card-badge">生产</span>
                        </template>
                      </div>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Teleport>

        <div v-if="draftPlan" class="plan-inline card" style="margin:0 8px 8px">
          <div class="card-title" style="padding:8px 12px"><strong>建议计划</strong></div>
          <PlanCard :plan="draftPlan" @save="saveDraftPlan" @apply="applyDraftPlan" />
        </div>

      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '../components/AppIcon.vue'
import ChatBubble from '../components/ChatBubble.vue'
import PlanCard from '../components/PlanCard.vue'
import {
  applyPlan,
  createSession,
  deleteSession,
  getContext,
  getMessages,
  listPlans,
  listSessions,
  markPlanRead,
  renameSession,
  savePlan,
  sendMessageStream,
  updatePlanStatus,
} from '../api/agents.js'
import { listProjects } from '../api/projects.js'
import {
  readActiveProjectContext,
  setActiveProjectContext,
  clearActiveProjectContext,
  onActiveProjectContextChange,
} from '../state/projectContext.js'
import { shortTime } from '../utils.js'

const router = useRouter()
const sessionsLoading = ref(true)
const messagesLoading = ref(false)
const sending = ref(false)
const error = ref('')
const sessions = ref([])
const currentSessionId = ref(null)
const messages = ref([])
const context = ref({})
const plans = ref([])
const draftPlan = ref(null)
const expandedPlanId = ref(null)
const planFilter = ref('active')
const composer = ref('')
const lastSentText = ref('')
const chatContainer = ref(null)
const composerEl = ref(null)
const activeProject = ref(readActiveProjectContext())
const projects = ref([])
const selectedProjectId = ref(readActiveProjectContext()?.id || null)
const route = useRoute()
const renamingSession = ref(null)
const renameTitle = ref('')
const sidebarCollapsed = ref(false)
const showRefPicker = ref(false)
const composerRef = ref(null)
const contextLoaded = ref(false)
let unsubContext = null

const currentSession = computed(() => sessions.value.find(s => s.id === currentSessionId.value) || null)

const projectId = computed(() => selectedProjectId.value || null)

const normalizedMessages = computed(() =>
  messages.value.map((m, i) => ({
    key: m.id || `msg-${i}`,
    role: m.role === 'agent' ? 'assistant' : m.role === 'tool' ? 'tool' : m.role,
    content: m.content || '',
    time: m.created_at || '',
  }))
)

const quickPrompts = computed(() => {
  const prompts = []
  const ctx = context.value
  const lr = ctx.latest_run
  const le = ctx.latest_evaluation
  const lm = ctx.latest_model
  const versions = ctx.versions || []

  // 基于实际状态生成精准提问
  if (lr && le) {
    // 有训练也有评估 → 可以做过拟合判断
    const trainMap = lr.map50_95
    const evalMap = le.map50_95
    if (trainMap != null && evalMap != null && trainMap - evalMap > 0.03) {
      prompts.push(`训练 mAP ${trainMap?.toFixed(3)} vs 评估 ${evalMap?.toFixed(3)}，是否过拟合？`)
    }
    prompts.push(`对比训练 ${lr.run_id} 和评估 ${le.run_id} 的指标差异`)
  }
  if (lr) {
    prompts.push(`分析训练 ${lr.run_id} 的结果，给出改进建议`)
    if (lr.map50_95 != null && lr.map50_95 < 0.4) {
      prompts.push(`mAP ${lr.map50_95.toFixed(3)} 偏低，如何提升？`)
    }
  }
  if (versions.length) {
    const v = versions[0]
    if (v.audit && (v.audit.missing_labels || v.audit.invalid_bboxes)) {
      prompts.push('当前数据集有哪些标注质量问题？')
    } else {
      prompts.push('当前数据集质量和分布如何？')
    }
  }
  if (lm) {
    const prodLabel = lm.is_production ? '已标记生产' : '未部署'
    prompts.push(`best.pt 是否适合导出？(${prodLabel})`)
  }
  if (ctx.runs?.length >= 2) {
    prompts.push(`对比最近 ${Math.min(ctx.runs.length, 3)} 次训练的指标趋势`)
  }

  // 始终有"生成优化计划"
  const planPrompt = lr ? `为训练 ${lr.run_id} 生成一份优化计划` : '生成当前项目的优化计划'
  if (!prompts.some(p => p.includes('优化计划'))) prompts.push(planPrompt)

  // 补齐到 4 个
  if (prompts.length < 4) {
    const fallbacks = ['如何判断模型是否过拟合？', '训练参数怎么调？', '导入数据后该做什么？', '如何改善标注质量？']
    for (const f of fallbacks) {
      if (!prompts.includes(f) && prompts.length < 4) prompts.push(f)
    }
  }
  return prompts.slice(0, 4)
})

const primaryPrompt = computed(() => {
  if (context.value.latest_run) return `分析最近一次训练 ${context.value.latest_run.run_id}，给出下一轮建议`
  if (context.value.versions?.length) return '分析当前数据集，给出训练建议'
  return ''
})

const contextSummary = computed(() => {
  const ctx = context.value
  if (!ctx || !Object.keys(ctx).length) return null
  const versions = ctx.versions || []
  const runs = ctx.runs || []
  const evals = ctx.evaluations || []
  const models = ctx.models || []
  const latestRun = runs[0]
  let bestMap = null
  for (const m of models) {
    if (m.map50_95 != null && (bestMap == null || m.map50_95 > bestMap)) bestMap = m.map50_95
  }
  for (const r of runs) {
    if (r.map50_95 != null && (bestMap == null || r.map50_95 > bestMap)) bestMap = r.map50_95
  }
  return {
    datasets: versions.length,
    trainings: runs.length,
    evaluations: evals.length,
    models: models.length,
    latestRun: latestRun ? `${latestRun.run_id} (${latestRun.status})` : null,
    bestMap: bestMap != null ? bestMap.toFixed(3) : null,
  }
})

const contextRefs = computed(() => {
  const ctx = context.value
  return {
    trainings: (ctx.runs || []).slice(0, 6).map(r => ({
      id: r.id, run_id: r.run_id, status: r.status,
      epochs: r.epochs, imgsz: r.imgsz,
      train_dataset: r.train_dataset, val_dataset: r.val_dataset,
      map50_95: r.map50_95 != null ? r.map50_95.toFixed(3) : null,
    })),
    evaluations: (ctx.evaluations || []).slice(0, 6).map(e => ({
      id: e.id, run_id: e.run_id, status: e.status,
      eval_dataset: e.eval_dataset,
      map50_95: e.map50_95 != null ? e.map50_95.toFixed(3) : null,
      precision: e.precision != null ? Number(e.precision).toFixed(3) : null,
      recall: e.recall != null ? Number(e.recall).toFixed(3) : null,
    })),
    datasets: (ctx.versions || []).slice(0, 6).map(v => ({
      id: v.id, dataset_name: v.dataset_name, version: v.version, dtype: v.dtype, image_count: v.image_count, class_count: v.class_count,
    })),
    models: (ctx.models || []).slice(0, 6).map(m => ({
      id: m.id, run_id: m.run_id, map50_95: m.map50_95 != null ? m.map50_95.toFixed(3) : null,
      precision: m.precision != null ? Number(m.precision).toFixed(3) : null,
      recall: m.recall != null ? Number(m.recall).toFixed(3) : null,
      map50: m.map50 != null ? Number(m.map50).toFixed(3) : null,
      best_epoch: m.best_epoch, is_production: m.is_production,
    })),
  }
})

const hasContextRefs = computed(() => {
  const r = contextRefs.value
  return r.trainings.length + r.evaluations.length + r.datasets.length + r.models.length > 0
})

const refGroups = computed(() => [
  { key: 'training', icon: '🏋️', label: '训练', emptyText: '暂无训练记录',
    items: contextRefs.value.trainings },
  { key: 'evaluation', icon: '📊', label: '评估', emptyText: '暂无评估记录',
    items: contextRefs.value.evaluations },
  { key: 'dataset', icon: '📦', label: '数据集', emptyText: '暂无数据集',
    items: contextRefs.value.datasets },
  { key: 'model', icon: '🧠', label: '模型', emptyText: '暂无模型',
    items: contextRefs.value.models },
])

function pickRef(type, item) {
  const labels = { training: '训练', evaluation: '评估', dataset: '数据集', model: '模型' }
  const icons = { training: '🏋️', evaluation: '📊', dataset: '📦', model: '🧠' }
  const name = item.run_id || (item.dataset_name + '/' + item.version)
  composerRef.value = {
    id: item.id,
    type,
    label: `${icons[type]} ${labels[type]}: ${name}`,
    contextHint: `[引用: ${labels[type]} ${name}]`,
  }
  // 智能默认提问
  if (!composer.value.trim()) {
    if (type === 'training') {
      composer.value = `分析训练 ${name} 的收敛情况、过拟合风险和下一轮建议`
    } else if (type === 'evaluation') {
      const evalDsName = item.eval_dataset?.name || ''
      composer.value = `分析评估 ${name}（在${evalDsName}上），对比训练指标判断泛化`
    } else if (type === 'dataset') {
      composer.value = `分析数据集 ${name} 的质量、分布和标注情况`
    } else {
      composer.value = `分析模型 ${name} 的精度、召回率和部署建议`
    }
  }
}

const allPlans = computed(() => plans.value)
const filteredPlans = computed(() => {
  if (planFilter.value === 'all') return plans.value
  if (planFilter.value === 'archived') return plans.value.filter(p => p.status === 'archived')
  return plans.value.filter(p => p.status !== 'archived')
})

function planStatusLabel(status) {
  return { draft: '草稿', executed: '已应用', archived: '已归档', deleted: '已删除' }[status] || status || '-'
}
function planStatusChip(status) {
  return { draft: '', executed: 'success', archived: 'warning', deleted: 'danger' }[status] || ''
}
function planTypeLabel(type) {
  return { training: '训练', annotation: '标注', data: '数据', param: '参数', general: '通用' }[type] || type || '计划'
}

onMounted(async () => {
  // 监听项目上下文变化（从其他页面切换项目时同步）
  unsubContext = onActiveProjectContextChange((proj) => {
    activeProject.value = proj
    selectedProjectId.value = proj?.id || null
  })

  try {
    // 加载项目列表
    try {
      projects.value = (await listProjects()) || []
    } catch { /* ignore */ }

    await refreshAll()

    const autoQuestion = route.query.q
    const autoRun = route.query.run
    const autoEval = route.query.eval
    if (autoQuestion) {
      await createNewSession()
      let contextHint = ''
      if (autoRun) contextHint = `[训练任务 ${autoRun}] `
      else if (autoEval) contextHint = `[评估任务 ${autoEval}] `
      composer.value = contextHint + autoQuestion
      nextTick(() => submitMessage())
    }
  } catch (err) {
    error.value = err?.message || '加载失败'
  } finally {
    sessionsLoading.value = false
  }
})

function onClickOutside(e) {
  if (showRefPicker.value &&
      !e.target.closest('.ref-picker-btn') &&
      !e.target.closest('.ref-picker-panel') &&
      !e.target.closest('.ref-picker-overlay')) {
    showRefPicker.value = false
  }
}

onMounted(() => { document.addEventListener('click', onClickOutside) })
onUnmounted(() => {
  document.removeEventListener('click', onClickOutside)
  if (unsubContext) unsubContext()
  if (currentAbort) currentAbort()
})

async function refreshAll() {
  const pid = projectId.value
  try {
    const [allSessions, ctx, allPlans] = await Promise.all([
      listSessions(pid),
      getContext(pid),
      listPlans(),
    ])
    sessions.value = allSessions || []
    context.value = ctx || {}
    contextLoaded.value = !!(ctx && Object.keys(ctx).length)
    plans.value = (allPlans || []).map(normalizePlanRecord)
  } catch (e) {
    console.error('refreshAll failed:', e)
    // 重试一次，不带 projectId
    try {
      const [allSessions, ctx] = await Promise.all([listSessions(null), getContext(null)])
      sessions.value = allSessions || []
      context.value = ctx || {}
      contextLoaded.value = !!(ctx && Object.keys(ctx).length)
    } catch {}
  }
  if (!currentSessionId.value && sessions.value[0]) {
    currentSessionId.value = sessions.value[0].id
    await loadMessages()
  }
}

async function switchProject() {
  const id = selectedProjectId.value
  if (id) {
    const proj = projects.value.find(p => p.id === id)
    if (proj) {
      activeProject.value = proj
      setActiveProjectContext(proj)
    }
  } else {
    activeProject.value = null
    clearActiveProjectContext()
  }
  currentSessionId.value = null
  messages.value = []
  draftPlan.value = null
  error.value = ''
  await refreshAll()
}

function goToProjects() {
  router.push('/projects')
}

async function loadMessages() {
  if (!currentSessionId.value) return
  messagesLoading.value = true
  try {
    messages.value = await getMessages(currentSessionId.value) || []
    await reloadContext()
    nextTick(scrollChatToBottom)
  } catch (err) {
    error.value = err?.message || '加载消息失败'
  } finally {
    messagesLoading.value = false
  }
}

async function reloadContext() {
  try {
    const ctx = await getContext(projectId.value) || {}
    context.value = ctx
    contextLoaded.value = !!(ctx && Object.keys(ctx).length)
  } catch { /* ignore */ }
}

async function selectSession(session) {
  currentSessionId.value = session.id
  draftPlan.value = null
  error.value = ''
  await loadMessages()
}

async function createNewSession() {
  try {
    const now = new Date().toISOString().slice(0, 16).replace('T', ' ')
    const session = await createSession(`新会话 ${now}`, projectId.value)
    sessions.value.unshift(session)
    currentSessionId.value = session.id
    messages.value = []
    draftPlan.value = null
    error.value = ''
  } catch (err) {
    error.value = err?.message || '创建会话失败'
  }
}

async function confirmDelete(session) {
  if (!confirm(`确认删除会话"${session.title || `会话 ${session.id}`}"？此操作不可撤销。`)) return
  try {
    await deleteSession(session.id)
    sessions.value = sessions.value.filter(s => s.id !== session.id)
    if (currentSessionId.value === session.id) {
      currentSessionId.value = sessions.value[0]?.id || null
      messages.value = []
      draftPlan.value = null
      if (currentSessionId.value) await loadMessages()
    }
  } catch (err) {
    error.value = err?.message || '删除会话失败'
  }
}

function startRename(session) {
  renamingSession.value = session
  renameTitle.value = session.title || ''
}

async function confirmRename() {
  const title = renameTitle.value.trim()
  if (!title || !renamingSession.value) return
  try {
    const updated = await renameSession(renamingSession.value.id, title)
    const idx = sessions.value.findIndex(s => s.id === renamingSession.value.id)
    if (idx !== -1) sessions.value[idx] = { ...sessions.value[idx], ...updated }
    renamingSession.value = null
  } catch (err) {
    error.value = err?.message || '重命名失败'
  }
}

function cancelRename() {
  renamingSession.value = null
  renameTitle.value = ''
}

let currentAbort = null

async function submitMessage() {
  let text = composer.value.trim()
  if (!text) return
  // 如果没有会话，自动创建
  if (!currentSessionId.value) {
    await createNewSession()
  }
  // 如果有引用，添加到消息前面
  if (composerRef.value) {
    text = `${composerRef.value.contextHint} ${text}`
  }
  lastSentText.value = text
  composer.value = ''
  composerRef.value = null
  sending.value = true
  error.value = ''

  if (composerEl.value) {
    composerEl.value.style.height = 'auto'
  }

  messages.value.push({ id: `temp-${Date.now()}`, role: 'user', content: text, created_at: new Date().toISOString() })
  nextTick(scrollChatToBottom)

  // 添加一个空的 agent 消息，用于流式填充
  const streamMsgId = `stream-${Date.now()}`
  messages.value.push({ id: streamMsgId, role: 'assistant', content: '', created_at: new Date().toISOString() })
  nextTick(scrollChatToBottom)

  try {
    const { stream } = sendMessageStream(currentSessionId.value, text, projectId.value)
    currentAbort = null

    for await (const event of stream) {
      if (event.tool_call) {
        // 显示工具调用
        const tc = event.tool_call
        messages.value.push({
          id: `tool-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,
          role: 'tool',
          content: `🔧 ${tc.tool}(${JSON.stringify(tc.args)})`,
          created_at: new Date().toISOString(),
          tool_detail: tc,
        })
        nextTick(scrollChatToBottom)
      }
      if (event.chunk) {
        const msg = messages.value.find(m => m.id === streamMsgId)
        if (msg) {
          msg.content += event.chunk
          nextTick(scrollChatToBottom)
        }
      }
      if (event.plan) {
        draftPlan.value = normalizeDraftPlan(event.plan)
      }
      if (event.title) {
        const sess = sessions.value.find(s => s.id === currentSessionId.value)
        if (sess) sess.title = event.title
        if (currentSession.value) currentSession.value.title = event.title
      }
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      // 用户取消了
    } else {
      error.value = err?.message || '发送失败'
      // 移除空的流消息
      messages.value = messages.value.filter(m => m.id !== streamMsgId)
    }
  } finally {
    sending.value = false
    await reloadContext()
    await reloadPlans()
  }
}

async function reloadPlans() {
  try {
    const rows = await listPlans()
    plans.value = (rows || []).map(normalizePlanRecord)
  } catch { /* ignore */ }
}

function retryLastMessage() {
  if (lastSentText.value) {
    composer.value = lastSentText.value
    submitMessage()
  }
}

function sendQuickPrompt(prompt) {
  if (!prompt) return
  composer.value = prompt
  submitMessage()
}

async function handleInlinePlanSave(plan) { await persistPlan(plan, false) }
async function saveDraftPlan(plan = draftPlan.value) { await persistPlan(plan, false) }
async function applyDraftPlan(plan = draftPlan.value) { await persistPlan(plan, true) }

async function persistPlan(plan, applyAfterSave) {
  if (!plan) return
  error.value = ''
  try {
    // 自动检测关联的训练: composerRef > 上下文latest_run > 标题中匹配
    let linkedTrainingId = composerRef.value?.type === 'training' ? composerRef.value.id : null
    if (!linkedTrainingId) {
      const lr = context.value.latest_run
      if (lr) {
        // 检查 plan 标题或用户最后发送的消息中是否提到了该训练
        const title = (plan.title || '')
        const lastMsg = lastSentText.value || ''
        if (title.includes(lr.run_id) || lastMsg.includes(lr.run_id)) {
          linkedTrainingId = lr.id
        }
      }
      // 兜底: 如果 plan 是关于最近训练的，直接关联
      if (!linkedTrainingId && lr && (plan.plan_type === 'optimization' || plan.plan_type === 'training')) {
        linkedTrainingId = lr.id
      }
    }

    const saved = await savePlan({
      session_id: currentSessionId.value,
      project_id: projectId.value,
      plan_type: plan.plan_type || 'general',
      title: plan.title || '未命名计划',
      content: plan,
      training_run_id: linkedTrainingId,
      dataset_version_id: composerRef.value?.type === 'dataset' ? composerRef.value.id : null,
    })
    if (applyAfterSave) {
      await applyPlan(saved.id)
      const items = Array.isArray(plan.items) ? plan.items : []
      const tParams = {}
      for (const item of items) {
        const k = String(item.param || '').toLowerCase()
        if (k === 'epochs') tParams.epochs = item.value
        else if (k === 'imgsz' || k === 'img_size') tParams.imgsz = item.value
        else if (k === 'batch') tParams.batch = item.value
        else if (k === 'base_model') tParams.base_model = item.value
        else if (k === 'device') tParams.device = item.value
      }
      if (Object.keys(tParams).length > 0) {
        const pid = projectId.value
        const q = new URLSearchParams()
        for (const [k, v] of Object.entries(tParams)) q.set(k, String(v))
        q.set('tab', 'training')
        window.location.href = pid ? `/projects/${pid}?${q.toString()}` : `/projects?${q.toString()}`
        return
      }
    }
    draftPlan.value = null
    await reloadPlans()
  } catch (err) {
    error.value = err?.message || '计划保存失败'
  }
}

async function applySavedPlan(plan) {
  try {
    const result = await applyPlan(plan.id)
    const items = Array.isArray(result?.params?.items) ? result.params.items : []
    const tParams = {}
    for (const item of items) {
      const k = String(item.param || '').toLowerCase()
      if (k === 'epochs') tParams.epochs = item.value
      else if (k === 'imgsz') tParams.imgsz = item.value
      else if (k === 'batch') tParams.batch = item.value
    }
    if (Object.keys(tParams).length > 0) {
      const pid = projectId.value
      const q = new URLSearchParams()
      for (const [k, v] of Object.entries(tParams)) q.set(k, String(v))
      q.set('tab', 'training')
      window.location.href = pid ? `/projects/${pid}?${q.toString()}` : `/projects?${q.toString()}`
      return
    }
    await reloadPlans()
  } catch (err) {
    error.value = err?.message || '计划应用失败'
  }
}

async function archivePlan(plan) {
  try {
    await updatePlanStatus(plan.id, 'archived')
    await reloadPlans()
  } catch (err) {
    error.value = err?.message || '归档失败'
  }
}

async function unarchivePlan(plan) {
  try {
    await updatePlanStatus(plan.id, 'draft')
    await reloadPlans()
  } catch (err) {
    error.value = err?.message || '恢复失败'
  }
}

async function deletePlan(plan) {
  if (!confirm(`删除计划"${plan.title || '未命名'}"？`)) return
  try {
    await updatePlanStatus(plan.id, 'deleted')
    await reloadPlans()
  } catch (err) {
    error.value = err?.message || '删除失败'
  }
}

function togglePlanExpand(plan) {
  if (expandedPlanId.value === plan.id) {
    expandedPlanId.value = null
  } else {
    expandedPlanId.value = plan.id
    if (!plan.is_read) {
      plan.is_read = 1
      markPlanRead(plan.id).catch(() => {})
    }
  }
}

function getPlanItems(plan) {
  if (!plan) return []
  let content = plan.content
  if (typeof content === 'string') {
    try { content = JSON.parse(content) } catch { return [] }
  }
  return content?.items || []
}

function getLinkedTrainingName(trainingRunId) {
  const runs = context.value.runs || []
  const run = runs.find(r => r.id === trainingRunId)
  if (run) return `训练: ${run.run_id}`
  const models = context.value.models || []
  const model = models.find(m => m.id === trainingRunId)
  if (model) return `模型: ${model.run_id}`
  return `关联 #${trainingRunId}`
}

function normalizePlanRecord(plan) {
  let content = plan?.content
  if (typeof content === 'string') {
    try { content = JSON.parse(content) } catch { content = { raw: content } }
  }
  return { ...plan, content }
}

function normalizeDraftPlan(plan) {
  return {
    plan_type: plan.plan_type || 'general',
    title: plan.title || '未命名计划',
    items: Array.isArray(plan.items) ? plan.items : [],
    reason: plan.reason || '',
  }
}

function scrollChatToBottom() {
  if (!chatContainer.value) return
  chatContainer.value.scrollTop = chatContainer.value.scrollHeight
}

function onComposerKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submitMessage()
  }
}

function autoResize() {
  const el = composerEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 160) + 'px'
}
</script>
