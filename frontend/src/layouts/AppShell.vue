<template>
  <LoginPage v-if="authReady && needLogin" @login-success="onLoginSuccess" />

  <div v-else-if="authReady" class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/">
        <div class="brand-mark brand-mark--glow">
          <svg viewBox="0 0 32 32" width="32" height="32" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="g1" x1="0" y1="0" x2="32" y2="32">
                <stop offset="0%" stop-color="#FDB97B"/>
                <stop offset="100%" stop-color="#fff"/>
              </linearGradient>
              <linearGradient id="g2" x1="0" y1="32" x2="32" y2="0">
                <stop offset="0%" stop-color="#fff"/>
                <stop offset="100%" stop-color="#FDE68A"/>
              </linearGradient>
            </defs>
            <g transform="rotate(-6, 16, 16)" opacity="0.5">
              <path d="M3 11V5.5A2.5 2.5 0 0 1 5.5 3H11" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
              <path d="M21 3h5.5A2.5 2.5 0 0 1 29 5.5V11" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
              <path d="M29 21v5.5A2.5 2.5 0 0 1 26.5 29H21" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
              <path d="M11 29H5.5A2.5 2.5 0 0 1 3 26.5V21" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
            </g>
            <g transform="rotate(3, 16, 16)" opacity="0.75">
              <path d="M5 12V6a1 1 0 0 1 1-1h6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M20 5h6a1 1 0 0 1 1 1v6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M27 20v6a1 1 0 0 1-1 1h-6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M12 27H6a1 1 0 0 1-1-1v-6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
            </g>
            <g>
              <path d="M8 14v-3.5A1.5 1.5 0 0 1 9.5 9H14" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
              <path d="M18 9h3.5A1.5 1.5 0 0 1 23 10.5V14" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
              <path d="M23 18v3.5a1.5 1.5 0 0 1-1.5 1.5H18" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
              <path d="M14 23H10.5A1.5 1.5 0 0 1 9 21.5V18" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
            </g>
            <circle cx="16" cy="16" r="2.5" fill="#fff" opacity="0.95"/>
            <circle cx="16" cy="16" r="4.5" stroke="#fff" stroke-width="0.8" opacity="0.4"/>
            <circle cx="16" cy="16" r="6.5" stroke="#fff" stroke-width="0.5" opacity="0.2"/>
            <line x1="16" y1="7" x2="16" y2="10.5" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <line x1="16" y1="21.5" x2="16" y2="25" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <line x1="7" y1="16" x2="10.5" y2="16" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <line x1="21.5" y1="16" x2="25" y2="16" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <circle cx="5" cy="5" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <circle cx="27" cy="5" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <circle cx="27" cy="27" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <circle cx="5" cy="27" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <line x1="5" y1="5" x2="9" y2="9" stroke="#FDE68A" stroke-width="0.6" opacity="0.4"/>
            <line x1="27" y1="5" x2="23" y2="9" stroke="#FDE68A" stroke-width="0.6" opacity="0.4"/>
            <line x1="27" y1="27" x2="23" y2="23" stroke="#FDE68A" stroke-width="0.6" opacity="0.4"/>
            <line x1="5" y1="27" x2="9" y2="23" stroke="#FDE68A" stroke-width="0.6" opacity="0.4"/>
          </svg>
        </div>
        <div>
          <strong>YOLOps Agent</strong>
          <span>工程化训练工作台</span>
        </div>
      </RouterLink>

      <nav class="nav">
        <RouterLink v-for="item in navItems" :key="item.to" class="nav-item" :to="item.to">
          <span class="nav-icon"><AppIcon :name="item.icon" /></span>
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <RouterLink class="settings-button" to="/settings">
        <span class="nav-icon"><AppIcon name="settings" /></span>
        <span>系统设置</span>
      </RouterLink>
      <button class="lock-button" @click="doLock" title="锁定工作台">
        <span class="nav-icon"><AppIcon name="lock" /></span>
        <span>锁定工作台</span>
      </button>
    </aside>

    <main class="workspace">
      <header class="topbar topbar-compact">
        <div class="gpu-pill" :title="runtimeTitle">
          <span :class="{ off: !runtimeOk }"></span>
          {{ runtimeLabel }}
        </div>
        <RouterLink class="secondary-action small-action topbar-quick-action" to="/training?create=1">
          <AppIcon name="train" />
          <span>全局训练</span>
        </RouterLink>
        <button class="notification-toggle" title="启用系统通知" @click="enableBrowserNotifications">
          通知
          <span v-if="notificationState.items.length" class="notification-dot">{{ notificationState.items.length }}</span>
        </button>
      </header>

      <RouterView v-slot="{ Component }">
        <keep-alive :max="12">
          <component :is="Component" />
        </keep-alive>
      </RouterView>
    </main>

    <div class="notification-stack">
      <div
        v-for="item in notificationState.items"
        :key="item.id"
        :class="['notification-card', `notification-card--${item.tone}`]"
      >
        <div>
          <strong>{{ item.title }}</strong>
          <p>{{ item.message }}</p>
        </div>
        <RouterLink v-if="item.url" class="notification-link" :to="item.url">查看</RouterLink>
        <button class="notification-close" @click="dismissNotification(item.id)">×</button>
      </div>
    </div>
  </div>

  <div v-else class="auth-splash">
    <div class="auth-splash-card">
      <div class="auth-splash-glow"></div>
      <div class="auth-splash-icon">
        <AppIcon name="lock" />
      </div>
      <strong>正在检查访问门禁</strong>
      <span>校验共享密码状态和本地会话令牌…</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { listNotificationJobs } from '../api/notifications.js'
import { getRuntime } from '../api/system.js'
import { clearToken, getAuthStatus, logout as logoutApi, saveToken, verifyToken } from '../api/auth.js'
import AppIcon from '../components/AppIcon.vue'
import LoginPage from '../pages/LoginPage.vue'
import {
  dismissNotification,
  notificationState,
  pushNotification,
  requestBrowserNotificationPermission,
} from '../state/notifications.js'

const authReady = ref(false)
const needLogin = ref(false)
const runtime = ref(null)
const runtimeOk = ref(false)

let notificationTimer = null
let notificationPrimed = false
const jobStatusMap = new Map()

const navItems = [
  { to: '/', label: '概览', icon: 'home' },
  { to: '/projects', label: '项目', icon: 'projects' },
  { to: '/datasets', label: '数据集', icon: 'database' },
  { to: '/annotation', label: '标注', icon: 'annotate' },
  { to: '/training', label: '训练', icon: 'train' },
  { to: '/registry', label: '模型', icon: 'model' },
  { to: '/inference', label: '推理', icon: 'activity' },
  { to: '/agent', label: 'Agent', icon: 'agent' },
]

const runtimeLabel = computed(() => {
  if (!runtimeOk.value) return '后端未连接'
  const gpu = runtime.value?.gpu?.summary || 'CPU'
  const db = runtime.value?.database
  const dbText = db?.backend === 'postgres' ? `PostgreSQL ${db.port}` : 'SQLite / 项目本地'
  return `${gpu} | ${dbText}`
})

const runtimeTitle = computed(() => {
  if (!runtimeOk.value) return '后端未连接'
  const db = runtime.value?.database || {}
  if (db.backend === 'sqlite') {
    return `数据目录：${db.data_dir || '-'}`
  }
  return `数据库：${db.backend || '-'}`
})

async function checkAuth() {
  authReady.value = false
  try {
    const status = await getAuthStatus()
    if (!status?.enabled) {
      needLogin.value = false
      await onSessionReady()
      return
    }

    needLogin.value = !(await verifyToken())
    if (!needLogin.value) {
      await onSessionReady()
    } else {
      clearSessionState()
    }
  } catch {
    needLogin.value = true
    clearSessionState()
  } finally {
    authReady.value = true
  }
}

async function onSessionReady() {
  await loadRuntime()
  startNotificationPolling()
}

function clearSessionState() {
  stopNotificationPolling()
  runtime.value = null
  runtimeOk.value = false
}

async function onLoginSuccess(token) {
  if (token && token !== 'disabled') {
    saveToken(token)
  }
  needLogin.value = false
  await onSessionReady()
}

function onAuthRequired() {
  clearToken()
  needLogin.value = true
  clearSessionState()
}

async function doLock() {
  await logoutApi()
  clearToken()
  needLogin.value = true
  clearSessionState()
}

onMounted(async () => {
  window.addEventListener('auth-required', onAuthRequired)
  await checkAuth()
})

onUnmounted(() => {
  window.removeEventListener('auth-required', onAuthRequired)
  stopNotificationPolling()
})

async function loadRuntime() {
  try {
    runtime.value = await getRuntime()
    runtimeOk.value = true
  } catch {
    runtimeOk.value = false
  }
}

function stopNotificationPolling() {
  if (notificationTimer) {
    clearInterval(notificationTimer)
    notificationTimer = null
  }
  notificationPrimed = false
  jobStatusMap.clear()
}

function startNotificationPolling() {
  stopNotificationPolling()
  pollNotifications()
  notificationTimer = setInterval(pollNotifications, 5000)
}

async function pollNotifications() {
  try {
    const jobs = await listNotificationJobs()
    for (const job of jobs || []) {
      const previous = jobStatusMap.get(job.key)
      jobStatusMap.set(job.key, job.status)
      if (!notificationPrimed) continue
      const finished = job.status === 'completed' || job.status === 'failed'
      const changed = previous && previous !== job.status
      if (finished && changed) pushNotification(notificationPayload(job))
    }
    notificationPrimed = true
  } catch {
    // keep the shell usable even when notification polling fails
  }
}

function notificationPayload(job) {
  const ok = job.status === 'completed'
  const kindText = {
    training: '训练',
    evaluation: '验证',
    model_export: '模型导出',
  }[job.kind] || '任务'
  return {
    tone: ok ? 'success' : 'danger',
    title: `${kindText}${ok ? '完成' : '失败'}`,
    message: `${job.name}${job.summary ? ` · ${job.summary}` : ''}${!ok && job.error ? ` · ${job.error}` : ''}`,
    url: job.url || '',
    duration: ok ? 9000 : 14000,
  }
}

async function enableBrowserNotifications() {
  const result = await requestBrowserNotificationPermission()
  if (result === 'granted') {
    pushNotification({ tone: 'success', title: '系统通知已启用', message: '训练、验证和导出完成后会提示。' })
  } else {
    pushNotification({ tone: 'info', title: '站内通知已启用', message: '浏览器通知未授权，仍会显示站内通知。' })
  }
}
</script>
