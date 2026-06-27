---
name: inference-onnx
description: 推理模块设计 — 权重选择、ONNX回退、预测图兜底、UI隔离
metadata: 
  node_type: memory
  type: project
  originSessionId: 5a7eb372-b469-475e-ae15-b49caf1c1774
---

## 权重选择
`_find_weight()` 优先 `.pt`（兼容性），ONNX 作为备选。加载失败自动回退到 `best.pt`。[[dtype-system]]

## 预测图
- `save=True, project=image_dir.resolve()` 用绝对路径确保输出到正确位置
- 无检测目标时复制原图作为兜底图，避免前端显示 "?"

## UI
- 图片推理：卡片网格 `infer-grid`
- 测试集推理：大图网格 `dataset-grid` + 底部统计（总数/总目标数/耗时）
- 两模式独立状态（`batchResult` vs `datasetResult`），切换不相互覆盖

**Why:** 之前 ONNX 加载报错导致推理失败，预测图存到错误目录导致问号。[[user-preferences]]
**How to apply:** 新推理相关功能参考 `app/api/inference.py:_run_single_prediction` 和 `_find_weight`。
