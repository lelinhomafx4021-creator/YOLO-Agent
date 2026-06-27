---
name: frontend-ux-patterns
description: 前端 UX 约定 — keep-alive、弱密码、日志主题、导出进度、备注同步、训练表、数据集卡片
metadata: 
  node_type: memory
  type: project
  originSessionId: 5a7eb372-b469-475e-ae15-b49caf1c1774
---

## keep-alive 页面缓存
`AppShell.vue` 中 `<keep-alive :max="6">` 包裹 `<RouterView>`。页面切换不销毁。
需自动刷新的页面加 `onActivated(load)`：ProjectDetailPage、DatasetsPage。

## 弱密码门禁
前端 localStorage `yolops_unlocked`，密码 `yolops`（`LoginPage.vue:GATE_PASSWORD`）。
后端 auth 关闭（`.env` 注释 `ACCESS_PASSWORD`），API 无认证。
侧栏底部"锁定工作台"按钮清除标记。

## 日志终端
浅色主题：白卡 `var(--card)` + 暖色边框。状态药丸浅底深字。
训练中显示 epoch 进度条（`epochs_completed/epochs_total`）。

## 导出进度
模型导出对话框单按钮 + 脉冲进度条（0→90%假进度，完成→100%）。完成后自动 `load()` 刷新列表。

## 备注同步
训练备注 ↔ 模型备注双向同步（`PUT` 时相互更新）。三处统一显示：训练表、训练详情、模型仓库。
备注以模型为数据源（`model_notes`），保存写模型端点再自动同步训练。

## 基础模型名清理
`cleanModel()` — 长路径提取最后的文件名：`D:\...\weights\best.pt` → `best.pt`。[[user-preferences]]

## 训练任务表 (2026-06-27 重构)

**标准列**: 任务名称 | 关联数据集 | 模型架构 | 状态 | 进度(Epoch) | 最佳mAP | 剩余时间 | 操作

**关键函数**:
- `modelArch(path)` — 从 base_model 提取架构名。查表映射 YOLOv5/v8/v11 系列 + 兜底取 stem 首字母大写。显示为 `.model-arch-tag`（primary-soft 底 + primary 字色）
- `epochProgressPct(run)` / `epochProgressText(run)` — 进度百分比 + "136/200" 文字。运行中进度条有 `.progress-bar--running` 渐变动画
- `bestMapDisplay(run)` — 从 `modelForRun()` 取 mAP50，等宽字体 `.map-value`
- `remainingTime(run)` — 线性估算：`elapsed / completed × remaining`。已完成/失败显示 `-`，排队中显示 `-`
- `statusLabel()` — created→排队中(warning)、running→运行中(info)、completed→已完成(success)、failed→失败(danger)

**两处使用**:
- `TrainingRunsPage.vue` — 全局训练列表，8 列完整版
- `ProjectDetailPage.vue` — 项目内训练表，`.training-table--compact` 紧凑版（8 列缩窄间距），另有 `archLabel()` + `statusChipClass()` 副本

**CSS**: `.training-table` / `.training-table--compact` / `.task-name-link` / `.model-arch-tag` / `.epoch-progress-cell` / `.map-value` / `.action-btn-group` / `@keyframes progress-pulse`

## 数据集卡片 (2026-06-27 重构)

**DatasetsPage.vue** 从平铺表格改为自适应卡片网格 `.dataset-card-grid`（`repeat(auto-fill, minmax(300px, 1fr))`）。

**卡片结构**:
```
.dsc-head: 名称(.dsc-name) + 版本(.version-chip) | dtype药丸下拉(.dtype-pill)
.dsc-stats: 4 列统计数字（标注中→已标注+进度%，其他→含框图像+标签总数）
.dsc-progress: 标注进度条（仅 annotation dtype）
.dsc-actions: 操作按钮行（预览/续传/拆分/data.yaml/改名/删除）
```

**dtype 药丸**: `.dtype-pill` — 紧凑 `<select>`，圆角 99px，card-soft 底，自定义下拉箭头 SVG。`max-width: 110px`。

**统计适配**: `isAnnotation(item)` 条件渲染不同统计项。标注中显示 `highlight` 色已标注数 + 进度百分比。

**Why:** 表格信息密度低、dtype 切换不直观、不同类型数据集关注的指标不同。卡片化让每个数据集的信息层次更清晰。
**How to apply:** 新数据集相关 UI 参照卡片结构。操作按钮按 dtype 条件显示（续传仅 annotation，拆分仅可拆分数据集）。
