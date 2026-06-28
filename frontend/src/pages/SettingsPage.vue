<template>
  <section class="page">
    <div class="page-header">
      <div>
        <h1>系统设置</h1>
        <p>修改 Agent、LLM、训练设备和共享门禁密码。普通运行参数会写入后端 `settings.json`。</p>
      </div>
      <button class="primary-action" @click="save" :disabled="saving">
        <AppIcon name="check" />
        {{ saving ? '保存中...' : '保存设置' }}
      </button>
    </div>

    <div v-if="loading" class="loading">正在加载设置...</div>
    <p v-else-if="error" class="error">{{ error }}</p>

    <div v-else class="settings-grid">
      <section class="card" style="padding:10px 14px">
        <div class="card-title" style="padding:0 0 6px">
          <strong>运行环境</strong>
          <span>只读</span>
        </div>
        <div class="table-card compact-table">
          <table>
            <tbody>
              <tr><td style="width:80px">后端</td><td>{{ runtime?.backend || 'FastAPI' }}</td></tr>
              <tr><td>数据库</td><td>{{ databaseLabel }}</td></tr>
              <tr><td>数据目录</td><td class="mono muted-text">{{ runtime?.database?.data_dir || 'backend/data' }}</td></tr>
              <tr><td>计算设备</td><td>{{ runtime?.gpu?.summary || 'CPU' }}</td></tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="card settings-panel">
        <div class="card-title"><strong>Agent 模式</strong><span>可保存</span></div>
        <div class="settings-list form-stack">
          <label class="form-field">
            <span>分析模式</span>
            <select v-model="settings.agent_mode" @change="autoSave">
              <option value="rule">规则分析（本地计算，零成本）</option>
              <option value="llm">LLM 辅助（AI 主动查询数据）</option>
            </select>
            <span class="hint" v-if="settings.agent_mode === 'llm'">启用前先把下面的 LLM 接口测通。</span>
          </label>
          <label class="form-field">
            <span>默认训练设备</span>
            <input v-model="settings.gpu_device" placeholder="cuda:0 或 cpu" @change="autoSave" />
          </label>
        </div>
      </section>

      <section class="card settings-panel">
        <div class="card-title"><strong>LLM 接口</strong><span>DeepSeek / OpenAI 兼容</span></div>
        <div class="settings-list form-stack">
          <label class="form-field">
            <span>API 端点</span>
            <input v-model="settings.llm_endpoint" placeholder="https://api.deepseek.com/v1" @change="autoSave" />
          </label>
          <label class="form-field">
            <span>模型名称</span>
            <input v-model="settings.llm_model" placeholder="deepseek-chat" @change="autoSave" />
          </label>
          <label class="form-field">
            <span>API Key</span>
            <input v-model="settings.llm_api_key" type="password" placeholder="sk-..." @change="autoSave" />
          </label>
          <button class="secondary-action" @click="testConnection" :disabled="testingConn">
            {{ testingConn ? '测试中...' : '测试连接' }}
          </button>
          <p v-if="connResult" :class="connOk ? 'action-msg' : 'error'">{{ connResult }}</p>
        </div>
      </section>

      <section class="card settings-panel">
        <div class="card-title"><strong>访问密码</strong><span>共享弱密码门禁</span></div>
        <div class="settings-list form-stack">
          <label class="form-field">
            <span>原密码</span>
            <input v-model="passwordForm.oldPassword" type="password" placeholder="先输入当前密码" />
          </label>
          <label class="form-field">
            <span>新密码</span>
            <input v-model="passwordForm.newPassword" type="password" placeholder="设置新的共享密码" />
          </label>
          <label class="form-field">
            <span>确认新密码</span>
            <input v-model="passwordForm.confirmPassword" type="password" placeholder="再次输入新密码" />
          </label>
          <button class="secondary-action" @click="updatePassword" :disabled="changingPassword">
            {{ changingPassword ? '更新中...' : '更新密码' }}
          </button>
          <p v-if="passwordMsg" :class="passwordOk ? 'action-msg' : 'error'">{{ passwordMsg }}</p>
          <p class="helper-text">修改后旧密码立即失效，当前会话会自动切换到新的登录令牌。</p>
        </div>
      </section>

      <section class="card settings-panel">
        <div class="card-title"><strong>工作区路径</strong><span>后端管理</span></div>
        <div class="settings-list">
          <p>数据集：backend/data/datasets</p>
          <p>上传暂存：backend/data/uploads</p>
          <p>训练输出：backend/data/runs</p>
          <p>模型仓库：backend/data/model_registry</p>
        </div>
      </section>
    </div>

    <p v-if="saveMsg" class="save-indicator">{{ saveMsg }}</p>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { changePassword as changePasswordApi, saveToken } from '../api/auth.js'
import { getSettings, testConnection as apiTestConnection, updateSettings } from '../api/settings.js'
import { getRuntime } from '../api/system.js'

const loading = ref(true)
const saving = ref(false)
const testingConn = ref(false)
const changingPassword = ref(false)
const error = ref('')
const saveMsg = ref('')
const connResult = ref('')
const connOk = ref(false)
const passwordMsg = ref('')
const passwordOk = ref(false)
const settings = ref({})
const runtime = ref(null)
const passwordForm = ref({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
})

const databaseLabel = computed(() => {
  const db = runtime.value?.database
  if (!db) return 'SQLite'
  if (db.backend === 'postgres') return `PostgreSQL ${db.host}:${db.port}`
  return `SQLite：${db.sqlite_path || 'backend/data/yolops.db'}`
})

onMounted(async () => {
  try {
    const [settingsData, runtimeData] = await Promise.all([getSettings(), getRuntime()])
    settings.value = settingsData
    runtime.value = runtimeData
  } catch (err) {
    error.value = err.message || '设置加载失败'
  } finally {
    loading.value = false
  }
})

let autoSaveTimer = null
function autoSave() {
  clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => save(), 300)
}

async function save() {
  saving.value = true
  saveMsg.value = ''
  try {
    settings.value = await updateSettings(settings.value)
    saveMsg.value = '设置已保存'
    setTimeout(() => { saveMsg.value = '' }, 1800)
  } catch (err) {
    saveMsg.value = `保存失败：${err.message}`
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testingConn.value = true
  connResult.value = ''
  connOk.value = false
  try {
    await updateSettings(settings.value)
    const data = await apiTestConnection()
    connOk.value = data.ok
    connResult.value = data.ok ? '连接成功' : `连接失败：${data.error || '未知错误'}`
  } catch (err) {
    connResult.value = `连接失败：${err.message}`
  } finally {
    testingConn.value = false
  }
}

async function updatePassword() {
  const { oldPassword, newPassword, confirmPassword } = passwordForm.value
  passwordMsg.value = ''
  passwordOk.value = false

  if (!oldPassword || !newPassword || !confirmPassword) {
    passwordMsg.value = '请先填写完整的密码信息'
    return
  }
  if (newPassword !== confirmPassword) {
    passwordMsg.value = '两次输入的新密码不一致'
    return
  }
  if (newPassword.trim().length < 3) {
    passwordMsg.value = '新密码至少 3 位'
    return
  }

  changingPassword.value = true
  try {
    const result = await changePasswordApi(oldPassword, newPassword)
    if (result?.token) saveToken(result.token)
    passwordForm.value = { oldPassword: '', newPassword: '', confirmPassword: '' }
    passwordOk.value = true
    passwordMsg.value = '共享密码已更新'
  } catch (err) {
    passwordMsg.value = err.message || '更新密码失败'
  } finally {
    changingPassword.value = false
  }
}
</script>
