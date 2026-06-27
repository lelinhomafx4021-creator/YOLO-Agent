from pathlib import Path
from typing import Any

from app.core.config import DATASETS_DIR, MODEL_REGISTRY_DIR, RUNS_DIR
from app.core.database import fetch_all, fetch_one


def build_context(project_id: int | None = None) -> dict[str, Any]:
    if project_id:
        project = fetch_one("SELECT * FROM projects WHERE id = %s", (project_id,))
        # ── 从训练/评估记录自动发现数据集（不再依赖 project_dataset_bindings）──
        # 收集该项目的训练和评估引用的所有 dataset_version_id
        ref_rows = fetch_all(
            """
            SELECT DISTINCT dv_id, role FROM (
                SELECT tr.dataset_version_id AS dv_id, 'train' AS role FROM training_runs tr WHERE tr.project_id = %s AND tr.dataset_version_id IS NOT NULL
                UNION
                SELECT tr.val_dataset_version_id AS dv_id, 'val' AS role FROM training_runs tr WHERE tr.project_id = %s AND tr.val_dataset_version_id IS NOT NULL
                UNION
                SELECT er.dataset_version_id AS dv_id, 'eval' AS role FROM evaluation_runs er WHERE er.project_id = %s AND er.dataset_version_id IS NOT NULL
            ) refs
            """,
            (project_id, project_id, project_id),
        )
        # 去重取最大 role（train > val > eval 优先级）
        role_map = {}
        for r in (ref_rows or []):
            dv_id = r["dv_id"]
            cur = role_map.get(dv_id, "")
            new_role = r["role"]
            # 优先级: train > val > eval
            priority = {"train": 3, "val": 2, "eval": 1}
            if priority.get(new_role, 0) > priority.get(cur, 0):
                role_map[dv_id] = new_role

        if role_map:
            # SQLite 不支持 IN 的 tuple 参数，构造占位符
            placeholders = ",".join(["%s"] * len(role_map))
            datasets = fetch_all(
                f"""
                SELECT dv.*, d.name AS dataset_name
                FROM dataset_versions dv
                JOIN datasets d ON d.id = dv.dataset_id
                WHERE dv.id IN ({placeholders})
                ORDER BY dv.id DESC
                """,
                tuple(role_map.keys()),
            )
            # 注入 role 信息
            for ds in datasets:
                ds["_ref_role"] = role_map.get(ds["id"], "")
        else:
            datasets = []

        runs = fetch_all(
            """
            SELECT tr.*, dv.version AS dataset_version_name, d.name AS dataset_name
            FROM training_runs tr
            LEFT JOIN dataset_versions dv ON dv.id = tr.dataset_version_id
            LEFT JOIN datasets d ON d.id = dv.dataset_id
            WHERE tr.project_id = %s
            ORDER BY tr.id DESC
            LIMIT 12
            """,
            (project_id,),
        )
        # 补充训练的 val dataset 信息
        for run in runs:
            if run.get("val_dataset_version_id"):
                vds = fetch_one(
                    "SELECT dv.version, d.name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s",
                    (run["val_dataset_version_id"],),
                )
                if vds:
                    run["_val_dataset_name"] = f"{vds['name']}/{vds['version']}"

        models = fetch_all(
            "SELECT * FROM model_versions WHERE project_id = %s AND training_run_id > 0 ORDER BY id DESC LIMIT 12",
            (project_id,),
        )
        evaluations = fetch_all(
            """
            SELECT er.*, mv.run_id AS model_run_id
            FROM evaluation_runs er
            LEFT JOIN model_versions mv ON mv.id = er.model_version_id
            WHERE er.project_id = %s
            ORDER BY er.id DESC
            LIMIT 12
            """,
            (project_id,),
        )
        sessions = fetch_all(
            "SELECT * FROM agent_sessions WHERE project_id = %s ORDER BY id DESC LIMIT 10",
            (project_id,),
        )
    else:
        project = None
        datasets = fetch_all(
            """
            SELECT dv.*, d.name AS dataset_name
            FROM dataset_versions dv
            JOIN datasets d ON d.id = dv.dataset_id
            ORDER BY dv.id DESC
            LIMIT 20
            """
        )
        runs = fetch_all("SELECT * FROM training_runs ORDER BY id DESC LIMIT 12")
        models = fetch_all("SELECT * FROM model_versions WHERE training_run_id > 0 ORDER BY id DESC LIMIT 12")
        evaluations = fetch_all("SELECT * FROM evaluation_runs ORDER BY id DESC LIMIT 12")
        sessions = fetch_all("SELECT * FROM agent_sessions ORDER BY id DESC LIMIT 10")

    versions = []
    for dataset in datasets:
        audit = {
            "missing_labels": dataset.get("missing_labels", 0),
            "orphan_labels": dataset.get("orphan_labels", 0),
            "invalid_bboxes": dataset.get("invalid_bboxes", 0),
            "empty_labels": dataset.get("empty_labels", 0),
        }
        review_progress = fetch_one(
            """
            SELECT
                COALESCE(SUM(CASE WHEN annotation_status IN ('unlabeled', 'ai_prelabel') THEN 1 ELSE 0 END), 0) AS pending_count,
                COALESCE(SUM(CASE WHEN annotation_status = 'reviewed' THEN 1 ELSE 0 END), 0) AS reviewed_count
            FROM image_items
            WHERE dataset_version_id = %s
            """,
            (dataset["id"],),
        )
        # split 分布
        splits = fetch_all(
            "SELECT split, COUNT(*) as cnt FROM image_items WHERE dataset_version_id=%s GROUP BY split",
            (dataset["id"],),
        )
        split_map = {s["split"]: s["cnt"] for s in (splits or [])}
        latest_export = fetch_one(
            """
            SELECT * FROM dataset_exports
            WHERE dataset_version_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (dataset["id"],),
        )
        versions.append(
            {
                "id": dataset["id"],
                "dataset_name": dataset.get("dataset_name", ""),
                "version": dataset.get("version", ""),
                "status": dataset.get("status", ""),
                "role": dataset.get("_ref_role") or dataset.get("role", ""),
                "dtype": dataset.get("dtype", ""),
                "image_count": dataset.get("image_count", 0),
                "class_count": dataset.get("class_count", 0),
                "split_breakdown": {
                    "train": split_map.get("train", 0),
                    "val": split_map.get("val", 0),
                    "test": split_map.get("test", 0),
                    "unlabeled": split_map.get("unlabeled", 0),
                },
                "pending_count": review_progress.get("pending_count", 0) if review_progress else 0,
                "reviewed_count": review_progress.get("reviewed_count", 0) if review_progress else 0,
                "audit": {
                    "missing_labels": audit.get("missing_labels", 0) if audit else 0,
                    "orphan_labels": audit.get("orphan_labels", 0) if audit else 0,
                    "invalid_bboxes": audit.get("invalid_bboxes", 0) if audit else 0,
                    "empty_labels": audit.get("empty_labels", 0) if audit else 0,
                },
                "latest_export": latest_export,
            }
        )

    run_details = []
    for run in runs:
        model = next((item for item in models if item.get("training_run_id") == run["id"]), None)
        report = {"summary": run.get("summary", "")} if run.get("report_path") else None

        # 训练集规模
        train_ds = next((v for v in versions if v["id"] == run.get("dataset_version_id")), None)
        train_ds_info = None
        if train_ds:
            train_ds_info = {"name": train_ds["dataset_name"], "image_count": train_ds["image_count"], "class_count": train_ds["class_count"], "dtype": train_ds["dtype"]}

        # 验证集规模
        val_ds = next((v for v in versions if v["id"] == run.get("val_dataset_version_id")), None)
        val_ds_info = None
        if val_ds:
            val_ds_info = {"name": val_ds["dataset_name"], "image_count": val_ds["image_count"], "class_count": val_ds["class_count"], "dtype": val_ds["dtype"]}
        elif run.get("_val_dataset_name"):
            val_ds_info = {"name": run["_val_dataset_name"], "image_count": None, "class_count": None}

        run_details.append(
            {
                "id": run["id"],
                "run_id": run["run_id"],
                "train_dataset": train_ds_info,
                "val_dataset": val_ds_info,
                "base_model": run.get("base_model", ""),
                "epochs": run.get("epochs", 0),
                "imgsz": run.get("imgsz", 0),
                "batch": run.get("batch", 0),
                "device": run.get("device", ""),
                "status": run.get("status", ""),
                "precision": model.get("precision") if model else None,
                "recall": model.get("recall") if model else None,
                "map50": model.get("map50") if model else None,
                "map50_95": model.get("map50_95") if model else None,
                "best_epoch": model.get("best_epoch") if model else None,
                "artifact_urls": _training_artifact_urls(model, run),
                "report_summary": report.get("summary") if report else "",
            }
        )

    model_details = []
    for model in models:
        model_details.append(
            {
                "id": model["id"],
                "run_id": model.get("run_id", ""),
                "dataset_name": model.get("dataset_name", ""),
                "dataset_version": model.get("dataset_version", ""),
                "precision": model.get("precision"),
                "recall": model.get("recall"),
                "map50": model.get("map50"),
                "map50_95": model.get("map50_95"),
                "best_epoch": model.get("best_epoch"),
                "is_candidate": bool(model.get("is_candidate")),
                "is_production": bool(model.get("is_production")),
                "best_weight_url": f"/api/models/{model['id']}/download/best",
                "last_weight_url": f"/api/models/{model['id']}/download/last",
            }
        )

    evaluation_details = []
    for evaluation in evaluations:
        samples = fetch_all(
            """
            SELECT * FROM evaluation_samples
            WHERE evaluation_run_id = %s
            ORDER BY id ASC
            LIMIT 12
            """,
            (evaluation["id"],),
        )
        # 获取评估关联的数据集信息
        eval_ds = fetch_one(
            "SELECT dv.version, dv.dtype, dv.image_count, d.name AS dataset_name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s",
            (evaluation.get("dataset_version_id"),),
        )
        eval_dataset_info = None
        if eval_ds:
            eval_splits = fetch_all(
                "SELECT split, COUNT(*) as cnt FROM image_items WHERE dataset_version_id=%s GROUP BY split",
                (evaluation["dataset_version_id"],),
            )
            eval_sm = {s["split"]: s["cnt"] for s in (eval_splits or [])}
            eval_dataset_info = {
                "name": f"{eval_ds.get('dataset_name','')}/{eval_ds.get('version','')}",
                "dtype": eval_ds.get("dtype",""),
                "image_count": eval_ds.get("image_count",0),
                "split_breakdown": {
                    "train": eval_sm.get("train",0),
                    "val": eval_sm.get("val",0),
                    "test": eval_sm.get("test",0),
                },
            }
        evaluation_details.append(
            {
                "id": evaluation["id"],
                "run_id": evaluation.get("run_id", ""),
                "status": evaluation.get("status", ""),
                "model_run_id": evaluation.get("model_run_id", ""),
                "precision": evaluation.get("precision"),
                "recall": evaluation.get("recall"),
                "map50": evaluation.get("map50"),
                "map50_95": evaluation.get("map50_95"),
                "report_summary": evaluation.get("summary", ""),
                "eval_dataset": eval_dataset_info,
                "samples": [
                    {
                        "image_path": item.get("image_path", ""),
                        "prediction_image_url": _file_url(item.get("prediction_image_path", "")),
                        "confidence_summary": item.get("confidence_summary", ""),
                        "match_summary": item.get("match_summary", ""),
                    }
                    for item in samples
                ],
            }
        )

    return {
        "project": project,
        "versions": versions,
        "runs": run_details,
        "models": model_details,
        "evaluations": evaluation_details,
        "latest_run": run_details[0] if run_details else None,
        "latest_model": model_details[0] if model_details else None,
        "latest_evaluation": evaluation_details[0] if evaluation_details else None,
        "sessions": sessions,
    }


def build_index(project_id: int | None = None) -> dict[str, Any]:
    """轻量索引 — 只有 ID 和名称，LLM 必须调工具拿具体数据。"""
    if project_id:
        project = fetch_one("SELECT id, name FROM projects WHERE id = %s", (project_id,))
        training_ids = fetch_all(
            "SELECT id, run_id, status FROM training_runs WHERE project_id = %s ORDER BY id DESC LIMIT 12",
            (project_id,),
        )
        eval_ids = fetch_all(
            "SELECT id, run_id, status FROM evaluation_runs WHERE project_id = %s ORDER BY id DESC LIMIT 12",
            (project_id,),
        )
        # 从训练/评估中收集引用的数据集 ID
        ref_rows = fetch_all(
            """
            SELECT DISTINCT dv_id FROM (
                SELECT dataset_version_id AS dv_id FROM training_runs WHERE project_id = %s AND dataset_version_id IS NOT NULL
                UNION SELECT val_dataset_version_id FROM training_runs WHERE project_id = %s AND val_dataset_version_id IS NOT NULL
                UNION SELECT dataset_version_id FROM evaluation_runs WHERE project_id = %s AND dataset_version_id IS NOT NULL
            ) refs
            """,
            (project_id, project_id, project_id),
        )
        dv_ids = [r["dv_id"] for r in (ref_rows or [])]
        if dv_ids:
            placeholders = ",".join(["%s"] * len(dv_ids))
            dataset_ids = fetch_all(
                f"SELECT dv.id, dv.version, dv.dtype, dv.image_count, d.name AS dataset_name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id IN ({placeholders}) ORDER BY dv.id DESC",
                tuple(dv_ids),
            )
        else:
            dataset_ids = []
        model_ids = fetch_all(
            "SELECT id, run_id, is_production, map50_95 FROM model_versions WHERE project_id = %s AND training_run_id > 0 ORDER BY id DESC LIMIT 12",
            (project_id,),
        )
    else:
        project = None
        training_ids = fetch_all("SELECT id, run_id, status FROM training_runs ORDER BY id DESC LIMIT 12")
        eval_ids = fetch_all("SELECT id, run_id, status FROM evaluation_runs ORDER BY id DESC LIMIT 12")
        dataset_ids = fetch_all("SELECT dv.id, dv.version, dv.dtype, dv.image_count, d.name AS dataset_name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id ORDER BY dv.id DESC LIMIT 20")
        model_ids = fetch_all("SELECT id, run_id, is_production, map50_95 FROM model_versions WHERE training_run_id > 0 ORDER BY id DESC LIMIT 12")

    return {
        "project": {"id": project["id"], "name": project["name"]} if project else None,
        "training_runs": [{"id": t["id"], "run_id": t["run_id"], "status": t["status"]} for t in (training_ids or [])],
        "evaluation_runs": [{"id": e["id"], "run_id": e["run_id"], "status": e["status"]} for e in (eval_ids or [])],
        "datasets": [{"id": d["id"], "name": f"{d['dataset_name']}/{d['version']}", "dtype": d.get("dtype",""), "image_count": d.get("image_count",0)} for d in (dataset_ids or [])],
        "models": [{"id": m["id"], "run_id": m["run_id"], "is_production": bool(m.get("is_production")), "map50_95_hint": round(m["map50_95"], 3) if m.get("map50_95") is not None else None} for m in (model_ids or [])],
    }


def _training_artifact_urls(model: dict | None, run: dict) -> dict[str, str]:
    root = Path(model["registry_path"]) if model and model.get("registry_path") else Path(run["run_path"])
    names = [
        "results.png",
        "confusion_matrix.png",
        "PR_curve.png",
        "F1_curve.png",
        "train_batch0.jpg",
        "val_batch0_pred.jpg",
        "metrics.json",
    ]
    result = {}
    for name in names:
        path = root / name
        if path.exists():
            result[name] = _file_url(str(path))
    return result


def _file_url(path_value: str) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    try:
        resolved = path.resolve()
        if resolved.is_relative_to(DATASETS_DIR.resolve()):
            return "/images/" + resolved.relative_to(DATASETS_DIR.resolve()).as_posix()
        if resolved.is_relative_to(RUNS_DIR.resolve()):
            return "/runs/" + resolved.relative_to(RUNS_DIR.resolve()).as_posix()
        if resolved.is_relative_to(MODEL_REGISTRY_DIR.resolve()):
            return "/model_registry/" + resolved.relative_to(MODEL_REGISTRY_DIR.resolve()).as_posix()
    except Exception:
        return ""
    return ""
