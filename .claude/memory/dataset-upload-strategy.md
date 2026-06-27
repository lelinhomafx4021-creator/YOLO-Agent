---
name: dataset-upload-strategy
description: 大数据集上传的批次策略和续传机制
metadata: 
  node_type: memory
  type: project
  originSessionId: 5a7eb372-b469-475e-ae15-b49caf1c1774
---

## 上传架构

- **每批 50 张**（`frontend/src/api/datasets.js`）
- 第一批创建版本 → `/datasets/{id}/annotation/upload-folder`
- 后续批次追加 → `/dataset-versions/{id}/append-images`
- **每批独立 try/catch**，单批失败不中断后续批次
- 进度回调返回 `{done, total, added, errors}`

## append-images 端点
- `backend/app/api/datasets.py:append_images_to_version`
- 自动检测 split 子目录结构（`images/unlabeled/` vs `images/`）
- 目录不存在时自动创建
- 单文件异常不影响同批其他文件，返回错误列表

## 续传
- 数据集列表页"续传"按钮，仅 `dtype=annotation` 显示
- 调用 `appendImagesToVersion()`

## 文件夹规范化
- `importer.py:_normalize_yolo_folders()` → `image/`→`images/`, `annot/`→`labels/`
- 导入时自动执行（copytree 之后）

**Why:** 之前 1700 张图只上传了 20 张，因为 append 端点不支持动态目录+无错误恢复。
**How to apply:** 新上传功能复用 `uploadAnnotationFolder` 和 `appendImagesToVersion`，不要重写。
