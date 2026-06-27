"""
Agent 工具定义 — YOLOps Agent 可以主动调用的数据库查询工具。

每个工具包含:
  - schema: OpenAI-compatible function definition
  - execute: 实际执行函数，返回字符串结果
"""

import json
from pathlib import Path

from app.core.database import fetch_all, fetch_one


def _fmt(v, default="-"):
    if v is None: return default
    try: return f"{float(v):.3f}"
    except: return str(v)


# ═══════════════════════════════════════════════════════════════════════════
# 工具注册表
# ═══════════════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_training_detail",
            "description": "获取指定训练任务的完整详情：参数、指标、状态、数据集信息。按 run_id 或 id 查询。",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "训练 run_id，如 helme-t1-20260626"},
                    "id": {"type": "integer", "description": "训练记录主键 id"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_evaluation_detail",
            "description": "获取指定评估/验证任务的完整详情：精度、召回率、mAP、逐图预测样本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "评估 run_id"},
                    "id": {"type": "integer", "description": "评估记录主键 id"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_training_runs",
            "description": "列出最近的训练任务及关键指标。可按项目筛选。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目 id，不传则查全部"},
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_evaluation_runs",
            "description": "列出最近的评估/验证任务及关键指标。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目 id"},
                    "limit": {"type": "integer", "description": "返回条数，默认 10"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dataset_detail",
            "description": "获取数据集版本的详细信息：图片数、类别、标注进度、审计结果。",
            "parameters": {
                "type": "object",
                "properties": {
                    "version_id": {"type": "integer", "description": "数据集版本 id"},
                },
                "required": ["version_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_model_detail",
            "description": "获取模型版本的详细信息：指标、权重路径、是否生产标记。",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "模型版本 id"},
                    "run_id": {"type": "string", "description": "模型 run_id"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_training_runs",
            "description": "对比两次训练任务的指标差异。",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id_1": {"type": "string", "description": "第一个训练 run_id"},
                    "run_id_2": {"type": "string", "description": "第二个训练 run_id"},
                },
                "required": ["run_id_1", "run_id_2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dataset_label_stats",
            "description": "获取指定数据集的标注统计：每类标注框数量、占比。",
            "parameters": {
                "type": "object",
                "properties": {
                    "version_id": {"type": "integer", "description": "数据集版本 id"},
                },
                "required": ["version_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_runs",
            "description": "按关键词搜索训练或评估任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词（匹配 run_id 或状态）"},
                    "kind": {"type": "string", "enum": ["training", "evaluation", "all"], "description": "类型：training/evaluation/all"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_summary",
            "description": "获取项目的综合摘要：数据集数量、训练/评估/模型总数、最新指标。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "项目 id，不传则查全局"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_full_context",
            "description": "获取训练任务的完整上下文：训练参数+指标、关联的数据集详情、关联的模型、关联的评估记录。一次调用获取所有相关信息。",
            "parameters": {
                "type": "object",
                "properties": {
                    "training_run_id": {"type": "string", "description": "训练 run_id"},
                },
                "required": ["training_run_id"],
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# 工具执行器
# ═══════════════════════════════════════════════════════════════════════════

def execute_tool(name: str, args: dict) -> str:
    """执行工具调用，返回 JSON 字符串。"""
    if name == "get_training_detail":
        return _tool_get_training_detail(args)
    elif name == "get_evaluation_detail":
        return _tool_get_evaluation_detail(args)
    elif name == "list_training_runs":
        return _tool_list_training_runs(args)
    elif name == "list_evaluation_runs":
        return _tool_list_evaluation_runs(args)
    elif name == "get_dataset_detail":
        return _tool_get_dataset_detail(args)
    elif name == "get_model_detail":
        return _tool_get_model_detail(args)
    elif name == "compare_training_runs":
        return _tool_compare_runs(args)
    elif name == "get_dataset_label_stats":
        return _tool_get_label_stats(args)
    elif name == "search_runs":
        return _tool_search_runs(args)
    elif name == "get_project_summary":
        return _tool_get_project_summary(args)
    elif name == "get_full_context":
        return _tool_get_full_context(args)
    else:
        return json.dumps({"error": f"Unknown tool: {name}"})


def _json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _tool_get_training_detail(args: dict) -> str:
    run_id = args.get("run_id")
    rid = args.get("id")
    if rid:
        run = fetch_one("SELECT tr.*, dv.version, d.name AS dataset_name FROM training_runs tr LEFT JOIN dataset_versions dv ON dv.id=tr.dataset_version_id LEFT JOIN datasets d ON d.id=dv.dataset_id WHERE tr.id=%s", (rid,))
    elif run_id:
        run = fetch_one("SELECT tr.*, dv.version, d.name AS dataset_name FROM training_runs tr LEFT JOIN dataset_versions dv ON dv.id=tr.dataset_version_id LEFT JOIN datasets d ON d.id=dv.dataset_id WHERE tr.run_id=%s", (run_id,))
    else:
        run = fetch_one("SELECT tr.*, dv.version, d.name AS dataset_name FROM training_runs tr LEFT JOIN dataset_versions dv ON dv.id=tr.dataset_version_id LEFT JOIN datasets d ON d.id=dv.dataset_id ORDER BY tr.id DESC LIMIT 1")
    if not run:
        return _json({"error": "Training run not found"})
    # 关联模型
    model = fetch_one("SELECT precision,recall,map50,map50_95,best_epoch,is_production FROM model_versions WHERE training_run_id=%s LIMIT 1", (run["id"],))
    # 验证集信息
    val_dataset = None
    if run.get("val_dataset_version_id"):
        vds = fetch_one("SELECT dv.dtype, dv.image_count, d.name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s", (run["val_dataset_version_id"],))
        if vds:
            val_dataset = {"name": vds["name"], "image_count": vds.get("image_count",0), "dtype": vds.get("dtype","")}
    return _json({
        "id": run["id"], "run_id": run.get("run_id",""), "status": run.get("status",""),
        "base_model": run.get("base_model",""), "epochs": run.get("epochs",0),
        "imgsz": run.get("imgsz",0), "batch": run.get("batch",0),
        "dataset": f"{run.get('dataset_name','')}/{run.get('version','')}",
        "dataset_version_id": run.get("dataset_version_id"),
        "val_dataset": val_dataset,
        "precision": _fmt(model["precision"]) if model else "-",
        "recall": _fmt(model["recall"]) if model else "-",
        "map50": _fmt(model["map50"]) if model else "-",
        "map50_95": _fmt(model["map50_95"]) if model else "-",
        "best_epoch": model.get("best_epoch") if model else None,
        "is_production": bool(model.get("is_production")) if model else False,
        "started_at": run.get("started_at",""), "finished_at": run.get("finished_at",""),
        "error": run.get("error",""),
    })


def _tool_get_evaluation_detail(args: dict) -> str:
    run_id = args.get("run_id")
    rid = args.get("id")
    if rid:
        run = fetch_one("SELECT * FROM evaluation_runs WHERE id=%s", (rid,))
    elif run_id:
        run = fetch_one("SELECT * FROM evaluation_runs WHERE run_id=%s", (run_id,))
    else:
        run = fetch_one("SELECT * FROM evaluation_runs ORDER BY id DESC LIMIT 1")
    if not run:
        return _json({"error": "Evaluation run not found"})
    samples = fetch_all("SELECT image_path,confidence_summary FROM evaluation_samples WHERE evaluation_run_id=%s LIMIT 10", (run["id"],))
    # 获取关联的数据集信息
    ds_info = fetch_one(
        "SELECT dv.version, dv.dtype, dv.image_count, d.name AS dataset_name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s",
        (run.get("dataset_version_id"),),
    )
    eval_dataset = None
    if ds_info:
        # 查 split 分布
        ds_splits = fetch_all("SELECT split, COUNT(*) as cnt FROM image_items WHERE dataset_version_id=%s GROUP BY split", (run["dataset_version_id"],))
        split_map = {s["split"]: s["cnt"] for s in (ds_splits or [])}
        eval_dataset = {
            "name": f"{ds_info.get('dataset_name','')}/{ds_info.get('version','')}",
            "dtype": ds_info.get("dtype",""),
            "image_count": ds_info.get("image_count",0),
            "split_breakdown": {
                "train": split_map.get("train", 0),
                "val": split_map.get("val", 0),
                "test": split_map.get("test", 0),
            },
        }
    return _json({
        "id": run["id"], "run_id": run.get("run_id",""), "status": run.get("status",""),
        "precision": _fmt(run.get("precision")), "recall": _fmt(run.get("recall")),
        "map50": _fmt(run.get("map50")), "map50_95": _fmt(run.get("map50_95")),
        "eval_dataset": eval_dataset,
        "samples": [{"image": s.get("image_path",""), "confidence": s.get("confidence_summary","")} for s in (samples or [])],
        "report_summary": run.get("summary",""),
        "started_at": run.get("started_at",""), "finished_at": run.get("finished_at",""),
    })


def _tool_list_training_runs(args: dict) -> str:
    limit = args.get("limit", 10)
    pid = args.get("project_id")
    if pid:
        rows = fetch_all("SELECT tr.id,tr.run_id,tr.status,tr.epochs,tr.imgsz,tr.batch,tr.base_model,mv.precision,mv.recall,mv.map50,mv.map50_95 FROM training_runs tr LEFT JOIN model_versions mv ON mv.training_run_id=tr.id WHERE tr.project_id=%s ORDER BY tr.id DESC LIMIT %s", (pid, limit))
    else:
        rows = fetch_all("SELECT tr.id,tr.run_id,tr.status,tr.epochs,tr.imgsz,tr.batch,tr.base_model,mv.precision,mv.recall,mv.map50,mv.map50_95 FROM training_runs tr LEFT JOIN model_versions mv ON mv.training_run_id=tr.id ORDER BY tr.id DESC LIMIT %s", (limit,))
    return _json([{
        "id": r["id"], "run_id": r.get("run_id",""), "status": r.get("status",""),
        "base_model": r.get("base_model",""), "epochs": r.get("epochs",0),
        "precision": _fmt(r.get("precision")), "recall": _fmt(r.get("recall")),
        "map50": _fmt(r.get("map50")), "map50_95": _fmt(r.get("map50_95")),
    } for r in rows])


def _tool_list_evaluation_runs(args: dict) -> str:
    limit = args.get("limit", 10)
    pid = args.get("project_id")
    if pid:
        rows = fetch_all("SELECT er.id,er.run_id,er.status,er.precision,er.recall,er.map50,er.map50_95,er.dataset_version_id,dv.dtype,dv.image_count FROM evaluation_runs er LEFT JOIN dataset_versions dv ON dv.id=er.dataset_version_id WHERE er.project_id=%s ORDER BY er.id DESC LIMIT %s", (pid, limit))
    else:
        rows = fetch_all("SELECT er.id,er.run_id,er.status,er.precision,er.recall,er.map50,er.map50_95,er.dataset_version_id,dv.dtype,dv.image_count FROM evaluation_runs er LEFT JOIN dataset_versions dv ON dv.id=er.dataset_version_id ORDER BY er.id DESC LIMIT %s", (limit,))
    return _json([{
        "id": r["id"], "run_id": r.get("run_id",""), "status": r.get("status",""),
        "precision": _fmt(r.get("precision")), "recall": _fmt(r.get("recall")),
        "map50": _fmt(r.get("map50")), "map50_95": _fmt(r.get("map50_95")),
        "dataset_version_id": r.get("dataset_version_id"),
        "eval_on_split": r.get("dtype",""), "eval_image_count": r.get("image_count",0),
    } for r in rows])


def _tool_get_dataset_detail(args: dict) -> str:
    vid = args["version_id"]
    v = fetch_one("SELECT dv.*, d.name AS dataset_name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s", (vid,))
    if not v:
        return _json({"error": f"Dataset version {vid} not found"})
    # 标注进度
    progress = fetch_one("SELECT COUNT(*) as total, SUM(CASE WHEN annotation_status='reviewed' THEN 1 ELSE 0 END) as reviewed FROM image_items WHERE dataset_version_id=%s", (vid,))
    # split 分布（train/val/test/unlabeled 各多少张）
    splits = fetch_all("SELECT split, COUNT(*) as cnt FROM image_items WHERE dataset_version_id=%s GROUP BY split ORDER BY cnt DESC", (vid,))
    split_map = {s["split"]: s["cnt"] for s in (splits or [])}
    return _json({
        "id": v["id"], "name": f"{v.get('dataset_name','')}/{v.get('version','')}",
        "image_count": v.get("image_count",0), "class_count": v.get("class_count",0),
        "dtype": v.get("dtype",""), "status": v.get("status",""),
        "split_breakdown": {
            "train": split_map.get("train", 0),
            "val": split_map.get("val", 0),
            "test": split_map.get("test", 0),
            "unlabeled": split_map.get("unlabeled", 0),
        },
        "audit": {
            "missing_labels": v.get("missing_labels",0),
            "orphan_labels": v.get("orphan_labels",0),
            "invalid_bboxes": v.get("invalid_bboxes",0),
            "empty_labels": v.get("empty_labels",0),
        },
        "annotation_progress": {
            "total": progress["total"] if progress else 0,
            "reviewed": progress["reviewed"] if progress else 0,
        } if progress else None,
    })


def _tool_get_model_detail(args: dict) -> str:
    rid = args.get("id")
    run_id = args.get("run_id")
    if rid:
        m = fetch_one("SELECT * FROM model_versions WHERE id=%s", (rid,))
    elif run_id:
        m = fetch_one("SELECT * FROM model_versions WHERE run_id=%s", (run_id,))
    else:
        m = fetch_one("SELECT * FROM model_versions ORDER BY id DESC LIMIT 1")
    if not m:
        return _json({"error": "Model not found"})
    return _json({
        "id": m["id"], "run_id": m.get("run_id",""),
        "precision": _fmt(m.get("precision")), "recall": _fmt(m.get("recall")),
        "map50": _fmt(m.get("map50")), "map50_95": _fmt(m.get("map50_95")),
        "best_epoch": m.get("best_epoch"),
        "is_production": bool(m.get("is_production")),
        "is_candidate": bool(m.get("is_candidate")),
        "model_format": m.get("model_format",""),
        "best_pt_path": m.get("best_pt_path",""),
    })


def _tool_compare_runs(args: dict) -> str:
    id1, id2 = args["run_id_1"], args["run_id_2"]
    a = fetch_one("SELECT tr.*, mv.precision,mv.recall,mv.map50,mv.map50_95 FROM training_runs tr LEFT JOIN model_versions mv ON mv.training_run_id=tr.id WHERE tr.run_id=%s", (id1,))
    b = fetch_one("SELECT tr.*, mv.precision,mv.recall,mv.map50,mv.map50_95 FROM training_runs tr LEFT JOIN model_versions mv ON mv.training_run_id=tr.id WHERE tr.run_id=%s", (id2,))
    if not a or not b:
        return _json({"error": "One or both runs not found"})
    keys = [("precision","Precision"),("recall","Recall"),("map50","mAP50"),("map50_95","mAP50-95")]
    comparison = []
    for k, label in keys:
        av, bv = a.get(k), b.get(k)
        if av is not None and bv is not None:
            comparison.append({"metric": label, "a": round(float(av),3), "b": round(float(bv),3), "delta": round(float(av)-float(bv),3)})
    return _json({
        "run_a": {"run_id": a.get("run_id",""), "status": a.get("status",""), "epochs": a.get("epochs",0)},
        "run_b": {"run_id": b.get("run_id",""), "status": b.get("status",""), "epochs": b.get("epochs",0)},
        "comparison": comparison,
    })


def _tool_get_label_stats(args: dict) -> str:
    vid = args["version_id"]
    v = fetch_one("SELECT * FROM dataset_versions WHERE id=%s", (vid,))
    if not v:
        return _json({"error": f"Version {vid} not found"})
    images = fetch_all("SELECT label_path FROM image_items WHERE dataset_version_id=%s AND label_path IS NOT NULL AND label_path != ''", (vid,))
    if not images:
        return _json({"error": "No labeled images in this version"})
    # 读取 class_names
    class_names = []
    try:
        import json as _j
        cn = v.get("class_names_json") or v.get("class_names") or "[]"
        if isinstance(cn, str):
            class_names = _j.loads(cn) if cn.startswith("[") else cn.split(",")
    except:
        class_names = []
    if not class_names:
        class_names = [f"class_{i}" for i in range(v.get("class_count", 0))]
    # 统计
    from collections import Counter
    counter = Counter()
    total = 0
    for img in images:
        lp = Path(img["label_path"])
        if lp.exists():
            for line in lp.read_text(encoding="utf-8").splitlines():
                parts = line.strip().split()
                if parts:
                    cid = int(parts[0])
                    name = class_names[cid] if cid < len(class_names) else f"class_{cid}"
                    counter[name] += 1
                    total += 1
    stats = [{"class": name, "count": counter.get(name, 0), "pct": round(counter.get(name,0)/max(total,1)*100,1)} for name in class_names]
    return _json({"total_boxes": total, "class_distribution": stats, "class_names": class_names})


def _tool_search_runs(args: dict) -> str:
    from app.core.config import DB_BACKEND
    query = f"%{args['query']}%"
    kind = args.get("kind", "all")
    like_op = "ILIKE" if DB_BACKEND == "postgres" else "LIKE"
    results = []
    if kind in ("training", "all"):
        rows = fetch_all(f"SELECT id,run_id,status FROM training_runs WHERE run_id {like_op} %s OR status {like_op} %s ORDER BY id DESC LIMIT 10", (query, query))
        for r in rows:
            results.append({"type": "training", "id": r["id"], "run_id": r.get("run_id",""), "status": r.get("status","")})
    if kind in ("evaluation", "all"):
        rows = fetch_all(f"SELECT id,run_id,status FROM evaluation_runs WHERE run_id {like_op} %s OR status {like_op} %s ORDER BY id DESC LIMIT 10", (query, query))
        for r in rows:
            results.append({"type": "evaluation", "id": r["id"], "run_id": r.get("run_id",""), "status": r.get("status","")})
    return _json(results)


def _tool_get_project_summary(args: dict) -> str:
    pid = args.get("project_id")
    if pid:
        proj = fetch_one("SELECT * FROM projects WHERE id=%s", (pid,))
        ds_count = fetch_one("SELECT COUNT(*) as c FROM project_dataset_bindings WHERE project_id=%s AND is_active=1", (pid,))
        tr_count = fetch_one("SELECT COUNT(*) as c FROM training_runs WHERE project_id=%s", (pid,))
        ev_count = fetch_one("SELECT COUNT(*) as c FROM evaluation_runs WHERE project_id=%s", (pid,))
        md_count = fetch_one("SELECT COUNT(*) as c FROM model_versions WHERE project_id=%s", (pid,))
        latest_tr = fetch_one("SELECT run_id,status FROM training_runs WHERE project_id=%s ORDER BY id DESC LIMIT 1", (pid,))
    else:
        proj = None
        ds_count = fetch_one("SELECT COUNT(*) as c FROM datasets")
        tr_count = fetch_one("SELECT COUNT(*) as c FROM training_runs")
        ev_count = fetch_one("SELECT COUNT(*) as c FROM evaluation_runs")
        md_count = fetch_one("SELECT COUNT(*) as c FROM model_versions")
        latest_tr = fetch_one("SELECT run_id,status FROM training_runs ORDER BY id DESC LIMIT 1")

    return _json({
        "project": proj.get("name") if proj else "全局",
        "datasets": ds_count["c"] if ds_count else 0,
        "training_runs": tr_count["c"] if tr_count else 0,
        "evaluation_runs": ev_count["c"] if ev_count else 0,
        "models": md_count["c"] if md_count else 0,
        "latest_training": {"run_id": latest_tr["run_id"], "status": latest_tr["status"]} if latest_tr else None,
    })


def _tool_get_full_context(args: dict) -> str:
    """
    获取训练任务的完整上下文：
      - 训练参数和指标
      - 关联的数据集（图片数、类别、标注进度、审计结果）
      - 关联的模型（权重、部署状态）
      - 关联的评估（如果有）
    一次调用返回所有关联信息。
    """
    run_id = args["training_run_id"]
    run = fetch_one("SELECT * FROM training_runs WHERE run_id=%s", (run_id,))
    if not run:
        return _json({"error": f"Training run {run_id} not found"})

    # 训练详情
    model = fetch_one("SELECT * FROM model_versions WHERE training_run_id=%s LIMIT 1", (run["id"],))
    # 验证集
    val_ds = None
    if run.get("val_dataset_version_id"):
        vds = fetch_one("SELECT dv.dtype, dv.image_count, d.name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s", (run["val_dataset_version_id"],))
        if vds:
            val_ds = {"name": vds["name"], "image_count": vds.get("image_count",0), "dtype": vds.get("dtype","")}
    training = {
        "id": run["id"], "run_id": run.get("run_id",""), "status": run.get("status",""),
        "base_model": run.get("base_model",""), "epochs": run.get("epochs",0),
        "imgsz": run.get("imgsz",0), "batch": run.get("batch",0),
        "dataset_version_id": run.get("dataset_version_id"),
        "val_dataset": val_ds,
        "precision": _fmt(model.get("precision")) if model else "-",
        "recall": _fmt(model.get("recall")) if model else "-",
        "map50": _fmt(model.get("map50")) if model else "-",
        "map50_95": _fmt(model.get("map50_95")) if model else "-",
        "best_epoch": model.get("best_epoch") if model else None,
        "started_at": run.get("started_at",""), "finished_at": run.get("finished_at",""),
    }

    # 关联数据集
    version = fetch_one("SELECT dv.*, d.name AS dataset_name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s", (run.get("dataset_version_id"),))
    dataset = None
    if version:
        progress = fetch_one("SELECT COUNT(*) as total, SUM(CASE WHEN annotation_status='reviewed' THEN 1 ELSE 0 END) as reviewed FROM image_items WHERE dataset_version_id=%s", (version["id"],))
        # split 分布
        ds_splits = fetch_all("SELECT split, COUNT(*) as cnt FROM image_items WHERE dataset_version_id=%s GROUP BY split", (version["id"],))
        split_map = {s["split"]: s["cnt"] for s in (ds_splits or [])}
        dataset = {
            "id": version["id"], "name": f"{version.get('dataset_name','')}/{version.get('version','')}",
            "image_count": version.get("image_count",0), "class_count": version.get("class_count",0),
            "dtype": version.get("dtype",""),
            "split_breakdown": {
                "train": split_map.get("train", 0),
                "val": split_map.get("val", 0),
                "test": split_map.get("test", 0),
                "unlabeled": split_map.get("unlabeled", 0),
            },
            "audit": {
                "missing_labels": version.get("missing_labels",0),
                "orphan_labels": version.get("orphan_labels",0),
                "invalid_bboxes": version.get("invalid_bboxes",0),
                "empty_labels": version.get("empty_labels",0),
            },
            "annotation_progress": {
                "total": progress["total"] if progress else 0,
                "reviewed": progress["reviewed"] if progress else 0,
            } if progress else None,
        }

    # 关联模型
    model_info = None
    if model:
        model_info = {
            "id": model["id"], "run_id": model.get("run_id",""),
            "precision": _fmt(model.get("precision")), "recall": _fmt(model.get("recall")),
            "map50": _fmt(model.get("map50")), "map50_95": _fmt(model.get("map50_95")),
            "is_production": bool(model.get("is_production")),
            "best_pt_path": model.get("best_pt_path",""),
        }

    # 关联评估
    evaluations = fetch_all("SELECT id,run_id,status,precision,recall,map50,map50_95,summary FROM evaluation_runs WHERE model_version_id=%s ORDER BY id DESC LIMIT 5", (model["id"],)) if model else []
    eval_list = [{
        "id": e["id"], "run_id": e.get("run_id",""), "status": e.get("status",""),
        "precision": _fmt(e.get("precision")), "recall": _fmt(e.get("recall")),
        "map50": _fmt(e.get("map50")), "map50_95": _fmt(e.get("map50_95")),
        "summary": e.get("summary",""),
    } for e in (evaluations or [])]

    return _json({
        "training": training,
        "dataset": dataset,
        "model": model_info,
        "evaluations": eval_list,
    })
