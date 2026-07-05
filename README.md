# YOLOps-Agent

YOLOps-Agent 是一个面向目标检测流程的轻量化 YOLOps 工作台，覆盖项目管理、数据集与标注、训练任务、模型归档和 Agent 分析。

它关注的是目标检测项目里更完整的工程链路，而不是单次推理 demo。项目默认以本地单机运行方式组织数据、训练和模型产物，适合继续维护、演示和功能扩展。

## 功能概览

- 项目管理：创建项目，关联数据集、训练任务和模型版本
- 数据集管理：导入 YOLO 数据集、查看版本、浏览图片与标注状态
- 标注工作台：逐图查看、编辑和保存标注结果
- 训练管理：发起训练、查看进度、读取日志、归档训练产物
- 模型管理：统一查看模型版本、指标、来源训练和导出结果
- Agent 分析：基于项目上下文分析训练、模型和数据集情况

## 界面预览

### 全局概览

![YOLOps-Agent 全局概览](./docs/readme-overview.png)

### Agent 对话

![YOLOps-Agent Agent 对话](./docs/readme-agent-chat.png)

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端 | Vue 3, Vite, Vue Router |
| 后端 | FastAPI, Pydantic, SQLModel |
| 训练 | Ultralytics YOLO |
| Agent | LangChain / LangGraph |
| 数据库 | SQLite 默认，PostgreSQL 可切换 |
| 存储 | 本地磁盘保存图片、标注、模型和训练产物 |

## 业务流程

```mermaid
flowchart LR
    A[创建项目] --> B[导入数据集]
    B --> C[预览与标注]
    C --> D[发起训练]
    D --> E[归档模型]
    E --> F[Agent 分析]
```

## 项目结构

```text
YOLOps-Agent/
├─ backend/                  # FastAPI 后端
│  ├─ app/
│  │  ├─ api/                # API 路由
│  │  ├─ agents/             # Agent 与分析能力
│  │  ├─ annotation/         # 标注读写与处理
│  │  ├─ dataset/            # 数据集导入、统计和版本管理
│  │  ├─ training/           # 训练与评估任务
│  │  ├─ registry/           # 模型归档和管理
│  │  └─ core/               # 配置、数据库、路径等基础能力
│  ├─ .env.example
│  └─ requirements.txt
├─ frontend/                 # Vue 3 + Vite 前端
│  ├─ src/
│  │  ├─ api/                # 前端 API 封装
│  │  ├─ components/         # 复用组件
│  │  ├─ layouts/            # 页面布局
│  │  └─ pages/              # 页面视图
│  └─ package.json
├─ docs/
├─ AGENTS.md
└─ README.md
```

## 本地启动

### 后端

```powershell
cd D:\workspace\YOLOps-Agent\backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

后端地址：

- API：`http://127.0.0.1:8000`
- Swagger：`http://127.0.0.1:8000/docs`

### 前端

```powershell
cd D:\workspace\YOLOps-Agent\frontend
npm install
npm run dev
```

前端地址：

- Web：`http://127.0.0.1:5174`

## 环境配置

配置模板见 [backend/.env.example](./backend/.env.example)。

默认使用 SQLite：

```env
DB_BACKEND=sqlite
SQLITE_PATH=D:\workspace\YOLOps-Agent\backend\data\yolops.db
```

如需切换 PostgreSQL：

```env
DB_BACKEND=postgres
PG_HOST=127.0.0.1
PG_PORT=55432
PG_USER=yolops
PG_PASSWORD=yolops123
PG_DATABASE=yolops
```

## 数据与产物

项目运行过程中会在本地磁盘保存：

- 数据集图片与标签
- 训练日志与运行产物
- 模型权重与导出文件
- 推理结果与分析报告

这些运行产物默认不应提交到 Git，仓库主要保留源码、配置模板和必要文档。

## 相关文档

- [AGENTS.md](./AGENTS.md)
- [docs/项目实现与架构总览.md](./docs/%E9%A1%B9%E7%9B%AE%E5%AE%9E%E7%8E%B0%E4%B8%8E%E6%9E%B6%E6%9E%84%E6%80%BB%E8%A7%88.md)
- [docs/YOLOps-Agent 打包发布实施清单.md](./docs/YOLOps-Agent%20%E6%89%93%E5%8C%85%E5%8F%91%E5%B8%83%E5%AE%9E%E6%96%BD%E6%B8%85%E5%8D%95.md)
