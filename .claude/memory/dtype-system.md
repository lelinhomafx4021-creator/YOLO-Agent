---
name: dtype-system
description: 数据集类型体系规范 — dtype 的取值、语义、自动检测规则
metadata: 
  node_type: memory
  type: project
  originSessionId: 5a7eb372-b469-475e-ae15-b49caf1c1774
---

## dtype 定义

| dtype | 含义 | 有标注 | 用途 |
|---|---|---|---|
| `train` | 训练集 | ✅ | 绑定到项目用于训练 |
| `val` | 验证集 | ✅ | 训练时验证、评估 |
| `test` | 测试/推理集 | 均可 | 有标注→评估精度，无标注→跑推理 |
| `annotation` | 标注中 | 部分 | 上传图片待标注，标完可拆分 |
| *(空)* | 未分类全量 | ✅ | 导入的全量数据集，拆分前状态 |

**关键规则：**
- 没有 `predict`，已合并到 `test`。[[dtype-no-predict]]
- `annotation` 数据集拆分时只导出 `reviewed` 图片
- 导入时自动检测：`images/train/`→train, `images/val/`→val, 无标注→test
- `image/` 单数目录名自动规范化为 `images/`

**Why:** 之前 predict 和 test 概念重叠，统一为 test 减少混淆。
**How to apply:** 所有新代码只用这 5 个 dtype。导入逻辑见 `app/dataset/importer.py:_detect_dtype_from_structure`。
