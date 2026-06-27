<template>
  <div v-if="visible" class="dialog-overlay" @click.self="onCancel">
    <div class="dialog confirm-dialog">
      <h3>{{ title }}</h3>
      <p>{{ message }}</p>
      <div class="dialog-actions">
        <button class="secondary-action" @click="onCancel">取消</button>
        <button class="primary-action danger-action" @click="onConfirm">确认删除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  visible: Boolean,
  title: { type: String, default: '确认操作' },
  message: { type: String, default: '确定要执行此操作吗？' },
})
const emit = defineEmits(['confirm', 'cancel'])
function onConfirm() { emit('confirm') }
function onCancel() { emit('cancel') }
</script>

<style scoped>
.confirm-dialog { max-width: 400px; }
.confirm-dialog h3 { margin: 0 0 8px; font-size: 16px; }
.confirm-dialog p { color: var(--muted); margin: 0 0 16px; font-size: 14px; line-height: 1.5; }
</style>
