<!--
  组件名称: ActionItem (快捷操作项)
  组件用途: 渲染单个快捷操作项，用于展示操作名称或功能入口。
           该组件通常作为列表项使用，接收外部传入的文本内容并显示为带图标的条目。
           组件本身仅负责展示，不包含交互逻辑，交互行为由父组件通过事件或路由处理。
-->
<template>
  <!-- 操作项外层容器：作为网格或列表中的一个条目 -->
  <div class="action-item">
    <!-- 装饰性图标：星号标记，用于视觉上区分操作项 -->
    <span>✦</span>
    <!-- 操作文本内容，通过 props text 传入，由父组件决定显示什么文字 -->
    <p>{{ text }}</p>
  </div>
</template>

<script setup>
/**
 * 组件属性定义
 * @prop {String} text - 操作项的显示文本，必填。由父组件传入，用于标注当前操作项的名称。
 */
defineProps({
  text: { type: String, required: true },
})

/**
 * 组件事件 (emits): 本组件为纯展示型组件，无向外派发的事件。
 * 若需要交互反馈，请在父组件中监听点击等事件或包裹可交互元素。
 */

/**
 * 响应式变量: 本组件无内部响应式状态，所有数据均通过 props 从父组件传入。
 */

/**
 * 计算属性: 本组件无计算属性。
 */

/**
 * 方法: 本组件无内部方法。
 */
</script>

<style scoped>
/* 操作项容器样式：以弹性布局居中展示图标和文本 */
.action-item {
  padding: 8px 10px;
  border: 1px solid var(--line-soft, #dbe5ee);
  border-radius: 7px;
  display: flex;             /* 弹性布局，使图标与文本水平排列 */
  align-items: center;       /* 垂直居中 */
  gap: 8px;
  cursor: pointer;           /* 手型光标，提示可点击 */
  background-color: var(--card-soft, #eef4f8);
  transition: background-color 0.2s ease; /* 悬停背景色过渡动画 */
}

/* 操作项悬停效果：加深背景色以提供视觉反馈 */
.action-item:hover {
  background-color: #f4f9fd;
}

/* 图标样式：颜色区别于文本，起到装饰强调作用 */
.action-item span {
  color: var(--primary, #1f6fa5);
  font-size: 13px;
}

/* 文本样式：常规字号与颜色，确保可读性 */
.action-item p {
  margin: 0;            /* 清除段落默认外边距 */
  font-size: 12px;
  color: var(--text, #223548);
  line-height: 1.5;
}
</style>
