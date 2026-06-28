from fastapi import APIRouter

from app.core.database import fetch_all

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("/jobs")
def list_job_notifications() -> list[dict]:
    jobs: list[dict] = []

    training_rows = fetch_all(
        """
        SELECT tr.id, tr.run_id, tr.status, tr.created_at, tr.started_at, tr.finished_at,
               tr.error, tr.project_id, tr.dataset_name, mv.map50, mv.map50_95
        FROM training_runs tr
        LEFT JOIN model_versions mv ON mv.training_run_id = tr.id
        ORDER BY tr.id DESC
        LIMIT 80
        """
    )
    for row in training_rows:
        jobs.append({
            "key": f"training:{row['id']}",
            "kind": "training",
            "id": row["id"],
            "name": row.get("run_id") or f"training-{row['id']}",
            "status": row.get("status") or "",
            "project_id": row.get("project_id"),
            "created_at": row.get("created_at"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "error": row.get("error") or "",
            "summary": _training_summary(row),
            "url": f"/training/{row['id']}",
        })

    evaluation_rows = fetch_all(
        """
        SELECT er.id, er.run_id, er.status, er.created_at, er.started_at, er.finished_at,
               er.error, er.project_id, er.map50, er.map50_95,
               d.name AS dataset_name, mv.model_name, mv.run_id AS model_run_id
        FROM evaluation_runs er
        LEFT JOIN dataset_versions dv ON dv.id = er.dataset_version_id
        LEFT JOIN datasets d ON d.id = dv.dataset_id
        LEFT JOIN model_versions mv ON mv.id = er.model_version_id
        ORDER BY er.id DESC
        LIMIT 80
        """
    )
    for row in evaluation_rows:
        jobs.append({
            "key": f"evaluation:{row['id']}",
            "kind": "evaluation",
            "id": row["id"],
            "name": row.get("run_id") or f"evaluation-{row['id']}",
            "status": row.get("status") or "",
            "project_id": row.get("project_id"),
            "created_at": row.get("created_at"),
            "started_at": row.get("started_at"),
            "finished_at": row.get("finished_at"),
            "error": row.get("error") or "",
            "summary": _evaluation_summary(row),
            "url": f"/evaluations/{row['id']}",
        })

    export_rows = fetch_all(
        """
        SELECT id, run_id, model_name, model_format, dataset_name, created_at, notes
        FROM model_versions
        WHERE training_run_id <= 0 AND run_id LIKE 'export_%'
        ORDER BY id DESC
        LIMIT 50
        """
    )
    for row in export_rows:
        name = row.get("model_name") or row.get("run_id") or f"model-{row['id']}"
        fmt = str(row.get("model_format") or "").upper() or "MODEL"
        jobs.append({
            "key": f"model_export:{row['id']}",
            "kind": "model_export",
            "id": row["id"],
            "name": name,
            "status": "completed",
            "created_at": row.get("created_at"),
            "finished_at": row.get("created_at"),
            "summary": f"{fmt} 模型已注册",
            "url": "/registry",
        })

    return jobs


def _fmt_metric(value) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value):.3f}"
    except Exception:
        return ""


def _training_summary(row: dict) -> str:
    score = _fmt_metric(row.get("map50"))
    dataset = row.get("dataset_name") or ""
    if score:
        return f"{dataset} mAP50 {score}".strip()
    return dataset or "训练任务状态已更新"


def _evaluation_summary(row: dict) -> str:
    score = _fmt_metric(row.get("map50_95"))
    dataset = row.get("dataset_name") or ""
    if score:
        return f"{dataset} mAP50-95 {score}".strip()
    return dataset or "验证任务状态已更新"
