<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-header">
        <h1>YOLOps-Agent</h1>
        <p>工业 YOLO 目标检测管理平台</p>
      </div>
      <div class="login-body">
        <div class="form-field">
          <span>访问密码</span>
          <input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            @keyup.enter="doLogin"
            autofocus
          />
        </div>
        <button class="primary-action full" :disabled="!password || loading" @click="doLogin">
          {{ loading ? '验证中...' : '进入系统' }}
        </button>
        <p v-if="error" class="error">{{ error }}</p>
        <p class="helper-text" style="text-align:center;margin-top:8px">弱密码门禁，仅防止误操作</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['login-success'])

// 前端弱密码 — 不改后端，纯粹的页面门禁
const GATE_PASSWORD = 'yolops'

const password = ref('')
const loading = ref(false)
const error = ref('')

async function doLogin() {
  if (!password.value) return
  loading.value = true
  error.value = ''
  // 模拟短暂延迟，避免太快闪过
  await new Promise(r => setTimeout(r, 300))
  if (password.value === GATE_PASSWORD) {
    emit('login-success')
  } else {
    error.value = '密码错误'
    password.value = ''
  }
  loading.value = false
}
</script>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #F6F2EE 0%, #EDE4DA 50%, #FBFAF8 100%);
}
.login-card {
  width: 360px; background: var(--card); border-radius: 13px;
  box-shadow: 0 8px 32px rgba(30,27,25,0.08); overflow: hidden;
}
.login-header {
  padding: 32px 28px 16px; text-align: center;
  background: linear-gradient(180deg, var(--primary-light) 0%, transparent 100%);
}
.login-header h1 { margin:0; font-size:22px; color:var(--primary); }
.login-header p { margin:4px 0 0; font-size:12px; color:var(--muted); }
.login-body { padding: 16px 28px 28px; display:flex; flex-direction:column; gap:10px; }
.login-body .form-field span { font-size:12px; color:var(--muted); }
.login-body input {
  width:100%; padding:10px 12px; font-size:14px; border:1px solid var(--line-soft);
  border-radius:8px; margin-top:4px; box-sizing:border-box;
}
.login-body input:focus { border-color:var(--primary); outline:none; }
</style>
