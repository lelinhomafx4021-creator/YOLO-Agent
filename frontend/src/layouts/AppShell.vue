<template>
  <LoginPage v-if="needLogin" @login-success="onLoginSuccess" />
  <div v-else class="app-shell">
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
            <!-- 外层大检测框 (微旋转) -->
            <g transform="rotate(-6, 16, 16)" opacity="0.5">
              <path d="M3 11V5.5A2.5 2.5 0 0 1 5.5 3H11" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
              <path d="M21 3h5.5A2.5 2.5 0 0 1 29 5.5V11" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
              <path d="M29 21v5.5A2.5 2.5 0 0 1 26.5 29H21" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
              <path d="M11 29H5.5A2.5 2.5 0 0 1 3 26.5V21" stroke="url(#g1)" stroke-width="1.4" stroke-linecap="round"/>
            </g>
            <!-- 中层检测框 (微旋转) -->
            <g transform="rotate(3, 16, 16)" opacity="0.75">
              <path d="M5 12V6a1 1 0 0 1 1-1h6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M20 5h6a1 1 0 0 1 1 1v6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M27 20v6a1 1 0 0 1-1 1h-6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
              <path d="M12 27H6a1 1 0 0 1-1-1v-6" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/>
            </g>
            <!-- 内层检测框 -->
            <g>
              <path d="M8 14v-3.5A1.5 1.5 0 0 1 9.5 9H14" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
              <path d="M18 9h3.5A1.5 1.5 0 0 1 23 10.5V14" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
              <path d="M23 18v3.5a1.5 1.5 0 0 1-1.5 1.5H18" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
              <path d="M14 23H10.5A1.5 1.5 0 0 1 9 21.5V18" stroke="url(#g2)" stroke-width="2" stroke-linecap="round"/>
            </g>
            <!-- 中心发光点 -->
            <circle cx="16" cy="16" r="2.5" fill="#fff" opacity="0.95"/>
            <circle cx="16" cy="16" r="4.5" stroke="#fff" stroke-width="0.8" opacity="0.4"/>
            <circle cx="16" cy="16" r="6.5" stroke="#fff" stroke-width="0.5" opacity="0.2"/>
            <!-- 准星线 -->
            <line x1="16" y1="7" x2="16" y2="10.5" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <line x1="16" y1="21.5" x2="16" y2="25" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <line x1="7" y1="16" x2="10.5" y2="16" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <line x1="21.5" y1="16" x2="25" y2="16" stroke="#fff" stroke-width="1.2" stroke-linecap="round" opacity="0.6"/>
            <!-- 四角节点 (神经网络感) -->
            <circle cx="5" cy="5" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <circle cx="27" cy="5" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <circle cx="27" cy="27" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <circle cx="5" cy="27" r="1.2" fill="#FDE68A" opacity="0.7"/>
            <!-- 连接线 -->
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
        <span class="nav-icon">🔒</span>
        <span>锁定工作台</span>
      </button>
    </aside>

    <main class="workspace">
      <header class="topbar topbar-compact">
        <div class="gpu-pill" :title="runtimeTitle">
          <span :class="{ off: !runtimeOk }"></span>
          {{ runtimeLabel }}
        </div>
      </header>

      <RouterView v-slot="{ Component }">
        <keep-alive :max="6">
          <component :is="Component" />
        </keep-alive>
      </RouterView>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getRuntime } from '../api/system.js'
import AppIcon from '../components/AppIcon.vue'
import LoginPage from '../pages/LoginPage.vue'

const needLogin = ref(false)

// 前端弱密码门禁：localStorage 存解锁状态，不依赖后端
const UNLOCK_KEY = 'yolops_unlocked'

function checkAuth() {
  needLogin.value = localStorage.getItem(UNLOCK_KEY) !== 'true'
}

function onLoginSuccess() {
  localStorage.setItem(UNLOCK_KEY, 'true')
  needLogin.value = false
  loadRuntime()
}

function onAuthRequired() {
  needLogin.value = true
}

function doLock() {
  localStorage.removeItem(UNLOCK_KEY)
  needLogin.value = true
}

onMounted(() => {
  checkAuth()
  if (!needLogin.value) loadRuntime()
  window.addEventListener('auth-required', onAuthRequired)
})

onUnmounted(() => {
  window.removeEventListener('auth-required', onAuthRequired)
})

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

const runtime = ref(null)
const runtimeOk = ref(false)

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

async function loadRuntime() {
  try {
    runtime.value = await getRuntime()
    runtimeOk.value = true
  } catch {
    runtimeOk.value = false
  }
}
</script>
