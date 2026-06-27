<template>
  <!-- 页面头部容器，用于展示页面标题、副标题和自定义操作区域 -->
  <div class="page-header">
    <!-- 标题区域：包含主标题和副标题 -->
    <div>
      <!-- 主标题：通过 title prop 传入，例如 "项目管理"、"用户列表" 等 -->
      <h1>{{ title }}</h1>
      <!-- 副标题：通过 subtitle prop 传入，对主标题的补充说明，可选 -->
      <p>{{ subtitle }}</p>
    </div>
    <!-- 操作区域：用于放置页面级别的操作按钮，如 "新建"、"刷新"、"导出" 等 -->
    <div class="header-actions">
      <!-- 插槽：支持父组件通过默认插槽自定义操作按钮或其他内容 -->
      <slot />
    </div>
  </div>
</template>

<script setup>
/**
 * 页面头部组件
 * 用于在每个页面上方展示页面标题、副标题以及右侧的操作按钮区域。
 * 通过 props 接收标题文本，通过默认插槽支持自定义操作内容。
 */

/**
 * title - 页面主标题（必填）
 *   类型：String，例如 "项目管理"、"模型训练" 等
 * subtitle - 页面副标题（可选）
 *   类型：String，默认值为空字符串，用于对主标题的补充说明
 */
defineProps({
  title: { type: String, required: true },    // 页面主标题，必须提供
  subtitle: { type: String, default: '' },    // 页面副标题，不传则显示为空
})
</script>

<style scoped>
/* 页面头部整体布局：flex 水平排列，标题与操作按钮分居两侧 */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 0;
}

/* 操作按钮区域：flex 布局，按钮之间保留 8px 间距 */
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
</style>
