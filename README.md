# YOLOps-Agent

工业目标检测数据集管理、YOLO 标注工作台、训练归档与 Agent 迭代平台。

这个项目不是“上传图片跑一次 YOLO”的演示，而是面向面试和工程实践的轻量级 YOLOps 系统。它关注目标检测项目真正麻烦的部分：数据集版本、逐图查看图片和 YOLO txt 标注、标注修订历史、训练任务、`best.pt` 归档、训练指标分析，以及 Agent 对下一轮数据和参数的迭代建议。

## 快速开始

### 1. 启动前端

```powershell
cd D:\workspace\YOLOps-Agent\frontend
npm install
npm run dev
```

访问：

```text
http://127.0.0.1:5174
```

### 2. 启动后端

当前开发演示默认使用 SQLite，避免被 WSL、容器和端口转发卡住。数据库、图片、导出数据集、训练产物和模型仓库都放在项目本地：

```text
D:\workspace\YOLOps-Agent\backend\data
```

```powershell
cd D:\workspace\YOLOps-Agent\backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8009
```

后端地址：

```text
http://127.0.0.1:8009
```

API 文档：

```text
http://127.0.0.1:8009/docs
```

## 当前进度

### 已完成的基础能力

- Vue 3 + Vite 前端骨架，中文 UI
- Stitch 风格迁移：暖橙主色 `#F97316`、偏白背景 `#FFF8F5`
- FastAPI 后端 API 骨架
- 数据集导入 + YOLO txt 质检 + 版本管理 + SHA256 指纹
- 标注工作台组件：Canvas bbox 渲染、画框、选框、删框、缩放、平移、快捷键
- 标注修订历史：保存快照到 `.yolops/history/`，支持查看和恢复
- 训练任务：后台线程启动 YOLO，归档 `best.pt` 和训练指标
- 模型仓库：候选模型、生产模型标记
- Agent 后端：会话、消息、上下文构建、迭代计划保存

### 当前最重要的开发重点

- 把数据集工作区做成真实图片浏览器：打开数据集版本后能一张一张查看图片和 bbox 状态。
- 把标注工作台接到真实图片和真实 txt：每次保存都留下修订历史。
- 把 Agent 对话页做完整：围绕训练参数、数据补充、标注复核生成可保存的下一轮计划。
- 准备一个 50 到 100 张图片的小型 YOLO 数据集，跑通端到端演示。

## 项目结构

```text
YOLOps-Agent/
├─ frontend/              # Vue 前端工作台
├─ backend/               # FastAPI 后端
├─ docs/                  # 项目文档
└─ ui-design/             # Stitch 导出稿与参考图
```

> 🧪 feat/agent-explore 分支新增：Agent 自动探索数据集功能，自动扫描数据集质量并生成优化建议。

## 核心卖点

- SQLite 元数据管理：数据集、图片索引、标注历史、训练任务、Agent 会话都结构化入库；图片、txt、pt 和训练图表仍保存在项目本地文件系统。
- 数据集工作区：每个版本都有 manifest、fingerprint 和图片索引。
- 逐图标注：打开真实图片，读取 YOLO txt，渲染和编辑 bbox。
- 标注历史：每次保存生成快照，可查看和恢复。
- 标注质量门禁：训练前检查缺失 txt、孤儿 txt、越界 bbox、类别不均衡。
- 训练任务管理：训练绑定数据集版本和参数快照。
- 模型仓库：每次训练自动归档 `best.pt`、`last.pt`、`results.csv` 和指标。
- Agent 对话：基于数据质量、训练指标和模型状态回答问题，并保存下一轮迭代计划。

## 文档

- [快速开始](./docs/quick-start.md)
- [项目计划书](./docs/project-plan.md)
- [系统架构](./docs/architecture.md)
- [前端开发说明](./docs/frontend-guide.md)
- [后端开发说明](./docs/backend-guide.md)
- [开发路线图](./docs/development-roadmap.md)
- [API 接口规范](./docs/api-spec.md) — 前后端联调 Shape 约定
- [前端组件规范](./docs/frontend-component-spec.md) — 组件 Props / 新增页面模板 / CSS class 速查
- [Track B 实现记录](./docs/track-b-implementation.md) — Phase 1 前端接入完成情况
