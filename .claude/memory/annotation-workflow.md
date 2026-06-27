---
name: annotation-workflow
description: 标注工作流 — 上传→标注→拆分→训练 的完整生命周期
metadata: 
  node_type: memory
  type: project
  originSessionId: 5a7eb372-b469-475e-ae15-b49caf1c1774
---

## 完整流程

```
上传图片 → dtype=annotation → 逐张标注 → 已复核图片显示框
→ 全部标完后拆分 → 生成 train/val/test 三个独立数据集 → 绑定到项目训练
```

## 标注进度
- `GET /dataset-versions/{id}/annotation-progress` 返回 `{total, reviewed, unlabeled, ai_prelabel, next_unlabeled_image_id}`
- 标注工作台左侧显示分段进度条（绿=已复核，橙=AI预标，灰=未标注）
- "跳转到下一张未标注"按钮

## 拆分规则
- `dtype=annotation` → 只导出 `reviewed` 图片（`backend/app/api/datasets.py:split_into_independent`）
- 拆分按钮显示条件：`isAnnotation AND reviewed_count>0` 或 `!isAnnotation AND hasLabels`
- 拆分对话框提示"标注中数据集，仅导出已复核的 N 张"

## 预览
- `DatasetPreviewPage.vue` — Canvas 叠加渲染 YOLO 标注框
- 已标注图片显示彩色框+类别标签，未标注显示原图
- 窗口缩放自动重绘

## 标注工作台
- "隐藏框/显示框"切换按钮 — 方便查看原图找遗漏目标
- 缩略图右下角色点：绿=reviewed, 橙=ai_prelabel, 灰=unlabeled

**Why:** 用户需要清晰的标注→拆分→训练流程，不标注完不能拆分，拆分只取已复核图片。
**How to apply:** 标注功能改动时保持 `annotation_status` 状态机（unlabeled→ai_prelabel→reviewed）。
