<!--
  ChipBadge.vue - 芯片/标签徽章组件

  用途：
    渲染一个带有主题色（tone）样式的行内标签或徽章，常用于在列表中
    标记状态（如进行中/已完成）、类别（如前端/后端）或标签信息。
    该组件是一个极简的纯展示型组件，不包含任何交互逻辑，通过 CSS class
    实现不同色调的视觉区分。

  使用示例：
    <ChipBadge tone="primary">进行中</ChipBadge>
    <ChipBadge tone="success">已通过</ChipBadge>
    <ChipBadge tone="warning">待审核</ChipBadge>
    <ChipBadge tone="danger">已失败</ChipBadge>

  插槽说明：
    默认插槽（<slot />）接收标签内显示的文本或图标内容。
-->

<template>
  <!-- 芯片标签根容器 -->
  <!-- .chip：基础芯片样式（圆角背景、内边距、字体大小等，由全局 CSS 提供） -->
  <!-- tone 动态 class：控制颜色主题，如 primary / success / warning / danger / info -->
  <!-- <slot />：Vue 默认插槽，由父组件传入标签文本或图标 -->
  <span :class="['chip', tone]"><slot /></span>
</template>

<script setup>
/**
 * 组件属性（props）定义
 *
 * 本组件为纯展示型组件，仅接受一个属性，不定义 emits 事件。
 * 所有视觉样式由外部 CSS 通过 class 组合控制，组件本身不包含样式文件。
 *
 * @prop {String} tone - 颜色主题名称
 *   传入的字符串值会作为 CSS class 动态绑定到根元素上。
 *   父组件或全局样式表中应定义对应的 .chip.{tone} 选择器来设置颜色。
 *   常用值: 'primary' | 'success' | 'warning' | 'danger' | 'info'
 *   默认值: ''（空字符串），表示不追加额外主题 class，使用 .chip 基础样式。
 */
defineProps({
  tone: {
    type: String,   // tone 必须为字符串类型
    default: '',    // 默认为空字符串，此时仅显示 .chip 基础样式，无主题色
  },
})
</script>

<!--
  样式说明

  本组件有意不包含 <style> 块（无论是 scoped 还是全局），原因如下：
    1. 保持主题色样式可被全局灵活复写或替换，不受组件作用域限制。
    2. 让消费方可以根据项目设计系统自定义 .chip 和 .chip.{tone} 的样式。

  建议在项目的全局样式表（如 main.css / global.css）中定义以下样式：

    /* 芯片基础样式 */
    .chip {
      display: inline-flex;
      align-items: center;
      padding: 2px 10px;
      border-radius: 4px;
      font-size: 12px;
      line-height: 22px;
      white-space: nowrap;
    }

    /* 各色调变体 */
    .chip.primary   { background-color: #e6f7ff; color: #1890ff; border: 1px solid #91d5ff; }
    .chip.success   { background-color: #f6ffed; color: #52c41a; border: 1px solid #b7eb8f; }
    .chip.warning   { background-color: #fffbe6; color: #faad14; border: 1px solid #ffe58f; }
    .chip.danger    { background-color: #fff2f0; color: #ff4d4f; border: 1px solid #ffa39e; }
    .chip.info      { background-color: #f0f5ff; color: #2f54eb; border: 1px solid #adc6ff; }
-->
