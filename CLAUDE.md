# CLAUDE.md

YOLOps-Agent — 工业 YOLO 目标检测 MLOps 平台。唯一架构文档，每次对话自动加载。

## 记忆系统

```
YOLOps-Agent/
├── CLAUDE.md              ← 架构合同（本文件，每次自动加载）
├── .claude/
│   ├── MEMORY.md          ← 记忆索引（每次自动加载）
│   └── memory/            ← 6 个记忆文件（按需加载）
│       ├── user-preferences.md      # 中文UI、无组件库
│       ├── dtype-system.md          # 5种dtype
│       ├── dataset-upload-strategy.md # 批次50、续传
│       ├── annotation-workflow.md   # 标注→拆分→训练
│       ├── inference-onnx.md        # ONNX回退、推理删除
│       └── frontend-ux-patterns.md  # keep-alive、导出轮询
```

## 架构

```
Vue 3 + Vite (5174) ──HTTP──> FastAPI (8009)
                                ├── PostgreSQL 127.0.0.1:55432 (默认) / SQLite (回退)
                                ├── 本地文件系统 (图片、标注、模型、日志)
                                └── Ultralytics YOLO (训练 + 预标注)
```

## 命令

```powershell
# 前端
cd D:\workspace\YOLOps-Agent\frontend
npm run dev                # http://127.0.0.1:5174
npm run build              # 构建检查

# 后端
cd D:\workspace\YOLOps-Agent\backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8009  # http://127.0.0.1:8009/docs
.\.venv\Scripts\python.exe -c "from app.main import app; print('OK')"  # 导入链验证
```

## 存储布局 (`backend/data/`)

```
datasets/{name}/{version}/  # images/ + labels/ + data.yaml
runs/                       # YOLO 训练输出
model_registry/             # best.pt, last.pt, results.csv, charts
exports/                    # 导出的 YOLO 数据集
uploads/                    # 上传临时目录
yolops.db                   # SQLite (回退模式)
settings.json               # 持久化设置
```

大文件不入库，只存路径和指标。

---

## dtype 类型体系 (核心业务规则)

| dtype | 含义 | 有标注 | 训练 | 验证/评估 |
|---|---|---|---|---|
| `train` | 训练集 | ✅ | ✅ | ✅ |
| `val` | 验证集 | ✅ | ❌ | ✅ |
| `test` | 测试/推理集 | 均可 | ❌ | ✅ |
| `annotation` | 标注中 | 部分 | ❌ | ❌ |
| *(空)* | 未分类全量 | ✅ | ✅ | ✅ |

- 导入自动检测：`images/train/`→train, `images/val/`→val, 无标注→test
- `annotation` 拆分时只导出 `reviewed` 图片
- `image/` 单数目录名自动规范化为 `images/`

## 数据集工作流

```
上传图片 → dtype=annotation → 标注工作台逐张标注
→ 已标注的预览显示框，未标注显示原图
→ 全部标完 → 拆分 → train/val/test 三个独立数据集 → 项目绑定 → 训练
```

- 标注进度: `GET /dataset-versions/{id}/annotation-progress`
- 批量上传: 每批 50 张，独立 try/catch，支持续传
- `refresh_dataset_version_metadata` 从 `image_items` 表计数（不是文件系统）

---

## 后端模块地图

| 模块 | 职责 |
|---|---|
| `app/core/config.py` | 路径、图片扩展名、DB 后端选择 |
| `app/core/database.py` | SQLModel DDL、`db()`/`fetch_one()`/`fetch_all()`、轻量 migration |
| `app/models.py` | 18 个 SQLModel ORM 类 |
| `app/dataset/importer.py` | 数据集创建、YOLO 导入（copy→normalize→audit→fingerprint→DB）、dtype 自动检测 |
| `app/dataset/statistics.py` | data.yaml 解析、文件指纹 |
| `app/dataset/version_metadata.py` | 版本元数据刷新（image_count/label_file_count/class 统计） |
| `app/dataset/yolo_txt_validator.py` | YOLO txt 审计 |
| `app/annotation/yolo_txt_io.py` | YOLO txt 读写 |
| `app/annotation/prelabel_service.py` | Ultralytics 预标注 |
| `app/annotation/revision_service.py` | 标注修订快照/历史/恢复 |
| `app/training/trainer.py` | 后台线程训练 (created→running→completed/failed) |
| `app/training/evaluator.py` | 后台线程评估 |
| `app/training/artifact_collector.py` | 训练产物收集、metrics 解析 |
| `app/registry/model_registry.py` | 模型注册、生产/归档 |
| `app/agents/training_analyst_agent.py` | 训练分析报告（训练完成自动生成） |
| `app/agents/evaluation_analyst_agent.py` | 评估分析报告（评估完成自动生成） |
| `app/agents/chat_agent.py` | Agent 对话 (LLM ToolUse / rule 分析 / 流式输出) |
| `app/agents/tools.py` | Agent 工具定义与执行（11 个数据库查询工具，含 split_breakdown） |
| `app/agents/context_builder.py` | 上下文 JSON 构建 + build_index 轻量索引；从训练/评估自动发现数据集 |
| `app/dataset/ai_quality.py` | AI 数据质量：模糊/曝光检测、重复检测、标注一致性 |
| `app/api/datasets.py` | 数据集 CRUD、版本、导入、追加、拆分、dtype、进度、审计、AI 质量 |
| `app/api/annotations.py` | 标注读写、预标注、修订历史 |
| `app/api/training.py` | 训练 CRUD、SSE 日志流、进度 |
| `app/api/models.py` | 模型列表、产物、导出、推广 |
| `app/api/projects.py` | 项目 CRUD、数据集绑定、项目内训练/评估 |
| `app/api/agents.py` | Agent 会话、聊天、计划 |
| `app/api/settings.py` | 设置读写 |
| `app/api/system.py` | GPU 信息、运行时状态 |
| `app/main.py` | FastAPI 入口、CORS、路由注册、静态挂载、auth 中间件 |

---

## 前端结构

```
src/
├── api/client.js          # fetch 封装 (get/post/put/del/postForm/authFetch)
├── api/datasets.js        # 数据集 API（含批量上传、续传、进度、拆分）
├── api/annotations.js     # 标注 API
├── api/training.js        # 训练 API
├── api/models.js          # 模型 API
├── api/projects.js        # 项目 API
├── api/agents.js          # Agent API
├── api/inference.js       # 推理 API
├── api/settings.js        # 设置 API
├── components/            # 14 个组件（AnnotationCanvas、ChatBubble、PlanCard…）
├── composables/           # useAnnotationKeyboard.js
├── layouts/AppShell.vue   # 侧栏 + 顶栏布局
├── pages/                 # 13 个页面（懒加载）
│   ├── OverviewPage.vue          # 全局概览
│   ├── DatasetsPage.vue          # 数据管理（卡片网格/导入/续传/拆分/dtype）
│   ├── DatasetPreviewPage.vue    # 数据集预览（Canvas 渲染标注框）
│   ├── AnnotationStudioPage.vue  # 标注工作台（进度/隐藏框/下一张未标注）
│   ├── LabelAuditPage.vue        # 标注审计
│   ├── TrainingRunsPage.vue      # 训练列表
│   ├── TrainingRunDetailPage.vue # 训练详情（指标/日志/产物/AI报告）
│   ├── ModelRegistryPage.vue     # 模型仓库
│   ├── ProjectsPage.vue          # 项目列表
│   ├── ProjectDetailPage.vue     # 项目详情（训练/评估/模型）
│   ├── EvaluationDetailPage.vue  # 评估详情
│   ├── AgentChatPage.vue         # Agent 对话
│   └── SettingsPage.vue          # 系统设置
├── router/index.js        # Vue Router，懒加载
└── style.css              # 全部 CSS，无 UI 库
```

---

## 前端设计约束 (不可妥协)

- **无 UI 组件库** — CSS 全手写在 `style.css`
- **设计 token (2026-06-27 重构)**: primary `#3C3D40`（净灰）, bg `#FAFBFC`（亮白）, card `#FFFFFF` + 毛玻璃, line `#E4E6EA`, radius ~10px — 纯白亮色，全浅色按钮/气泡/logo
- **全部中文 UI** — 按钮、标签、占位符、提示
- **API 调用走 `src/api/*.js`** — 页面禁止裸 `fetch()`
- **加载模式**: `ref(loading=true)` → `onMounted` async → `loading=false` → 模板 `v-if="loading"`
- **不新增 npm 依赖** — 除非明确批准
- **CSS 放 `style.css`** — 不用 `<style scoped>` 除非页面专属样式

---

## 关键编码模式

### 后端

```python
from app.core.database import db, fetch_all, fetch_one, utc_now

# 读取
row = fetch_one("SELECT * FROM datasets WHERE id = %s", (dataset_id,))
rows = fetch_all("SELECT * FROM training_runs ORDER BY id DESC")

# 写入
with db() as cur:
    cur.execute("INSERT INTO ... VALUES (%s, %s)", (a, b))
    result = cur.fetchone()

# 新路由
# 在 app/api/xxx.py 中: router = APIRouter(prefix="/api/xxx", tags=["xxx"])
# 在 app/main.py 中: app.include_router(xxx.router)

# Schema 变更: 只 ADD COLUMN, 不 drop/rename
# 在 database.py 的 _run_lightweight_migrations() 中加迁移

# 长任务: 用 threading.Thread 后台执行，不阻塞 HTTP
```

### 前端

```javascript
// 新页面: src/pages/NewPage.vue → router/index.js 懒加载 → AppShell.vue 加导航
// API: src/api/new_module.js → export async function xxx() { return get('/xxx') }
// CSS: 加在 style.css，复用已有 class
// 状态: ref() 存数据，computed() 派生，模板自动解包 .value
```

---

## 模块对接合约 (新模块必须遵守)

### 状态机

```
# 标注状态
annotation_status: unlabeled → ai_prelabel → reviewed

# 训练/评估状态
# created = 排队中（GPU 空闲时由 _maybe_start_next() 自动调度）
status: created → running → completed / failed

# 模型状态 (简化后只有两个)
is_production = 1     ← 设为生产 (同数据集只有一个)
model_format = ""     ← 原始 YOLO，非空 = 导出格式 (ONNX/TensorRT/TFLite)
```

### 数据集 → 训练

```
POST /api/projects/{id}/training-runs { dataset_version_id, base_model, epochs, imgsz, batch, device }
```

**前置条件**: dtype 必须是 `train` 或空（未分类），且 `label_file_count > 0`。`val`/`test`/`annotation` 不能用于训练。

### 数据集 → 标注

```
GET  /api/dataset-versions/{id}/annotation-progress  → { total, reviewed, unlabeled, next_unlabeled_image_id }
GET  /api/annotations/{image_id}                      → { image, boxes }
PUT  /api/annotations/{image_id} { boxes, status }    → 保存 + 自动创建修订快照
POST /api/annotations/{image_id}/prelabel { model_path, conf } → AI 预标注
```

**写入副作用**: `PUT` 更新 `image_items.annotation_status` → 然后调用方应触发 `refresh_dataset_version_metadata`

### 标注 → 数据集拆分

```
POST /api/dataset-versions/{id}/split-into { train_count, val_count, test_count | train_ratio, val_ratio, test_ratio }
```

**前置条件**: `dtype=annotation` 时只导出 `reviewed` 图片，其他 dtype 导出全部有标注图片。拆分后生成 3 个独立数据集（各含 `images/` + `labels/` + `data.yaml`），dtype 自动设为 train/val/test。

### 训练 → 模型注册

训练线程完成后自动执行（`trainer.py → artifact_collector.py`）：
1. 复制 `best.pt` / `last.pt` 到 `model_registry/`
2. 解析 `results.csv` → `training_metrics` 逐轮写入
3. 生成 `ai_training_report.md`
4. 创建 `model_versions` 行，关联 `training_run_id`

### 模型 → 评估

```
POST /api/projects/{id}/evaluation-runs { model_version_id, dataset_version_id }
```

**前置条件**: 数据集 `label_file_count > 0` 且 dtype 不是 `annotation`。评估在后台线程运行，状态流同训练。完成后生成 `evaluation_samples` 逐图结果。

### 模型 → 推理

```
POST /api/inference/predict { model_id, images[], conf, iou } → { results: [{ prediction_image_url, box_count }] }
```

**前置条件**: 模型必须存在且权重文件可访问。前端自动选中 `is_production=1` 的模型。

### 项目 → 数据集绑定

```
POST /api/projects/{id}/datasets { dataset_version_id, role }
```

绑定后项目内训练/评估可下拉选择已绑定数据集。`role` 字段记录用途（train/val/test），当前为软标记不影响过滤逻辑——过滤由 dtype 决定。

### 训练 → Agent

Agent 有两种获取数据的方式，优先级：**Tool Use > context_builder**。

**Tool Use (LLM 模式)**:
Agent 主动调用工具查询数据库，前端显示 🔧 气泡：
```
用户: "对比训练 #5 和 #3"
Agent: 🔧 compare_training_runs("run_5","run_3")  →  基于实际数据回复
```
工具定义在 `app/agents/tools.py`，11 个工具覆盖训练/评估/数据集/模型/搜索/对比/统计/全局上下文。

**Context Builder (预加载到 System Prompt)**:
```
GET /api/agent/context?project_id={id} → { datasets, runs, models, evaluations }
```
训练报告路径: `{model_registry_path}/{run_id}/ai_training_report.md`
评估报告路径: `{run_path}/ai_evaluation_report.md`

**非流式**: `POST /sessions/{id}/chat` → 返回完整 JSON (含 tool_calls 日志)
**流式**: `POST /sessions/{id}/chat/stream` → SSE 事件流 (chunk | tool_call | plan | title | done)

---

## 路径系统

DB 存相对路径（相对 DATA_DIR），读写用 `resolve_path()`/`relative_path()`（`app/core/config.py`）。兼容已有绝对路径。前端 `imageUrl()` 用 `datasets/` 子串匹配生成 URL。

## 前端性能

`<keep-alive :max="6">` 包裹 `<RouterView>`，页面切换不销毁。关键页面加 `onActivated(load)` 切回自动刷新。

## 当前状态 (2026-06-26)

| 已验证 |
|---|
| 数据集：创建/导入/上传/批量追加/续传/dtype/拆分/预览(Canvas框)/data.yaml查看 |
| 标注：Canvas编辑/预标注/修订历史/进度追踪/隐藏框/类别管理/跳转未标注 |
| 训练：后台/SSE日志/epoch进度条/指标轮询/产物收集/AI报告/optimizer+lr0/GPU下拉/备注 |
| 模型：注册/产物/下载/ONNX导出(进度条)/生产/备注(训练↔模型互相同步) |
| 项目：CRUD/绑定/训练表(模型名+run_id+mAP50+备注)/评估 |
| Agent：会话/聊天(LLM/rule/ToolUse)/计划/流式/AI标题 |
| 推理：图片(卡片)/测试集(大图网格+统计)/摄像头/ONNX优先.pt兜底 |
| 系统：设置/GPU检测/弱密码门禁(前端localStorage)/日志浅色主题 |

### Agent 架构 (2026-06-26 更新)

Agent 支持两种模式，在 `settings.json` 中切换 `agent_mode: "rule" | "llm"`：

**LLM Tool Use 模式** (`tools.py` + `chat_agent.py`):
- **11 个工具**（LLM 可主动调用，最多 5 轮循环）：
  get_training_detail, get_evaluation_detail, list_training_runs,
  list_evaluation_runs, get_dataset_detail, get_model_detail, compare_training_runs,
  get_dataset_label_stats, search_runs, get_project_summary, **get_full_context**
- 所有工具返回 `split_breakdown` (train/val/test 分布)
- 训练工具返回 `train_dataset` + `val_dataset` (含 image_count/class_count/dtype)
- 评估工具返回 `eval_dataset` (含 dtype/image_count/split_breakdown)
- 前端显示 🔧 tool_call 气泡

**规则分析模式** (`chat_agent.py` _rule_xxx):
- 7 个专项分析函数：过拟合诊断、训练分析、评估分析、数据质量、部署评估、对比、改进建议
- 纯本地计算，不调 API

**流式输出** (`chat_stream`):
- SSE endpoint `/sessions/{id}/chat/stream`
- 事件: chunk | tool_call | plan | title | done

**上下文构建** (`context_builder.py`):
- `build_context(project_id)` — 完整上下文塞入 System Prompt（LLM 模式用）
- `build_index(project_id)` — 轻量索引仅 ID/名称（备用）
- **数据集自动发现**: 从 training_runs (dataset_version_id + val_dataset_version_id) 和 evaluation_runs 的 UNION 查询自动发现项目引用的数据集，**不再依赖 project_dataset_bindings 表**

**计划系统** (`plan_service.py`):
- 保存时自动检测 training_run_id：composerRef → 标题匹配 → latest_run 兜底
- status: draft → archived → deleted (软删除，前端列表隐藏)
- is_read: 展开时自动标记 is_read=1，蓝点消失
- 前端在侧栏底部显示 (sidebar-plans)，支持筛选（活跃/已归档/全部）

**⚠️ 已知陷阱**:
- SYSTEM_PROMPT 中 JSON 示例的 `{` `}` 必须转义为 `{{` `}}`，否则 Python `.format()` 抛 KeyError → LLM 模式静默崩溃回退规则模式
- SQLite 不支持 `ILIKE`，必须用 `DB_BACKEND` 条件判断选择 `LIKE` / `ILIKE`
- `model_versions` 查询必须加 `WHERE training_run_id > 0` 过滤 ONNX 导出条目
- 训练绑定 val 数据集通过 `training_runs.val_dataset_version_id`，不再用 project_dataset_bindings

### AI 数据质量模块 (`ai_quality.py`)

三个纯本地分析（不调 AI API）:
- `check_image_quality()`: Laplacian 模糊检测 + 直方图曝光检测
- `find_duplicates()`: DCT 感知哈希 + 汉明距离
- `check_annotation_consistency()`: YOLO 推理 + IoU 对比人工标注

API: `GET /dataset-versions/{id}/ai-quality?checks=quality,duplicates,consistency`

### 已知待做

| 优先级 | 项目 | 说明 |
|---|---|---|
| 中 | 上下文面板不可跳转 | 看到训练名但点不了，需加 RouterLink |
| 中 | 计划只支持 3 参数 | epochs/imgsz/batch，需扩展 model/device |
| 低 | 长回复无折叠 | 超过 500 字应自动折叠 |
| 低 | 无对话导出 | Agent 分析结果无法保存为 Markdown |

### 已修复 (2026-06-26)

| 问题 | 修复 |
|---|---|
| LLM 调用 crash 静默回退规则模式 | SYSTEM_PROMPT 中 `{}` 与 Python `.format()` 冲突 → 转义为 `{{}}` |
| `search_runs` SQLite 报错 | `ILIKE` → `LIKE`（根据 DB_BACKEND 自适应） |
| ref picker 显示"暂无数据集" | 从训练/评估 UNOIN 自动发现数据集，不依赖 project_bindings |
| 训练上下文缺少数据集规模 | 加 `train_dataset`/`val_dataset` (image_count/class_count/dtype) 到 run_details |
| 训练和模型卡片展示重复 | 分开字段：训练卡 epochs/imgsz，模型卡 P/R/mAP50/best_epoch |
| 计划不绑定模型 | persistPlan 自动检测 composerRef + 标题匹配 + latest_run 兜底 |
| ONNX 导出混入模型列表 | `WHERE training_run_id > 0` 过滤 |
| 数据库垃圾数据 | 清理 57 个测试数据集，completed 训练残留 error 字段 |

### UI 重构 (2026-06-27)

**训练任务表** (`TrainingRunsPage.vue`):
- 列精简为 8 列：任务名称 | 关联数据集 | 模型架构 | 状态 | 进度(Epoch) | 最佳mAP | 剩余时间 | 操作
- `modelArch()` 从 base_model 提取架构名（`yolov8s.pt` → `YOLOv8s`），查表映射 YOLOv5/v8/v11 系列
- `epochProgressPct/Text()` 进度条 + X/Y epochs 文字，运行中进度条脉冲动画
- `bestMapDisplay()` 从关联 model_versions 读取 mAP50
- `remainingTime()` 线性估算：elapsed/completed × remaining，已完成显示 `-`
- 状态标签：created→排队中(warning)、running→运行中(info)、completed→已完成(success)
- 移除"项目"列，保留顶部项目筛选下拉

**数据集页面** (`DatasetsPage.vue`):
- 表格 → 自适应卡片网格 (`dataset-card-grid`，minmax(300px, 1fr))
- 每卡：名称+版本+dtype药丸下拉 + 4 统计数字 + 可选进度条 + 操作按钮行
- 标注中显示"已标注/进度%"，其他显示"含框图像/标签总数"
- dtype 选择器改为 `.dtype-pill` 紧凑药丸风格

**项目详情训练表** (`ProjectDetailPage.vue`):
- 与全局训练表列对齐：任务名称 | 数据集 | 架构 | 状态 | 进度 | mAP50 | 备注 | 操作
- 紧凑变体 `.training-table--compact`，新增 `archLabel()` + `statusChipClass()`

**训练排队系统** (`trainer.py`, 2026-06-27):
- `_gpu_lock = threading.Lock()` — GPU 互斥锁，确保同一时间只有一个训练使用 GPU
- `_maybe_start_next()` — 调度核心：检查 running → 取最早 created → 标记 running → 启动线程
- 训练完成/失败时 `finally` 块自动调用 `_maybe_start_next()` 启动下一个排队任务
- `_recover_orphaned_runs()` — 首次调度时自动将残留 running 标记为 failed（服务器重启恢复）
- `start_training_background()` 不再直接启动线程，改为委托 `_maybe_start_next()`

**新增 CSS 类** (`style.css`):
- `.dataset-card-grid` / `.dataset-card` / `.dsc-*` — 数据集卡片系统
- `.dtype-pill` — 紧凑 dtype 药丸下拉
- `.training-table` / `.training-table--compact` — 标准化训练表格
- `.model-arch-tag` / `.model-arch-tag--sm` — 模型架构标签（primary-soft 底）
- `.task-name-link` / `.map-value` / `.action-btn-group` — 辅助类
- `.progress-bar--running` — 运行中进度条（静态深灰，已去动画）

### 色板重构 (2026-06-27)
- 暖橙 `#F97316` → 中性灰 `#525252`，暖粉底 `#FFF8F5` → 冷灰白 `#F9FAFB`
- 全局毛玻璃：sidebar blur(20px)、card blur(8px)、dialog blur(12px)
- 去除装饰动画：logo-pulse、progress-pulse 渐变闪动
- 补定义 `--bg-warm` / `--primary-light`（之前漏定义导致回退异常）
- 组件硬编码色值同步修正（DatasetPreviewPage / AnnotationStudioPage / LoginPage / CameraPanel）

---
## Agent 数据流详解 (LLM 实际收到的数据)

### 训练详情 (get_training_detail / get_full_context)
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

### 评估详情 (get_evaluation_detail)
```json
{
  "run_id": "安全帽模型训练-E1-20260626T11",
  "precision": 0.692, "recall": 0.644,
  "map50": 0.691, "map50_95": 0.437,
  "eval_dataset": {"name": "安全帽全集-验证集/v001", "dtype": "val", "image_count": 20, "split_breakdown": {"train":0,"val":20,"test":0}}
}
```

### 数据集详情 (get_dataset_detail)
```json
{
  "dataset_name": "安全帽全集-训练集", "image_count": 30, "class_count": 2,
  "split_breakdown": {"train": 30, "val": 0, "test": 0}
}
```

### 数据流路径
```
用户点 + 选引用 → "[引用: 训练 T3] 分析..."
                        ↓
后端 build_context(project_id) → 查全部训练/评估/数据集/模型
                        ↓
System Prompt ← 塞入完整上下文 JSON
                        ↓
LLM 直接对比 train mAP 0.851 vs eval mAP 0.437 → 判断过拟合
```

---

## Agent 11 个工具速查

| # | 工具名 | 参数 | 返回要点 |
|---|---|---|---|
| 1 | `get_training_detail` | run_id | 训练参数 + P/R/mAP + train_dataset + val_dataset |
| 2 | `get_evaluation_detail` | run_id | 评估指标 + eval_dataset + 逐图样本 |
| 3 | `list_training_runs` | limit | 训练列表含关键指标 |
| 4 | `list_evaluation_runs` | limit | 评估列表含 eval_on_split、eval_image_count |
| 5 | `get_dataset_detail` | dataset_version_id | 规模 + split_breakdown + 审计 |
| 6 | `get_model_detail` | model_id | P/R/mAP50/best_epoch/is_production |
| 7 | `compare_training_runs` | run_id_a, run_id_b | 两次训练 delta 对比 (需 ≥2 条训练) |
| 8 | `get_dataset_label_stats` | dataset_version_id | 每类标注框数量和占比 |
| 9 | `search_runs` | query | 按关键词搜训练/评估 (LIKE/ILIKE 自适应) |
| 10 | `get_project_summary` | 无 | 项目统计概览 |
| 11 | `get_full_context` | 无 | 训练+数据集(split)+模型+评估 一次性全部返回 |

所有工具定义在 `app/agents/tools.py`，执行器约 500 行。每个工具返回 JSON 字符串，LLM 解析后回复用户。

---

## Agent 前端关键交互

### Ref Picker (数据引用选择器)
输入框旁 + 按钮，弹出面板四个标签页：

| 标签 | 卡片展示 |
|---|---|
| 🏋️ 训练 | epochs·imgsz + val mAP |
| 📊 评估 | 评估用数据集名 + 指标 |
| 📦 数据集 | dtype 标签 + 张数·类别数 |
| 🧠 模型 | P·R·mAP50 + best_epoch + 生产标记 |

**训练和模型展示不同数据**（之前重复显示相同字段）：
- 训练卡片：轮数、分辨率、验证mAP
- 模型卡片：精确率、召回率、mAP50、best_epoch、部署状态

选中后插入 `[引用: 训练 T3]` 格式文本到输入框。

### 计划侧栏 (AgentChatPage.vue)
- 位置：左侧栏底部 `.sidebar-plans`，max-height: 35%，overflow-y: auto
- 对话列表在上方 max-height: 50%
- 筛选按钮：活跃 / 已归档 / 全部
- 展开计划时自动调 `POST /api/agent/plans/{id}/read` 标记 is_read=1
- 未读计划显示蓝色圆点 `.plan-unread-dot`
- 应用按钮：把计划参数 (epochs/imgsz/batch) 填入训练表单

### persistPlan 模型绑定逻辑
保存计划时按优先级自动检测关联的训练：
1. 从 composerRef 解析用户选择的引用
2. 标题关键词匹配（如计划标题含 "安全帽模型训练-T2"）
3. 兜底：项目最新 training_run

---

## API 端点速查 (Agent 相关)

```
GET    /api/agent/sessions?project_id=            # 会话列表
POST   /api/agent/sessions { project_id, title }  # 创建会话
DELETE /api/agent/sessions/{id}                   # 删除会话
PUT    /api/agent/sessions/{id} { title }         # 重命名
POST   /api/agent/sessions/{id}/chat { message, refs[] }       # 非流式聊天
POST   /api/agent/sessions/{id}/chat/stream { message, refs[] } # SSE 流式聊天
GET    /api/agent/context?project_id=              # 上下文 JSON
POST   /api/agent/plans { session_id, title, content_json, training_run_id }  # 保存计划
GET    /api/agent/plans?project_id=&status=        # 计划列表
GET    /api/agent/plans/{id}                       # 计划详情
PATCH  /api/agent/plans/{id} { status }            # 更新状态 (draft/archived/deleted)
POST   /api/agent/plans/{id}/read                  # 标记已读
```

---

## 数据库当前状态 (2026-06-26)

- **DB 后端**: SQLite (`backend/data/yolops.db`)
- **数据集**: 3 个（安全帽全集-训练集 v001、安全帽全集-验证集 v001、安全帽全集-测试集 v001），已清理 57 个测试垃圾
- **训练记录**: 1 条（安全帽模型训练-T3，50 epoch，mAP50=0.975，mAP50-95=0.851）
- **评估记录**: 1 条（安全帽模型训练-E1，eval mAP50=0.691，mAP50-95=0.437，明显过拟合）
- **模型**: 1 个（关联 T3 训练，best_epoch=49）
- **项目**: 安全帽检测项目

---

## LLM 配置

```json
// backend/data/settings.json
{
  "agent_mode": "llm",           // "rule" | "llm"
  "llm_endpoint": "https://api.deepseek.com/v1",
  "llm_model": "deepseek-chat",
  "llm_api_key": "sk-...",
  "gpu_device": "cuda:0"
}
```

LLM 调用流程：
1. 用户消息 + System Prompt (含 build_context 完整上下文) → POST DeepSeek API
2. DeepSeek 返回 tool_calls → 后端执行工具查 DB → 结果追加到 messages
3. 最多 5 轮循环 → 最终回复流式输出到前端

---

## 测试状态

2026-06-26 全面测试：**17/18 通过**。唯一未通过项：`compare_training_runs` 需要 ≥2 条训练记录（当前项目只有 1 条）。

测试报告：`docs/agent-feature-report.md`

---

### 升级路线

**第一阶段: 体验打磨**
- ✅ 训练表列精简 + 模型架构标签 + 剩余时间估算 + 进度动画 (2026-06-27)
- ✅ 数据集页面卡片化 + dtype 药丸选择器 (2026-06-27)
- ✅ 训练 GPU 排队系统：_gpu_lock 互斥 + _maybe_start_next 调度 + 重启恢复 (2026-06-27)
- ✅ 色板重构：暖橙→中性灰 + 全局毛玻璃 + 去装饰动画 (2026-06-27)
- 上下文面板可点击跳转原页面
- 计划支持全部训练参数
- 对话历史搜索
- 长回复自动折叠

**第二阶段: 能力增强**
- 多模型对比分析 (3+ 次训练同时对比)
- 标注质量评分卡片 (0-100 分)
- YOLO-World 零样本预标注
- Agent 直接创建训练任务

**第三阶段: 真 Agent**
- 多步自主规划 ("帮我提升 mAP" → 分析→训练→评估→报告)
- 主动学习 (Agent 选最不确定的图片让人标)
- 知识库 (历史训练参数和结果积累)
