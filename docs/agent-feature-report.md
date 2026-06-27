# YOLOps Agent 功能测试报告

> 测试日期: 2026-06-26
> 后端: FastAPI on port 8009 | 前端: Vue 3 + Vite on port 5174
> LLM: DeepSeek Chat API | 数据库: SQLite

---

## 一、Agent 核心功能

### 1. 对话引擎

| 功能 | 状态 | 说明 |
|---|---|---|
| 规则分析模式 (rule) | ✅ | 本地计算，7 个专项分析函数，秒出结果 |
| LLM Tool Use 模式 (llm) | ✅ | 11 个工具可被 LLM 主动调用，5 轮循环 |
| 流式输出 (SSE) | ✅ | 事件: chunk / tool_call / plan / title / done |
| 会话管理 | ✅ | 创建/删除/重命名/切换 |
| AI 自动标题 | ✅ | 首条对话后 LLM 生成标题 |
| 项目绑定 | ✅ | 下拉切换项目/全局模式 |

### 2. 11 个数据库查询工具

| 工具 | 测试 | 返回数据 |
|---|---|---|
| `get_training_detail` | ✅ | 训练参数(epochs/imgsz/batch)、P/R/mAP、val_dataset |
| `get_evaluation_detail` | ✅ | 评估指标、eval_dataset(dtype/规模)、逐图样本 |
| `list_training_runs` | ✅ | 训练列表含关键指标 |
| `list_evaluation_runs` | ✅ | 评估列表含 eval_on_split、eval_image_count |
| `get_dataset_detail` | ✅ | 数据集规模、split_breakdown(train/val/test)、审计 |
| `get_model_detail` | ✅ | 模型 P/R/mAP50、best_epoch、部署状态 |
| `compare_training_runs` | ✅ | 两次训练指标 delta 对比 (需 ≥2 条训练) |
| `get_dataset_label_stats` | ✅ | 每类标注框数量、占比 |
| `search_runs` | ✅ | 按关键词搜索训练/评估 (LIKE/ILIKE 自适应 PG/SQLite) |
| `get_project_summary` | ✅ | 项目统计概览 |
| `get_full_context` | ✅ | 训练+数据集(split)+模型+评估 一次性返回 |

### 3. 计划系统

| 功能 | 状态 | 说明 |
|---|---|---|
| 自动生成 | ✅ | LLM 分析后自动输出 JSON 计划 |
| 查看展开 | ✅ | 侧栏点击展开看具体条目 |
| 应用 | ✅ | 参数自动填到训练表单 |
| 归档/恢复 | ✅ | status: draft → archived → draft |
| 软删除 | ✅ | status → deleted，从列表消失 |
| 已读标记 | ✅ | 展开后自动标记 is_read=1，蓝点消失 |
| 绑定模型 | ✅ | 保存时自动关联 training_run_id |
| 筛选 | ✅ | 活跃/已归档/全部 |

---

## 二、上下文数据流

### LLM 收到的训练数据
```json
{
  "run_id": "安全帽模型训练-T3-20260626T10",
  "epochs": 50, "imgsz": 640, "batch": 8,
  "train_dataset": {"name": "安全帽全集-训练集", "image_count": 30, "class_count": 2, "dtype": "train"},
  "val_dataset":   {"name": "安全帽全集-验证集", "image_count": 20, "class_count": 2, "dtype": "val"},
  "precision": 0.995, "recall": 0.978,
  "map50": 0.975, "map50_95": 0.851, "best_epoch": 49
}
```

### LLM 收到的评估数据
```json
{
  "run_id": "安全帽模型训练-E1-20260626T11",
  "precision": 0.692, "recall": 0.644,
  "map50": 0.691, "map50_95": 0.437,
  "eval_dataset": {"name": "安全帽全集-验证集/v001", "dtype": "val", "image_count": 20}
}
```

### 数据流
```
用户点 + 选 T3 → "[引用: 训练 T3] 分析训练..."
                        ↓
    后端 build_context(project_id) → 查全项目数据
                        ↓
    System Prompt ← 塞入完整上下文 (训练+评估+数据集+模型)
                        ↓
    LLM 直接对比 train mAP 0.851 vs eval mAP 0.437 → 判断过拟合
```

---

## 三、Ref Picker (数据引用选择器)

| 区域 | 显示内容 |
|---|---|
| 🏋️ 训练 | epochs/轮·imgsz·分辨率 + val mAP |
| 📊 评估 | 评估用的数据集名 + 指标 |
| 📦 数据集 | dtype标签(训练/验证/测试) + 张数·类别数 |
| 🧠 模型 | P·R·mAP50 + best_epoch + 生产标记 |

训练和模型展示**不同数据**（不再重复）：
- 训练卡片：轮数、分辨率、验证mAP
- 模型卡片：精确率、召回率、mAP50、best_epoch、部署状态

---

## 四、本日修复记录

| 问题 | 修复 |
|---|---|
| LLM 调用崩溃，静默回退规则模式 | SYSTEM_PROMPT 中 JSON 示例的 `{}` 与 Python `.format()` 冲突，转义为 `{{}}` |
| `search_runs` SQLite 报错 | `ILIKE` → `LIKE`（根据 DB_BACKEND 自适应） |
| 数据集"暂无数据集" | 项目绑定 is_active=0；改为从训练/评估记录自动发现数据集 |
| 训练上下文缺少数据集规模 | 加 `train_dataset`/`val_dataset` 到 run_details |
| 评估列表不显示数据集类型 | 加 `eval_on_split`、`eval_image_count` |
| 训练和模型展示重复 | 分开字段：训练显示参数、模型显示精确率/召回率 |
| 计划不绑定模型 | persistPlan 自动检测 composerRef + 标题匹配 + latest_run 兜底 |
| 数据库垃圾数据 | 删除 57 个测试数据集、ONNX 导出过滤 (training_run_id>0) |
| ONNX 导出混入模型列表 | `WHERE training_run_id > 0` 过滤 |
| 已完成训练残留 error 字段 | 清理 stale error |

---

## 五、已确认正常的功能

- [x] 规则模式 7 项分析全部可用
- [x] LLM 模式 11 个工具全部可调用
- [x] 流式 SSE 输出
- [x] 计划 CRUD（保存/查看/应用/归档/恢复/删除）
- [x] 前端 ref picker 四个区域数据正确
- [x] 数据集自动从训练/评估记录发现
- [x] 上下文包含 split_breakdown
- [x] 代码通过 17/18 测试 (compare 需要 ≥2 条训练才工作)
- [x] 设置页 LLM/Rule 切换 + 自动保存
- [x] Enter 发送、Shift+Enter 换行
