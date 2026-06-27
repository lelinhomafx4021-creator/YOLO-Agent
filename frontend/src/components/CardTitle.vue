<!--
  组件名称: CardTitle
  组件用途: 卡片标题栏组件，用于在卡片容器中展示标题和可选的右侧辅助文字。
           左侧以加粗文字显示主标题，右侧以普通文字显示附加信息（如数量、状态等）。
  使用示例:
    <CardTitle title="检测结果" right="共 3 项" />
  说明:
    - 本组件为纯展示型组件，无内部状态、无事件派发（emits）。
    - 不含 <style> 样式块，样式由父组件或全局样式表统一定义。
-->

<template>
  <!-- 卡片标题外层容器：flex 行布局，左右排列标题与辅助文字 -->
  <div class="card-title">
    <!-- 主标题：使用 <strong> 标签加粗显示，始终渲染 -->
    <strong>{{ title }}</strong>
    <!-- 右侧辅助文字：条件渲染，仅当 right 属性有值时（非空字符串）才显示 -->
    <span v-if="right">{{ right }}</span>
  </div>
</template>

<script setup>
/**
 * 组件属性（props）
 * @prop {String}  title  - 主标题文字（必填）。组件核心内容，始终显示。
 * @prop {String}  right  - 右侧辅助文字（可选，默认值为空字符串 ''）。
 *                          常用于显示数量、状态、分类等附加信息。
 *                          当未传入或传入空字符串时，对应的 <span> 不会渲染。
 */
defineProps({
  title: { type: String, required: true },
  right: { type: String, default: '' },
})

/**
 * 本组件使用 <script setup> 语法，无需导出选项。
 * 当前无以下内容（若后续扩展需添加对应注释）：
 *   - 响应式变量（ref / reactive）
 *   - 计算属性（computed）
 *   - 方法（function）
 *   - 事件派发（emits）
 */
</script>
