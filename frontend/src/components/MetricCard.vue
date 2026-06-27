<!--
  组件名称: MetricCard（指标卡片）
  组件用途: 在仪表盘或统计概览页中展示单个关键绩效指标（KPI），
           例如请求总数、错误率、响应时间等。卡片包含标题、数值、
           可选图标，并支持危险告警（danger）和高亮强调（highlight）
           两种视觉状态，帮助用户快速识别指标的重要程度和异常情况。
  使用方式: <MetricCard title="请求总数" value="12,345" icon="📊" />
-->
<template>
  <!-- 指标卡片根元素：根据 danger / highlight 布尔属性动态切换 CSS 类名 -->
  <section :class="['metric-card', { danger, highlight }]">
    <!-- 文本区域：包含指标标题和数值 -->
    <div>
      <!-- 指标标题文本，例如 "请求总数"、"错误率" 等 -->
      <span>{{ title }}</span>
      <!-- 指标数值文本，例如 "12,345"、"3.2%" 等，使用 `<strong>` 加粗醒目显示 -->
      <strong>{{ value }}</strong>
    </div>
    <!-- 图标区域：v-if 条件渲染，仅当 icon 属性非空时显示对应的图标文字或 Emoji -->
    <i v-if="icon">{{ icon }}</i>
  </section>
</template>

<script setup>
/**
 * 组件属性（Props）定义
 * 所有属性通过父组件传入，驱动卡片的内容与样式表现。
 */

// title: 指标的名称标签，必填，类型为字符串
// 示例值: "请求总数"、"平均响应时间"、"错误率"
defineProps({
  title: { type: String, required: true },

  // value: 指标的数值，必填，类型为字符串
  // 示例值: "12,345"、"3.2%"、"200ms"
  value: { type: String, required: true },

  // icon: 指标对应的图标，可选，默认值为空字符串
  // 可填入 Emoji 字符（如 "📊"）或纯文本图标标识符
  icon: { type: String, default: '' },

  // danger: 是否为危险/告警状态，可选布尔值
  // 为 true 时卡片将应用 .danger 样式（通常为红色系），
  // 用于提示指标异常，例如错误率突增
  danger: Boolean,

  // highlight: 是否为高亮状态，可选布尔值
  // 为 true 时卡片将应用 .highlight 样式（通常增强边框或背景），
  // 用于突出展示重点关注的指标
  highlight: Boolean,
})
</script>

<!--
  组件样式说明：
  当前组件未使用 <style scoped>，样式定义委托给全局 CSS 或父组件作用域样式，
  以此保持组件的轻量并允许主题系统灵活覆盖。

  外部需定义的样式类（供参考）：
    .metric-card              - 卡片容器基础样式（边框、圆角、内边距、背景色）
    .metric-card.danger       - 危险状态（例如红色边框/背景）
    .metric-card.highlight    - 高亮状态（例如蓝色边框或阴影增强）
    .metric-card div           - 文本区域布局（flex 排列）
    .metric-card span          - 标题文字样式（字号、颜色）
    .metric-card strong        - 数值文字样式（大字号加粗）
    .metric-card i             - 图标样式（字号、边距）

  如需将样式内聚到组件内部，可在此处添加 <style scoped> 块。
-->
