---
name: user-preferences
description: 用户的编码偏好和反馈 — 如何与这个项目协作
metadata: 
  node_type: memory
  type: user
  originSessionId: 5a7eb372-b469-475e-ae15-b49caf1c1774
---

## 用户角色
AI 目标检测 MLOps 平台开发者，技术能力强，关注实际可用性而非花哨 UI。

## 偏好
- **所有 UI 文本用中文** — 按钮、标签、占位符、提示信息
- **不使用 UI 组件库** — 全部手写 CSS，设计 token 在 `frontend/src/style.css`
- **先思考再改代码** — 不要看到一个点就改，先理清整体逻辑
- **一次性改完相关的所有文件** — 不要留尾巴让下次修
- **功能正确性优先于 UI 美观** — 但也不能太丑
- **不喜欢冗余状态** — 比如 candidate 状态被取消了，只保留 production/archived

## 反馈记录
- predict 和 test 应该是一个东西 → 合并为 test [[dtype-system]]
- 1700 张图只上传 20 张不可接受 → 修复了批量上传 [[dataset-upload-strategy]]
- 标注工作台需要能看到原图 → 加了隐藏框切换按钮 [[annotation-workflow]]
- 数据集预览需要显示标注框 → Canvas 叠加渲染 [[annotation-workflow]]
- 训练日志要实时显示 → SSE 流式推送

**How to apply:** 每次对话开始前检查 CLAUDE.md + MEMORY.md，理解项目现状和用户风格后再动手。
