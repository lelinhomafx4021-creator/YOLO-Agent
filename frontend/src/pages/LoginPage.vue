<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-hero">
        <div class="login-icon-wrap">
          <AppIcon name="lock" />
        </div>
        <div class="login-header">
          <h1>YOLOps Agent</h1>
        </div>
      </div>

      <div class="login-body">
        <label class="form-field">
          <span>访问密码</span>
          <input
            v-model="password"
            type="password"
            placeholder="输入共享密码"
            @keyup.enter="doLogin"
            autofocus
          />
        </label>

        <button class="primary-action full login-submit" :disabled="!password.trim() || loading" @click="doLogin">
          <AppIcon v-if="!loading" name="lock" />
          {{ loading ? '验证中...' : '进入工作台' }}
        </button>

        <p v-if="error" class="error login-error">{{ error }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AppIcon from '../components/AppIcon.vue'
import { login as loginApi } from '../api/auth.js'

const emit = defineEmits(['login-success'])

const password = ref('')
const loading = ref(false)
const error = ref('')

async function doLogin() {
  if (!password.value.trim() || loading.value) return

  loading.value = true
  error.value = ''

  try {
    const result = await loginApi(password.value.trim())
    password.value = ''
    emit('login-success', result.token)
  } catch (err) {
    error.value = err?.message || '密码错误'
    password.value = ''
  } finally {
    loading.value = false
  }
}
</script>
