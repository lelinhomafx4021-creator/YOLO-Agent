<template>
  <div class="plan-card">
    <div class="plan-head">
      <span :class="['plan-chip', plan.plan_type || 'general']">{{ typeLabel }}</span>
      <strong>{{ plan.title || '未命名计划' }}</strong>
    </div>
    <ul v-if="items.length" class="plan-items">
      <li v-for="(item, i) in items" :key="i">{{ item.text || item }}</li>
    </ul>
    <p v-if="plan.reason" class="plan-reason">{{ plan.reason }}</p>
    <div class="plan-actions" v-if="showActions">
      <button class="secondary-action small-action" @click="$emit('save', plan)">保存</button>
      <button class="primary-action small-action" @click="$emit('apply', plan)">应用</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  plan: { type: Object, required: true },
  showActions: { type: Boolean, default: true },
})

defineEmits(['save', 'apply'])

const typeLabel = computed(() => {
  const map = { training: '训练', annotation: '标注', data: '数据', param: '参数', general: '通用' }
  return map[props.plan.plan_type] || '计划'
})

const items = computed(() => {
  if (Array.isArray(props.plan.items)) return props.plan.items
  return []
})
</script>
