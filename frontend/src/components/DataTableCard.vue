<!--
  DataTableCard.vue —— 数据表格卡片组件

  用途：以卡片样式展示结构化表格数据。支持两种数据模式：
  1. 传统模式：headers 为字符串数组，rows 为二维数组
  2. 对象模式：columns 定义列配置（含 label/key），rows 为对象数组
  3. 提供具名插槽 'cell-<列名>' 供外部自定义单元格渲染
  4. 可选 inline 属性使卡片表现为内联样式
-->
<template>
  <!-- 卡片容器：根据 inline 属性动态切换内联样式 -->
  <section :class="['card', 'table-card', { inline }]">
    <!-- 标题栏：仅在传入 title 时渲染，右侧固定显示"查看全部 →" -->
    <CardTitle v-if="title" :title="title" right="查看全部 →" />

    <!-- 数据表格 -->
    <table>
      <!-- 表头：遍历 resolvedHeaders 动态生成列标题 -->
      <thead>
        <tr>
          <th v-for="col in resolvedHeaders" :key="col">{{ col }}</th>
        </tr>
      </thead>
      <!-- 表体：遍历 rows 数组，每行根据 resolvedHeaders 渲染单元格 -->
      <tbody>
        <tr v-for="(row, index) in rows" :key="index">
          <td v-for="col in resolvedHeaders" :key="col">
            <!--
              具名插槽 'cell-<列名>'：允许外部自定义该列单元格的渲染内容
              向外暴露当前行数据 (row) 和解析后的单元格值 (value)
              若未提供插槽内容，则直接显示默认解析值
            -->
            <slot :name="'cell-' + col" :row="row" :value="resolveCell(row, col)">
              {{ resolveCell(row, col) }}
            </slot>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<script setup>
// 导入 Vue 的计算属性 API
import { computed } from 'vue'
// 导入卡片标题子组件
import CardTitle from './CardTitle.vue'

/**
 * 组件属性定义
 * @prop {string}  title   - 卡片标题（可选，为空时不渲染标题栏）
 * @prop {Array}   headers - 列标题字符串数组（传统模式必填）
 * @prop {Array|null} columns - 列配置对象数组（对象模式），每项含 label（显示名）和 key（数据字段名）
 * @prop {Array}   rows    - 表格数据行（必填），传统模式为二维数组，对象模式为对象数组
 * @prop {boolean} inline  - 是否以内联卡片样式显示
 */
const props = defineProps({
  // 卡片标题，为空字符串时不显示标题栏
  title: { type: String, default: '' },
  // 列标题数组，传统模式下作为表头并用于按索引取值
  headers: { type: Array, required: true },
  // 列配置数组（对象模式），为 null 时退化为传统模式；每项应包含 label 和 key
  columns: { type: Array, default: null },
  // 表格数据行，必填；类型随模式变化：传统模式为二维数组，对象模式为对象数组
  rows: { type: Array, required: true },
  // 是否以内联样式显示卡片，用于在网格布局中按需控制宽度
  inline: Boolean,
})

/**
 * 计算属性：解析最终的表头列表
 * - 若提供了 columns（对象模式），则提取每列的 label 作为表头
 * - 否则回退到原始的 headers 数组（传统模式）
 */
const resolvedHeaders = computed(() => {
  if (props.columns) return props.columns.map(c => c.label)
  return props.headers
})

/**
 * 解析指定行中某一列的单元格值
 * @param {Object|Array} row    - 当前行数据
 * @param {string}       header - 列标题
 * @returns {string} 解析后的单元格文本
 *
 * 传统模式（无 columns）：
 * - row 为数组时按索引取值
 * - row 为对象时直接通过 header 字符串作为键取值
 * 对象模式（有 columns）：
 * - 根据 header 找到对应的 column 配置，再通过 col.key 从 row 对象中取值
 */
function resolveCell(row, header) {
  if (!props.columns) {
    // 传统模式：rows 为 string[][], header 是字符串本身
    // 通过 headers 数组中的索引位置取 row 中对应列的值
    const idx = props.headers.indexOf(header)
    return Array.isArray(row) ? row[idx] : row[header]
  }
  // 对象模式：rows 为对象数组，columns 定义了 label 到 key 的映射
  // 先根据 header（即 column.label）找到对应的列配置，再通过 key 取值
  const col = props.columns.find(c => c.label === header)
  return col ? row[col.key] : ''
}
</script>

<!--
  样式说明：
  - .table-card：基础卡片样式，由全局 card 样式统一管理（圆角、阴影、内边距等）
  - .table-card.inline：内联变体，宽度由父容器控制，适用于网格卡片布局
  - 表格样式（table/thead/tbody/tr/th/td）：遵循设计系统中的表格规范
  - 标题栏通过 CardTitle 子组件呈现，无需在此重复定义
  - 组件本身不包含 scoped 样式，完全依赖于全局 CSS 变量和组件库样式
-->
