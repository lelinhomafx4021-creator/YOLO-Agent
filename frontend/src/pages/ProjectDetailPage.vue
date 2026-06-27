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
          <strong>{{ latestTrainingRun?.run_id || '-' }}</strong>
          <small>{{ latestTrainingRun ? `${statusText(latestTrainingRun.status)} / ${latestTrainingRun.epochs} epochs` : '还没有训练记录' }}</small>
        </div>
        <div class="project-summary-card">
          <span>最近验证</span>
          <strong>{{ latestEvaluationRun?.run_id || '-' }}</strong>
          <small>{{ latestEvaluationRun ? `mAP50-95 ${fmtMetric(latestEvaluationRun.map50_95)}` : '还没有验证记录' }}</small>
        </div>
        <div class="project-summary-card">
          <span>当前主模型</span>
          <strong>{{ featuredModel?.model_name || featuredModel?.run_id || '-' }}</strong>
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
          <div><span>最近训练</span><strong>{{ latestTrainingRun?.run_id || '-' }}</strong></div>
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
                <optgroup v-if="project.models.length" label="已有模型（断点续训）">
                  <option v-for="m in project.models" :key="m.id" :value="m.best_pt_path">
                    {{ m.model_name || m.run_id }} (mAP50: {{ fmtMetric(m.map50) }})
                  </option>
                </optgroup>
              </select>
            </label>
            <label class="form-field"><span>epochs</span><input v-model.number="trainForm.epochs" type="number" min="1" /></label>
            <div style="display:flex;gap:6px">
              <label class="form-field" style="flex:1;min-width:0"><span>优化器</span>
                <select v-model="trainForm.optimizer" style="width:100%">
                  <option value="auto">auto</option>
                  <option value="SGD">SGD</option>
                  <option value="Adam">Adam</option>
                  <option value="AdamW">AdamW</option>
                </select>
              </label>
              <label class="form-field" style="flex:1;min-width:0"><span>lr0</span><input v-model="trainForm.lr0" placeholder="0.01" style="width:100%" /></label>
            </div>
            <div style="display:flex;gap:6px">
              <label class="form-field" style="flex:1;min-width:0"><span>尺寸</span><input v-model.number="trainForm.imgsz" type="number" min="64" style="width:100%" /></label>
              <label class="form-field" style="flex:1;min-width:0"><span>Batch</span><input v-model.number="trainForm.batch" type="number" min="1" style="width:100%" /></label>
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
                    <RouterLink class="task-name-link" :to="`/training/${run.id}`">{{ run.run_id }}</RouterLink>
                  </td>
                  <td class="muted-text" style="max-width:120px">{{ run.dataset_name }}</td>
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
                  {{ model.model_name || model.run_id }} (mAP50-95: {{ fmtMetric(model.map50_95) }})
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
            <table>
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
                  <td>{{ run.run_id }}</td>
                  <td>{{ run.model_name || run.model_run_id || '-' }}</td>
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
          <div><span>当前主模型</span><strong>{{ featuredModel?.run_id || '-' }}</strong></div>
          <div><span>模型总数</span><strong>{{ project.models.length }}</strong></div>
        </div>
        <div class="table-card section-pad">
          <table>
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
                <td>{{ model.model_name || model.run_id }}</td>
                <td>{{ model.base_model }}<span v-if="model.model_format" class="chip" style="margin-left:4px;font-size:9px">{{ model.model_format.toUpperCase() }}</span></td>
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

      <section v-if="activeTab === 'agent'" class="card section-pad compact-detail-section">
        <div class="card-title">
          <strong>项目 Agent</strong>
          <span>围绕这个项目的训练、验证、模型和数据分布做对话分析。</span>
        </div>
        <div class="detail-grid">
          <div class="info-item"><span>可读数据批次</span><strong>{{ project.datasets.length }}</strong></div>
          <div class="info-item"><span>可读训练记录</span><strong>{{ project.training_runs.length }}</strong></div>
          <div class="info-item"><span>可读验证记录</span><strong>{{ project.evaluation_runs.length }}</strong></div>
          <div class="info-item"><span>可读模型记录</span><strong>{{ project.models.length }}</strong></div>
        </div>
        <div class="project-agent-grid">
          <div class="project-context-list">
            <div class="project-context-item">
              <span>最近训练关注点</span>
              <strong>{{ latestTrainingRun ? `${latestTrainingRun.run_id} / ${statusText(latestTrainingRun.status)}` : '暂无训练记录' }}</strong>
            </div>
            <div class="project-context-item">
              <span>最近验证关注点</span>
              <strong>{{ latestEvaluationRun ? `${latestEvaluationRun.run_id} / mAP50-95 ${fmtMetric(latestEvaluationRun.map50_95)}` : '暂无验证记录' }}</strong>
            </div>
            <div class="project-context-item">
              <span>当前模型关注点</span>
              <strong>{{ featuredModel ? `${featuredModel.run_id} / ${modelState(featuredModel)}` : '暂无模型记录' }}</strong>
            </div>
          </div>
          <div class="project-context-list project-prompt-list">
            <div v-for="prompt in quickAgentPrompts" :key="prompt" class="project-context-item">
              <span>推荐分析主题</span>
              <strong>{{ prompt }}</strong>
            </div>
          </div>
        </div>
        <div class="button-row section-actions">
          <RouterLink class="primary-action" to="/agent">打开项目对话</RouterLink>
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
import { useRoute } from 'vue-router'
import { listVersions } from '../api/datasets.js'
import { createProjectEvaluationRun, createProjectTrainingRun, getProject } from '../api/projects.js'
import { deleteRun, updateRun } from '../api/training.js'
import { updateModel } from '../api/models.js'
import { getRuntime } from '../api/system.js'
import { deleteModel as deleteModelApi } from '../api/models.js'
import { setActiveProjectContext } from '../state/projectContext.js'
import { fmtMetric, formatError, shortTime, statusText } from '../utils.js'
import { del } from '../api/client.js'

const route = useRoute()
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

onMounted(load)
onActivated(load)  // keep-alive 切回时自动刷新

async function loadGpu() {
  try {
    const rt = await getRuntime()
    gpuList.value = (rt.gpu?.devices || []).map(d => ({ device: `cuda:${d.index}`, label: `${d.name} · ${d.memory_total_gb}GB` }))
  } catch { gpuList.value = [] }
}

async function load() {
  loading.value = true
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
    loading.value = false
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
    await load()
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
    await load()
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
  try { await deleteRun(run.id); await load() } catch (e) { alert(e?.message || '删除失败') }
}
async function deleteEvalRun(run) {
  if (!confirm(`确认删除验证「${run.run_id}」？`)) return
  try { await del(`/evaluation-runs/${run.id}`); await load() } catch (e) { alert(e?.message || '删除失败') }
}
async function deleteModel(model) {
  if (!confirm(`确认删除模型「${model.run_id}」？`)) return
  try { await deleteModelApi(model.id); await load() } catch (e) { alert(e?.message || '删除失败') }
}

function archLabel(path) {
  if (!path) return '-'
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

</script>
