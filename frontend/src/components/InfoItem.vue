<!--
  组件名称：InfoItem（信息条目）
  用途：通用的标签-值展示项，用于在详情面板中以统一样式显示一对 label（标签名）和 value（值）。
  支持通过 wide 属性切换宽布局模式。
-->
<template>
  <!-- 信息条目容器，wide 为 true 时添加 .wide 样式类实现宽布局 -->
  <div :class="['info-item', { wide }]">
    <!-- 标签文本 -->
    <span>{{ label }}</span>
    <!-- 值文本，使用 strong 加粗突出显示 -->
    <strong>{{ value }}</strong>
  </div>
</template>

<script setup>
/**
 * label - 字段标签（必填），如"名称"、"状态"等
 * value - 字段值（必填），展示的具体内容
 * wide  - 是否启用宽布局模式（可选），默认 false
 */
defineProps({
  label: { type: String, required: true },
  value: { type: String, required: true },
  wide: Boolean,
})
</script>
