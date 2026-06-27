<template>
  <div :class="['chat-bubble', role]">
    <div class="bubble-avatar">
      <span class="avatar-text">{{ role === 'user' ? '我' : 'AI' }}</span>
    </div>
    <div class="bubble-body">
      <div class="bubble-text" v-html="rendered"></div>
      <div class="bubble-actions" v-if="role === 'assistant'">
        <button class="bubble-btn" :class="{ done: copySuccess }" @click="copyContent" :title="copySuccess ? '已复制' : '复制'">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button>
      </div>
      <div v-if="plan" class="bubble-plan">
        <PlanCard :plan="plan" @save="$emit('save-plan', plan)" />
      </div>
      <div class="bubble-time" v-if="time">{{ formatTime(time) }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import PlanCard from './PlanCard.vue'

const props = defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
  time: { type: String, default: '' },
  plan: { type: Object, default: null },
})

defineEmits(['save-plan'])

const copySuccess = ref(false)

const rendered = computed(() => {
  let text = (props.content || '')

  // 先转义 HTML，保护安全
  text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  // ── 块级元素（先处理，避免被行内规则干扰）──

  // ```代码块``` — 多行
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="${lang}">${code.trim()}</code></pre>`
  })

  // 表格 — 先标出行，再组表
  text = text.replace(/^(\|.+\|)\n(\|[-:| ]+\|)\n((?:\|.+\|\n?)+)/gm, (_, header, sep, rows) => {
    const hCells = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`).join('')
    const rHtml = rows.trim().split('\n').map(row => {
      const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`).join('')
      return `<tr>${cells}</tr>`
    }).join('')
    return `<div class="md-table-wrap"><table>${hCells}${rHtml}</table></div>`
  })

  // --- 分割线
  text = text.replace(/^---$/gm, '<hr>')

  // # ## ### 标题
  text = text.replace(/^### (.+)$/gm, '<h4>$1</h4>')
  text = text.replace(/^## (.+)$/gm, '<h3>$1</h3>')
  text = text.replace(/^# (.+)$/gm, '<h2>$1</h2>')

  // - 无序列表
  text = text.replace(/^- (.+)$/gm, '<li>$1</li>')
  text = text.replace(/(<li>.*?<\/li>\n?)+/gs, '<ul>$&</ul>')

  // 1. 有序列表
  text = text.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>')

  // ── 行内元素 ──

  // **粗体**
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  // *斜体*
  text = text.replace(/\*(.+?)\*/g, '<em>$1</em>')
  // `行内代码`
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  // 链接
  text = text.replace(/(https?:\/\/\S+)/g, '<a href="$1" target="_blank">$1</a>')

  // ── 段落与换行 ──

  // 双换行 → 段落分割
  text = text.replace(/\n{2,}/g, '</p><p>')
  // 单换行 → <br>
  text = text.replace(/\n/g, '<br>')

  return '<div class="md-content">' + text + '</div>'
})

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.content)
    copySuccess.value = true
    setTimeout(() => copySuccess.value = false, 1500)
  } catch { /* ignore */ }
}

function formatTime(t) {
  return t ? String(t).replace('T',' ').replace('Z','').slice(0,16) : ''
}
</script>
