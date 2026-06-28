<template>
  <section class="page compact-page">
    <div class="page-header">
      <div>
        <h1>{{ project?.name || '项目工作台' }}</h1>
        <p>{{ project?.description || '围绕项目统一管理训练、验证、模型和 Agent 分析。' }}</p>
      </div>
      <div class="header-actions">
        <RouterLink class="secondary-action" to="/projects">返回项目</RouterLink>
        <RouterLink class="primary-action" to="/datasets">管理数据集</RouterLink>
      </div>
    </div>

    <div v-if="loading" class="loading">正在加载项目...</div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-else-if="project">
      <div class="metric-grid four compact-metric-grid">
        <div class="metric-card"><span>训练记录</span><strong>{{ project.counts.training_count }}</strong></div>
        <div class="metric-card"><span>验证记录</span><strong>{{ project.counts.evaluation_count }}</strong></div>
        <div class="metric-card"><span>模型记录</span><strong>{{ project.counts.model_count }}</strong></div>
        <div class="metric-card"><span>最佳 mAP50</span><strong>{{ fmtMetric(project.counts.best_map50) }}</strong></div>
      </div>

      <div class="project-summary-strip dense-strip">
        <div class="project-summary-card">
          <span>最近训练</span>
          <strong>{{ latestTrainingRun ? displayTrainingName(latestTrainingRun) : '-' }}</strong>
          <small>{{ latestTrainingRun ? `${statusText(latestTrainingRun.status)} / ${latestTrainingRun.epochs} epochs` : '还没有训练记录' }}</small>
        </div>
        <div class="project-summary-card">
          <span>最近验证</span>
          <strong>{{ latestEvaluationRun?.run_id || '-' }}</strong>
          <small>{{ latestEvaluationRun ? `mAP50-95 ${fmtMetric(latestEvaluationRun.map50_95)}` : '还没有验证记录' }}</small>
        </div>
        <div class="project-summary-card">
          <span>当前主模型</span>
          <strong>{{ featuredModel ? displayModelName(featuredModel) : '-' }}</strong>
          <small>{{ featuredModel ? modelState(featuredModel) : '还没有模型' }}</small>
        </div>
      </div>

      <div class="project-tabs compact-tabs">
        <button v-for="tab in tabs" :key="tab.key" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
          {{ tab.label }}
        </button>
      </div>

      <section v-if="activeTab === 'training'" class="card">
        <div class="card-title">
          <strong>训练</strong>
          <span>训练记录、训练图表和 best.pt 都归属于项目。</span>
        </div>
        <div class="compact-stats project-substats">
          <div><span>最近训练</span><strong>{{ latestTrainingRun ? displayTrainingName(latestTrainingRun) : '-' }}</strong></div>
          <div><span>运行中</span><strong>{{ project.training_runs.filter(item => item.status === 'running').length }}</strong></div>
          <div><span>已完成</span><strong>{{ project.training_runs.filter(item => item.status === 'completed').length }}</strong></div>
          <div><span>失败</span><strong>{{ project.training_runs.filter(item => item.status === 'failed').length }}</strong></div>
        </div>
        <div class="two-col dense-two-col">
          <div class="section-pad compact-form-panel">
            <label class="form-field">
              <span>训练数据</span>
              <select v-model.number="trainForm.dataset_version_id">
                <option :value="0" disabled>选择训练数据</option>
                <option v-for="v in labeledVersions" :key="v.id" :value="v.id">
                  {{ v.dataset_name }} / {{ v.version }} ({{ dtypeLabel(v) }} · {{ v.image_count }}张 · {{ v.label_file_count }}标注)
                </option>
              </select>
            </label>
            <label class="form-field">
              <span>基础模型</span>
              <select v-model="trainForm.base_model">
                <optgroup label="预训练模型">
                  <option value="yolo11n.pt">YOLO11n (nano, 最快)</option>
                  <option value="yolo11s.pt">YOLO11s (small)</option>
                  <option value="yolo11m.pt">YOLO11m (medium)</option>
                  <option value="yolo11l.pt">YOLO11l (large)</option>
                  <option value="yolo11x.pt">YOLO11x (xlarge, 最准)</option>
                  <option value="yolov8n.pt">YOLOv8n (nano)</option>
                  <option value="yolov8s.pt">YOLOv8s (small)</option>
                  <option value="yolov8m.pt">YOLOv8m (medium)</option>
                  <option value="yolov8l.pt">YOLOv8l (large)</option>
                  <option value="yolov8x.pt">YOLOv8x (xlarge)</option>
                </optgroup>
                <optgroup label="队列续训">
                  <option :value="LATEST_PROJECT_MODEL_SENTINEL">{{ latestProjectModelOptionText }}</option>
                </optgroup>
                <optgroup v-if="queueTrainingRunOptions.length" label="指定训练任务产物（T8/T9 可绑定 T7）">
                  <option
                    v-for="run in queueTrainingRunOptions"
                    :key="run.id"
                    :value="`${TRAINING_RUN_MODEL_PREFIX}${run.id}`"
                  >
                    使用 {{ displayTrainingName(run) }} 的产出模型（{{ statusText(run.status) }}）
                  </option>
                </optgroup>
                <optgroup v-if="project.models.length" label="已有产出模型（可指定 T7/T8 的 best.pt 继续训练）">
                  <option v-for="m in project.models" :key="m.id" :value="m.best_pt_path">
                    {{ displayModelName(m) }} / 来源训练 {{ m.source_training_display_name || m.run_id }} (mAP50: {{ fmtMetric(m.map50) }})
                  </option>
                </optgroup>
              </select>
              <small v-if="trainForm.base_model === LATEST_PROJECT_MODEL_SENTINEL" class="helper-text">
                启动时会解析为本项目最新完成模型；当前参考：{{ latestProjectModelHint }}
              </small>
              <small v-else-if="selectedBaseModelHint" class="helper-text">{{ selectedBaseModelHint }}</small>
            </label>
            <label class="form-field"><span>epochs</span><input v-model.number="trainForm.epochs" type="number" min="1" /></label>
            <div class="form-row">
              <label class="form-field form-field-flex"><span>优化器</span>
                <select v-model="trainForm.optimizer" style="width:100%">
                  <option value="auto">auto</option>
                  <option value="SGD">SGD</option>
                  <option value="Adam">Adam</option>
                  <option value="AdamW">AdamW</option>
                </select>
              </label>
              <label class="form-field form-field-flex"><span>lr0</span><input v-model="trainForm.lr0" placeholder="0.01" style="width:100%" /></label>
            </div>
            <div class="form-row">
              <label class="form-field form-field-flex"><span>尺寸</span><input v-model.number="trainForm.imgsz" type="number" min="64" style="width:100%" /></label>
              <label class="form-field form-field-flex"><span>Batch</span><input v-model.number="trainForm.batch" type="number" min="1" style="width:100%" /></label>
            </div>
            <label class="form-field"><span>训练设备</span>
              <select v-model="trainForm.device">
                <option value="">自动选择</option>
                <option v-for="g in gpuList" :key="g.device" :value="g.device">{{ g.label }}</option>
                <option value="cpu">CPU</option>
              </select>
            </label>
            <button class="primary-action" @click="startTraining">启动训练</button>
            <p v-if="actionError" class="error">{{ actionError }}</p>
            <p v-if="actionMsg" class="action-msg">{{ actionMsg }}</p>
            <p class="helper-text">选择一个有标注的数据集作为训练数据，系统会记住上次选择。</p>
          </div>

          <div class="table-card section-pad">
            <table class="training-table training-table--compact">
              <thead>
                <tr>
                  <th>任务名称</th>
                  <th>数据集</th>
                  <th>架构</th>
                  <th>状态</th>
                  <th>进度</th>
                  <th>mAP50</th>
                  <th>备注</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="run in project.training_runs" :key="run.id">
                  <td>
                    <RouterLink class="task-name-link" :to="`/training/${run.id}`">{{ displayTrainingName(run) }}</RouterLink>
                    <div v-if="run.output_model_display_name || run.output_model_name" class="table-cell-sub">产出模型：{{ run.output_model_display_name || run.output_model_name }}</div>
                    <div v-else-if="run.status === 'completed'" class="table-cell-sub">未找到注册模型</div>
                  </td>
                  <td class="muted-text cell-clip">{{ run.dataset_display_name || run.dataset_name }}</td>
                  <td><span class="model-arch-tag model-arch-tag--sm">{{ archLabel(run.base_model) }}</span></td>
                  <td>
                    <span :class="['chip', statusChipClass(run.status)]">{{ statusText(run.status) }}</span>
                  </td>
                  <td class="muted-text">{{ run.epochs }} epochs</td>
                  <td>
                    <span v-if="run.map50 != null" class="map-value">{{ fmtMetric(run.map50) }}</span>
                    <span v-else class="muted-text">-</span>
                  </td>
                  <td>
                    <input
                      class="inline-notes"
                      :value="run.model_notes || run.notes || ''"
                      placeholder="备注..."
                      @blur="saveModelNotes(run, $event.target.value)"
                      @keyup.enter="$event.target.blur()"
                    />
                  </td>
                  <td>
                    <div class="action-btn-group">
                      <RouterLink class="secondary-action small-action" :to="`/training/${run.id}`">详情</RouterLink>
                      <button class="secondary-action small-action danger-action" @click="deleteTrainingRun(run)">删除</button>
                    </div>
                  </td>
                </tr>
                <tr v-if="project.training_runs.length === 0">
                  <td colspan="8" class="empty-cell">当前还没有训练记录。</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'evaluation'" class="card">
        <div class="card-title">
          <strong>验证</strong>
          <span>优先使用独立 test 集，没有时再用 val 做链路验证。</span>
        </div>
        <div class="compact-stats project-substats">
          <div><span>最近验证</span><strong>{{ latestEvaluationRun?.run_id || '-' }}</strong></div>
          <div><span>已完成</span><strong>{{ project.evaluation_runs.filter(item => item.status === 'completed').length }}</strong></div>
          <div><span>失败</span><strong>{{ project.evaluation_runs.filter(item => item.status === 'failed').length }}</strong></div>
          <div><span>运行中</span><strong>{{ project.evaluation_runs.filter(item => item.status === 'running').length }}</strong></div>
        </div>
        <div class="two-col dense-two-col">
          <div class="section-pad compact-form-panel">
            <label class="form-field">
              <span>模型版本 (仅YOLO)</span>
              <select v-model.number="evalForm.model_version_id">
                <option :value="0" disabled>选择模型</option>
                <option v-for="model in project.models.filter(m => !m.model_format || m.model_format === 'YOLO')" :key="model.id" :value="model.id">
                  {{ displayModelName(model) }} (mAP50-95: {{ fmtMetric(model.map50_95) }})
                </option>
              </select>
            </label>
            <label class="form-field">
              <span>验证数据</span>
              <select v-model.number="evalForm.dataset_version_id">
                <option :value="0" disabled>选择验证数据</option>
                <option v-for="v in allVersionsForEval" :key="v.id" :value="v.id">
                  {{ v.dataset_name }} / {{ v.version }} ({{ dtypeLabel(v) }} · {{ v.image_count }}张{{ v.label_file_count ? ' · ' + v.label_file_count + '标注' : '' }})
                </option>
              </select>
            </label>
            <label class="form-field"><span>source split</span><input v-model="evalForm.source_split" /></label>
            <label class="form-field"><span>图像尺寸</span><input v-model.number="evalForm.imgsz" type="number" min="64" /></label>
            <label class="form-field"><span>Batch</span><input v-model.number="evalForm.batch" type="number" min="1" /></label>
            <label class="form-field"><span>设备</span><input v-model="evalForm.device" placeholder="留空自动选择" /></label>
            <button class="primary-action" @click="startEvaluation">启动验证</button>
            <p v-if="actionError" class="error">{{ actionError }}</p>
            <p v-if="actionMsg" class="action-msg">{{ actionMsg }}</p>
          </div>

          <div class="table-card section-pad">
            <table class="training-table training-table--compact">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>模型</th>
                  <th>状态</th>
                  <th>mAP50</th>
                  <th>mAP50-95</th>
                  <th>详情</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="run in project.evaluation_runs" :key="run.id">
                  <td>
                    <div class="table-cell-stack">
                      <span class="table-cell-main">{{ run.run_id }}</span>
                      <span class="table-cell-sub">{{ run.dataset_display_name || run.dataset_name || '未关联数据集' }}</span>
                    </div>
                  </td>
                  <td>
                    <div class="table-cell-stack">
                      <span class="table-cell-main">{{ run.model_display_name || run.display_model_name || run.model_name || run.model_run_id || '-' }}</span>
                      <span class="table-cell-sub">{{ run.source_split || 'test' }}</span>
                    </div>
                  </td>
                  <td>{{ statusText(run.status) }}</td>
                  <td>{{ fmtMetric(run.map50) }}</td>
                  <td>{{ fmtMetric(run.map50_95) }}</td>
                  <td><RouterLink class="secondary-action small-action" :to="`/evaluations/${run.id}`">详情</RouterLink></td>
                  <td><button class="secondary-action small-action danger-action" @click="deleteEvalRun(run)">删除</button></td>
                </tr>
                <tr v-if="project.evaluation_runs.length === 0">
                  <td colspan="7">当前还没有验证记录。</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section v-if="activeTab === 'models'" class="card">
        <div class="card-title">
          <strong>模型</strong>
          <span>重点管理 best.pt、来源训练和候选 / 生产状态。</span>
        </div>
        <div class="compact-stats project-substats">
          <div><span>生产模型</span><strong>{{ project.models.filter(item => item.is_production).length }}</strong></div>
          <div><span>归档模型</span><strong>{{ project.models.filter(item => !item.is_production).length }}</strong></div>
          <div><span>当前主模型</span><strong>{{ featuredModel ? displayModelName(featuredModel) : '-' }}</strong></div>
          <div><span>模型总数</span><strong>{{ project.models.length }}</strong></div>
        </div>
        <div class="table-card section-pad">
          <table class="training-table training-table--compact">
            <thead>
              <tr>
                <th>Run</th>
                <th>基础模型</th>
                <th>mAP50</th>
                <th>mAP50-95</th>
                <th>状态</th>
                <th>best.pt</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="model in project.models" :key="model.id">
                <td>
                  <div class="table-cell-stack">
                    <span class="table-cell-main">{{ displayModelName(model) }}</span>
                    <span class="table-cell-sub">{{ model.source_training_display_name || (model.is_production ? '生产模型' : '候选模型') }}</span>
                  </div>
                </td>
                <td>
                  <div class="table-cell-stack">
                    <span class="table-cell-main">{{ modelBaseLabel(model) }}</span>
                    <span v-if="model.model_format" class="table-cell-sub">{{ model.model_format.toUpperCase() }}</span>
                  </div>
                </td>
                <td>{{ fmtMetric(model.map50) }}</td>
                <td>{{ fmtMetric(model.map50_95) }}</td>
                <td>{{ modelState(model) }}</td>
                <td><a class="secondary-action small-action" :href="`/api/models/${model.id}/download/best`" target="_blank">下载</a></td>
                <td><button class="secondary-action small-action danger-action" @click="deleteModel(model)">删除</button></td>
              </tr>
              <tr v-if="project.models.length === 0">
                <td colspan="7">当前还没有模型记录。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="activeTab === 'agent'" class="card project-agent-panel">
        <div class="project-agent-hero">
          <div class="project-agent-hero-main">
            <span class="project-agent-eyebrow">项目 Agent</span>
            <h3>围绕训练、验证、模型与数据集，直接进入分析模式</h3>
            <p>
              把最近一次训练、最近一次验证和当前主模型串起来看，比单独读一条记录更快定位问题。
            </p>
          </div>
          <div class="project-agent-launch">
            <span class="project-agent-launch-label">当前推荐入口</span>
            <strong>{{ agentHeadline }}</strong>
            <button class="primary-action" @click="openAgentWorkspace">打开项目对话</button>
          </div>
        </div>

        <div class="project-agent-stats">
          <div class="project-agent-stat">
            <span>可读数据批次</span>
            <strong>{{ project.datasets.length }}</strong>
            <small>数据集与版本</small>
          </div>
          <div class="project-agent-stat">
            <span>可读训练记录</span>
            <strong>{{ project.training_runs.length }}</strong>
            <small>最近训练可直接分析</small>
          </div>
          <div class="project-agent-stat">
            <span>可读验证记录</span>
            <strong>{{ project.evaluation_runs.length }}</strong>
            <small>优先串联最近验证结果</small>
          </div>
          <div class="project-agent-stat">
            <span>可读模型记录</span>
            <strong>{{ project.models.length }}</strong>
            <small>包含生产与候选模型</small>
          </div>
        </div>

        <div class="project-agent-grid">
          <div class="project-agent-block">
            <div class="project-agent-block-head">
              <strong>最新信号</strong>
              <span>先看最值得分析的三条上下文</span>
            </div>
            <div class="project-agent-signal-list">
              <div class="project-agent-signal">
                <span class="project-agent-signal-label">最近训练</span>
                <strong>{{ latestTrainingRun ? displayTrainingName(latestTrainingRun) : '暂无训练记录' }}</strong>
                <small>{{ latestTrainingRun ? `${statusText(latestTrainingRun.status)} · ${latestTrainingRun.epochs} epochs` : '需要先发起训练' }}</small>
              </div>
              <div class="project-agent-signal">
                <span class="project-agent-signal-label">最近验证</span>
                <strong>{{ latestEvaluationRun?.run_id || '暂无验证记录' }}</strong>
                <small>{{ latestEvaluationRun ? `mAP50-95 ${fmtMetric(latestEvaluationRun.map50_95)}` : '需要先发起验证' }}</small>
              </div>
              <div class="project-agent-signal">
                <span class="project-agent-signal-label">当前主模型</span>
                <strong>{{ featuredModel ? displayModelName(featuredModel) : '暂无模型记录' }}</strong>
                <small>{{ featuredModel ? modelState(featuredModel) : '训练完成后会自动沉淀模型' }}</small>
              </div>
            </div>
          </div>

          <div class="project-agent-block">
            <div class="project-agent-block-head">
              <strong>推荐分析主题</strong>
              <span>直接带着问题进入对话</span>
            </div>
            <div class="project-agent-prompt-list">
              <button
                v-for="prompt in quickAgentPrompts"
                :key="prompt"
                class="project-agent-prompt"
                @click="openAgentPrompt(prompt)"
              >
                <strong>{{ prompt }}</strong>
                <span>进入 Agent 分析</span>
              </button>
            </div>
          </div>
        </div>

        <div class="project-agent-footer">
          <RouterLink v-if="latestTrainingRun" class="secondary-action" :to="`/training/${latestTrainingRun.id}`">查看最近训练</RouterLink>
          <RouterLink v-if="latestEvaluationRun" class="secondary-action" :to="`/evaluations/${latestEvaluationRun.id}`">查看最近验证</RouterLink>
          <RouterLink v-if="featuredModel" class="secondary-action" to="/registry">查看模型仓库</RouterLink>
        </div>
      </section>
    </template>
  </section>
</template>

<script setup>
import { computed, onActivated, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listVersions } from '../api/datasets.js'
import { createProjectEvaluationRun, createProjectTrainingRun, getProject } from '../api/projects.js'
import { deleteRun, updateRun } from '../api/training.js'
import { updateModel } from '../api/models.js'
import { getRuntime } from '../api/system.js'
import { deleteModel as deleteModelApi } from '../api/models.js'
import { setActiveProjectContext } from '../state/projectContext.js'
import { displayModelName, displayTrainingName, fmtMetric, formatError, shortTime, statusText } from '../utils.js'
import { del } from '../api/client.js'

const route = useRoute()
const router = useRouter()
const project = ref(null)
const versions = ref([])
const gpuList = ref([])
const loading = ref(true)
const error = ref('')
const actionMsg = ref('')
const actionError = ref('')
const activeTab = ref(route.query.tab || 'training')

const tabs = [
  { key: 'training', label: '训练' },
  { key: 'evaluation', label: '验证' },
  { key: 'models', label: '模型' },
  { key: 'agent', label: 'Agent' },
]

const LATEST_PROJECT_MODEL_SENTINEL = '__latest_project_model__'
const TRAINING_RUN_MODEL_PREFIX = '__training_run_model__:'

const trainForm = reactive({
  dataset_version_id: 0,
  base_model: 'yolo11n.pt',
  epochs: 50,
  imgsz: 640,
  batch: 8,
  device: '',
  run_name: '',
  optimizer: 'auto',
  lr0: '',
})

const evalForm = reactive({
  model_version_id: 0,
  dataset_version_id: 0,
  binding_id: 0,
  source_split: 'test',
  imgsz: 640,
  batch: 8,
  device: '',
})

const latestTrainingRun = computed(() => project.value?.training_runs?.[0] || null)
const latestEvaluationRun = computed(() => project.value?.evaluation_runs?.[0] || null)
const latestCompletedProjectModel = computed(() => {
  const rows = project.value?.models || []
  return rows.find(item => {
    const format = String(item.model_format || 'YOLO').toUpperCase()
    return (!format || format === 'YOLO') &&
      (item.best_pt_path || item.last_pt_path) &&
      (!item.training_status || item.training_status === 'completed')
  }) || null
})
const latestProjectModelOptionText = computed(() => {
  const model = latestCompletedProjectModel.value
  if (!model) return '使用本项目最新完成模型（启动时解析，当前暂无已完成模型）'
  return `使用最新完成模型：${displayModelName(model)} / ${model.source_training_display_name || model.run_id || '未关联训练'}`
})
const latestProjectModelHint = computed(() => {
  const model = latestCompletedProjectModel.value
  const latestRunText = latestTrainingRun.value
    ? `；最近训练任务：${latestTrainingRun.value.run_id}（${statusText(latestTrainingRun.value.status)}）`
    : ''
  if (!model) return `暂无已完成模型。第一个任务请选择官方预训练模型，后续排队任务再选这里${latestRunText}。`
  const score = model.map50 != null ? `，mAP50 ${fmtMetric(model.map50)}` : ''
  return `${displayModelName(model)}，来源训练 ${model.source_training_display_name || model.run_id || '-'}${score}${latestRunText}`
})
const selectedBaseModelHint = computed(() => {
  if (String(trainForm.base_model || '').startsWith(TRAINING_RUN_MODEL_PREFIX)) {
    const runId = Number(String(trainForm.base_model).slice(TRAINING_RUN_MODEL_PREFIX.length))
    const run = (project.value?.training_runs || []).find(item => Number(item.id) === runId)
    if (!run) return ''
    return `队列启动时会使用训练任务 ${displayTrainingName(run)} 产出的模型；如果该任务失败，当前任务会失败并提示原因。`
  }
  const selected = (project.value?.models || []).find(item => {
    const weight = item.best_pt_path || item.last_pt_path || ''
    return weight && weight === trainForm.base_model
  })
  if (!selected) return ''
  const score = selected.map50 != null ? `，mAP50 ${fmtMetric(selected.map50)}` : ''
  return `将使用已产出模型继续训练：${displayModelName(selected)}，来源任务 ${selected.source_training_display_name || selected.run_id || '-'}${score}`
})
const queueTrainingRunOptions = computed(() => {
  return (project.value?.training_runs || []).filter(run => {
    if (run.status === 'failed') return false
    return run.status === 'created' || run.status === 'running' || run.status === 'completed'
  })
})
const featuredModel = computed(() => {
  const rows = project.value?.models || []
  return rows.find(item => item.is_production) || rows.find(item => item.is_candidate) || rows[0] || null
})

// 训练数据：只允许有标注且不是 val/test/annotation 的数据集
const labeledVersions = computed(() => versions.value.filter(v => {
  const dt = (v.dtype || '').trim()
  if (dt === 'val' || dt === 'test' || dt === 'annotation') return false
  return Number(v.label_file_count || 0) > 0
}))
// 验证/测试数据：有标注的数据集（排除标注中）
const allVersionsForEval = computed(() => {
  return versions.value.filter(v => {
    const dt = (v.dtype || '').trim()
    if (dt === 'annotation') return false
    return Number(v.label_file_count || 0) > 0
  })
})

function dtypeLabel(item) {
  const dt = (item.dtype || '').trim()
  const map = { train: '训练集', val: '验证集', test: '测试/推理集', annotation: '标注中' }
  if (map[dt]) return map[dt]
  return Number(item.label_file_count || 0) > 0 ? '有标注' : '全量'
}

const quickAgentPrompts = [
  '分析最近一次训练是否过拟合，并给出下一轮参数建议。',
  '根据最近一次验证结果，生成补数与复标计划。',
  '对比当前主模型和最近训练的 best.pt，判断是否应该晋升。',
]

const agentHeadline = computed(() => {
  if (latestEvaluationRun.value) return `优先分析 ${latestEvaluationRun.value.run_id}`
  if (latestTrainingRun.value) return `优先分析 ${latestTrainingRun.value.run_id}`
  return '先进入 Agent 建立项目上下文'
})

onMounted(() => load())
onActivated(() => load({ silent: true }))  // keep-alive 切回时静默刷新

async function loadGpu() {
  try {
    const rt = await getRuntime()
    gpuList.value = (rt.gpu?.devices || []).map(d => ({ device: `cuda:${d.index}`, label: `${d.name} · ${d.memory_total_gb}GB` }))
  } catch { gpuList.value = [] }
}

async function load(options = {}) {
  const { silent = false } = options
  if (!silent) loading.value = true
  error.value = ''
  try {
    const [projectData, verResp] = await Promise.all([getProject(route.params.id), listVersions(), loadGpu()])
    const versionData = verResp.items
    project.value = projectData
    versions.value = versionData
    setActiveProjectContext(projectData)
    // 记住上次选择的训练数据
    const lastTrainId = localStorage.getItem(`proj_${projectData.id}_train_dsid`)
    if (lastTrainId && labeledVersions.value.find(v => v.id === Number(lastTrainId))) {
      trainForm.dataset_version_id = Number(lastTrainId)
    }
    // 记住上次选择的验证数据
    const lastEvalId = localStorage.getItem(`proj_${projectData.id}_eval_dsid`)
    if (lastEvalId && allVersionsForEval.value.find(v => v.id === Number(lastEvalId))) {
      evalForm.dataset_version_id = Number(lastEvalId)
    }
    // 优先选生产模型
    const prod = projectData.models.find(m => m.is_production) || projectData.models[0]
    if (!evalForm.model_version_id && prod) {
      evalForm.model_version_id = prod.id
    }
    // 从 URL 查询参数预填训练参数
    const q = route.query
    if (q.epochs) trainForm.epochs = parseInt(q.epochs)
    if (q.imgsz) trainForm.imgsz = parseInt(q.imgsz)
    if (q.batch) trainForm.batch = parseInt(q.batch)
    if (q.base_model) trainForm.base_model = q.base_model
    if (q.device) trainForm.device = q.device
  } catch (err) {
    error.value = formatError(err, '项目加载失败')
  } finally {
    if (!silent) loading.value = false
  }
}

async function startTraining() {
  actionMsg.value = ''
  actionError.value = ''
  if (!trainForm.dataset_version_id) {
    actionError.value = '请先选择训练数据'
    return
  }
  try {
    localStorage.setItem(`proj_${project.value.id}_train_dsid`, String(trainForm.dataset_version_id))
    await createProjectTrainingRun(project.value.id, { ...trainForm, run_name: trainForm.run_name || null })
    actionMsg.value = '训练任务已创建。'
    activeTab.value = 'training'
    await load({ silent: true })
  } catch (err) {
    actionError.value = formatError(err, '训练启动失败')
  }
}

async function startEvaluation() {
  actionMsg.value = ''
  actionError.value = ''
  if (!evalForm.model_version_id || !evalForm.dataset_version_id) {
    actionError.value = '请先选择模型和验证数据'
    return
  }
  try {
    localStorage.setItem(`proj_${project.value.id}_eval_dsid`, String(evalForm.dataset_version_id))
    await createProjectEvaluationRun(project.value.id, { ...evalForm })
    actionMsg.value = '验证任务已创建。'
    activeTab.value = 'evaluation'
    await load({ silent: true })
  } catch (err) {
    actionError.value = formatError(err, '验证启动失败')
  }
}

async function saveModelNotes(run, value) {
  const notes = (value || '').trim()
  if (notes === (run.model_notes || run.notes || '')) return
  try {
    if (run.model_id) {
      await updateModel(run.model_id, { model_name: run.model_name || run.run_id, notes })
      run.model_notes = notes
    } else {
      await updateRun(run.id, { notes })
      run.notes = notes
    }
  } catch (e) { /* 静默 */ }
}

async function deleteTrainingRun(run) {
  if (!confirm(`确认删除训练「${run.run_id}」？关联的模型也会被删除。`)) return
  try { await deleteRun(run.id); await load({ silent: true }) } catch (e) { alert(e?.message || '删除失败') }
}
async function deleteEvalRun(run) {
  if (!confirm(`确认删除验证「${run.run_id}」？`)) return
  try { await del(`/evaluation-runs/${run.id}`); await load({ silent: true }) } catch (e) { alert(e?.message || '删除失败') }
}
async function deleteModel(model) {
  if (!confirm(`确认删除模型「${model.run_id}」？`)) return
  try { await deleteModelApi(model.id); await load({ silent: true }) } catch (e) { alert(e?.message || '删除失败') }
}

function shortPath(path) {
  if (!path) return ''
  const n = String(path).replace(/\\/g, '/')
  return n.split('/').pop() || n
}

function modelBaseLabel(model) {
  const base = shortPath(model?.base_model || '')
  if (!base) return '-'
  return base.replace(/\.(pt|yaml)$/i, '')
}

function archLabel(path) {
  if (!path) return '-'
  if (path === LATEST_PROJECT_MODEL_SENTINEL) return '最新项目模型'
  if (String(path).startsWith(TRAINING_RUN_MODEL_PREFIX)) return '指定任务产物'
  const n = String(path).replace(/\\/g, '/').split('/').pop().toLowerCase()
  const archMap = {
    'yolo11n.pt': 'YOLO11n', 'yolo11s.pt': 'YOLO11s', 'yolo11m.pt': 'YOLO11m', 'yolo11l.pt': 'YOLO11l', 'yolo11x.pt': 'YOLO11x',
    'yolov8n.pt': 'YOLOv8n', 'yolov8s.pt': 'YOLOv8s', 'yolov8m.pt': 'YOLOv8m', 'yolov8l.pt': 'YOLOv8l', 'yolov8x.pt': 'YOLOv8x',
    'yolov5n.pt': 'YOLOv5n', 'yolov5s.pt': 'YOLOv5s', 'yolov5m.pt': 'YOLOv5m', 'yolov5l.pt': 'YOLOv5l', 'yolov5x.pt': 'YOLOv5x',
  }
  if (archMap[n]) return archMap[n]
  const stem = n.replace(/\.pt$/i, '')
  return stem.length > 1 ? stem.charAt(0).toUpperCase() + stem.slice(1) : stem || n
}

function statusChipClass(status) {
  return {
    completed: 'success',
    running: 'info',
    failed: 'danger',
    created: 'warning',
    pending: 'warning',
  }[status] || ''
}

function modelState(model) {
  return model?.is_production ? '生产' : '归档'
}

function openAgentWorkspace() {
  if (project.value) setActiveProjectContext(project.value)
  router.push('/agent')
}

function openAgentPrompt(prompt) {
  if (project.value) setActiveProjectContext(project.value)
  router.push({ path: '/agent', query: { q: prompt } })
}

</script>
