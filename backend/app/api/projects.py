from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import DATASETS_DIR, MODEL_REGISTRY_DIR, RUNS_DIR
from app.core.database import db, fetch_all, fetch_one, utc_now
from app.core.path_utils import file_to_url
from app.presentation import decorate_evaluation_run, decorate_model, decorate_training_run
from app.schemas.common import EvaluationCreate, ProjectCreate, ProjectDatasetBind, TrainingCreate
from app.training.evaluator import create_evaluation_run, start_evaluation_background
from app.training.trainer import create_training_run, start_training_background


router = APIRouter(prefix="/api/projects", tags=["projects"])

ALLOWED_ROLES = {"train", "val", "test", "supplement", "unlabeled"}


def _safe_model_display_name(row: dict) -> str:
    raw_name = str(row.get("model_name") or row.get("run_id") or "").replace("\\", "/")
    if raw_name and "/" not in raw_name:
        return raw_name
    dataset = row.get("dataset_name") or "model"
    raw_tail = Path(raw_name).name if raw_name else ""
    if raw_tail:
        tail = raw_tail.replace(".pt", "").replace(".onnx", "").replace(".engine", "").replace(".yaml", "")
        if tail and tail.lower() not in {"model", "best", "last"}:
            return f"{dataset}_{tail}"
    base = Path(str(row.get("base_model") or "model")).name
    base = base.replace(".pt", "").replace(".yaml", "") or "model"
    return f"{dataset}_{base}"


def _with_display_model_name(row: dict) -> dict:
    item = dict(row)
    name = _safe_model_display_name(item)
    fmt = str(item.get("model_format") or "").upper()
    if fmt and fmt != "YOLO" and f"[{fmt}]" not in name:
        name = f"{name} [{fmt}]"
    item["display_model_name"] = name
    return item


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80, description="项目名称")
    description: str | None = Field(default=None, description="项目说明")
    workspace_name: str | None = Field(default=None, description="绑定的工作台名称")


@router.get("")
def list_projects() -> list[dict]:
    projects = fetch_all("SELECT * FROM projects ORDER BY id DESC")
    for project in projects:
        project.update(_project_counts(project["id"]))
    return projects


@router.post("")
def create_project(payload: ProjectCreate) -> dict:
    now = utc_now()
    try:
        with db() as cur:
            cur.execute(
                """
                INSERT INTO projects(name, description, task_type, workspace_name, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'active', %s, %s) RETURNING *
                """,
                (payload.name, payload.description, payload.task_type, payload.workspace_name, now, now),
            )
            return dict(cur.fetchone())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{project_id}")
def update_project(project_id: int, payload: ProjectUpdate) -> dict:
    _require_project(project_id)
    now = utc_now()

    updates = {}
    if payload.name is not None:
        updates["name"] = payload.name
    if payload.description is not None:
        updates["description"] = payload.description
    if payload.workspace_name is not None:
        updates["workspace_name"] = payload.workspace_name

    if not updates:
        return fetch_one("SELECT * FROM projects WHERE id = %s", (project_id,))

    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [project_id]

    with db() as cur:
        cur.execute(
            f"UPDATE projects SET {set_clause} WHERE id = %s RETURNING *",
            values,
        )
        return dict(cur.fetchone())


@router.get("/{project_id}")
def get_project(project_id: int) -> dict:
    project = _require_project(project_id)
    project["counts"] = _project_counts(project_id)
    project["datasets"] = _project_datasets(project_id)
    training_runs = fetch_all(
        """
        SELECT tr.*, dv.version AS dataset_version_name, d.name AS dataset_name,
               mv.model_name, mv.id AS model_id, mv.notes AS model_notes,
               mv.map50, mv.map50_95, mv.is_production,
               mv.run_id AS model_run_id, mv.base_model AS model_base_model,
               mv.model_format AS model_format
        FROM training_runs tr
        JOIN dataset_versions dv ON dv.id = tr.dataset_version_id
        JOIN datasets d ON d.id = dv.dataset_id
        LEFT JOIN model_versions mv ON mv.training_run_id = tr.id
        WHERE tr.project_id = %s
        ORDER BY tr.id DESC
        LIMIT 50
        """,
        (project_id,),
    )
    project["training_runs"] = [decorate_training_run(row) for row in training_runs]
    project["models"] = fetch_all(
        """
        SELECT mv.*, tr.status AS training_status, tr.display_name AS source_training_display_name, p.name AS project_name
        FROM model_versions mv
        LEFT JOIN training_runs tr ON tr.id = mv.training_run_id
        LEFT JOIN projects p ON p.id = mv.project_id
        WHERE mv.project_id = %s
        ORDER BY mv.id DESC
        LIMIT 50
        """,
        (project_id,),
    )
    project["models"] = [decorate_model(row) for row in project["models"]]
    evaluation_runs = fetch_all(
        """
        SELECT er.*, mv.run_id AS model_run_id, mv.model_name AS model_name,
               mv.dataset_name AS model_dataset_name, mv.base_model AS model_base_model,
               mv.model_format AS model_format, tr.display_name AS source_training_display_name,
               mv.training_run_id,
               d.name AS dataset_name, dv.version AS dataset_version_name
        FROM evaluation_runs er
        LEFT JOIN model_versions mv ON mv.id = er.model_version_id
        LEFT JOIN training_runs tr ON tr.id = mv.training_run_id
        LEFT JOIN dataset_versions dv ON dv.id = er.dataset_version_id
        LEFT JOIN datasets d ON d.id = dv.dataset_id
        WHERE er.project_id = %s
        ORDER BY er.id DESC
        LIMIT 50
        """,
        (project_id,),
    )
    project["evaluation_runs"] = [decorate_evaluation_run(row) for row in evaluation_runs]
    project["latest_agent_session"] = fetch_one(
        "SELECT * FROM agent_sessions WHERE project_id = %s ORDER BY id DESC LIMIT 1",
        (project_id,),
    )
    return project


@router.get("/{project_id}/datasets")
def list_project_datasets(project_id: int) -> list[dict]:
    _require_project(project_id)
    return _project_datasets(project_id)


@router.post("/{project_id}/datasets")
def bind_project_dataset(project_id: int, payload: ProjectDatasetBind) -> dict:
    _require_project(project_id)
    version = fetch_one(
        "SELECT dv.*, d.name AS dataset_name FROM dataset_versions dv "
        "JOIN datasets d ON d.id = dv.dataset_id WHERE dv.id = %s",
        (payload.dataset_version_id,),
    )
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")

    # 自动推断 role
    role = payload.role
    if not role:
        role = _infer_role(version.get("dataset_name", ""))
    if role not in ALLOWED_ROLES:
        raise HTTPException(status_code=400, detail=f"invalid role: {role}")

    # 训练/验证/测试集必须有标注文件
    if role in ("train", "val", "test") and version.get("label_file_count", 0) == 0:
        raise HTTPException(
            status_code=400,
            detail=f"该数据集没有标注文件（label_file_count=0），无法作为{'训练' if role == 'train' else '验证' if role == 'val' else '测试'}集使用。请使用有 YOLO 标注的数据集，或先完成标注后导出。",
        )

    if role == "unlabeled" and version.get("status") != "annotation":
        raise HTTPException(status_code=400, detail="待标注图集只能绑定 annotation 类型数据")
    if role in {"train", "val", "test", "supplement"} and version.get("status") == "annotation":
        latest_export = fetch_one(
            "SELECT * FROM dataset_exports WHERE dataset_version_id = %s ORDER BY id DESC LIMIT 1",
            (payload.dataset_version_id,),
        )
        if not latest_export:
            raise HTTPException(status_code=400, detail="待标注图集需要先导出为 YOLO train/val/test 后再绑定训练或测试用途")
    if role in {"train", "val", "test"}:
        with db() as cur:
            cur.execute(
                "UPDATE project_dataset_bindings SET is_active = 0 WHERE project_id = %s AND role = %s AND is_active = 1",
                (project_id, role),
            )
    with db() as cur:
        cur.execute(
            """
            INSERT INTO project_dataset_bindings(
                project_id, dataset_version_id, role, source_split, note, is_active, created_at
            ) VALUES (%s, %s, %s, %s, %s, 1, %s) RETURNING *
            """,
            (project_id, payload.dataset_version_id, role, payload.source_split, payload.note, utc_now()),
        )
        bound = dict(cur.fetchone())

    # 自动关联同源的 train/val/test 数据集
    _auto_bind_splits(project_id, version)

    return bound


@router.delete("/{project_id}/datasets/{binding_id}")
def unbind_project_dataset(project_id: int, binding_id: int) -> dict:
    """解绑数据集。"""
    _require_project(project_id)
    binding = fetch_one(
        "SELECT * FROM project_dataset_bindings WHERE id = %s AND project_id = %s",
        (binding_id, project_id),
    )
    if not binding:
        raise HTTPException(status_code=404, detail="binding not found")
    with db() as cur:
        cur.execute("UPDATE project_dataset_bindings SET is_active = 0 WHERE id = %s", (binding_id,))
    return {"message": "unbound", "binding_id": binding_id}


def _infer_role(dataset_name: str) -> str:
    """从数据集名称推断用途。"""
    if dataset_name.endswith("_train"):
        return "train"
    if dataset_name.endswith("_val"):
        return "val"
    if dataset_name.endswith("_test"):
        return "test"
    return "supplement"


def _auto_bind_splits(project_id: int, bound_version: dict) -> None:
    """绑 train/val/test 时，自动查找同源的其他 split 并绑定。"""
    ds_name = bound_version.get("dataset_name", "")
    # 从名称推断基础名：helmet_fixed_train → helmet_fixed
    suffix = None
    for s in ("_train", "_val", "_test"):
        if ds_name.endswith(s):
            suffix = s
            break
    if not suffix:
        return

    base_name = ds_name[: -len(suffix)]
    splits_needed = {"_train": "train", "_val": "val", "_test": "test"}
    del splits_needed[suffix]  # 已经绑了的跳过

    for split_suffix, role in splits_needed.items():
        # 检查是否已经绑了这个 role
        existing = fetch_one(
            "SELECT id FROM project_dataset_bindings WHERE project_id = %s AND role = %s AND is_active = 1",
            (project_id, role),
        )
        if existing:
            continue

        # 找同名数据集的最新版本
        target_name = base_name + split_suffix
        target_ds = fetch_one("SELECT id FROM datasets WHERE name = %s", (target_name,))
        if not target_ds:
            continue
        target_ver = fetch_one(
            "SELECT id FROM dataset_versions WHERE dataset_id = %s ORDER BY id DESC LIMIT 1",
            (target_ds["id"],),
        )
        if not target_ver:
            continue

        with db() as cur:
            cur.execute(
                """
                INSERT INTO project_dataset_bindings(
                    project_id, dataset_version_id, role, source_split, note, is_active, created_at
                ) VALUES (%s, %s, %s, '', '自动关联', 1, %s)
                """,
                (project_id, target_ver["id"], role, utc_now()),
            )


@router.post("/{project_id}/training-runs")
def create_project_training_run(project_id: int, payload: TrainingCreate) -> dict:
    _require_project(project_id)
    try:
        data = payload.model_dump()
        data["project_id"] = project_id
        run = create_training_run(**data)
        start_training_background(run["id"])
        return run
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{project_id}/training-runs")
def list_project_training_runs(project_id: int) -> list[dict]:
    _require_project(project_id)
    return fetch_all(
        """
        SELECT tr.*, dv.version AS dataset_version_name, d.name AS dataset_name
        FROM training_runs tr
        JOIN dataset_versions dv ON dv.id = tr.dataset_version_id
        JOIN datasets d ON d.id = dv.dataset_id
        WHERE tr.project_id = %s
        ORDER BY tr.id DESC
        """,
        (project_id,),
    )


@router.post("/{project_id}/evaluation-runs")
def create_project_evaluation_run(project_id: int, payload: EvaluationCreate) -> dict:
    _require_project(project_id)
    model = fetch_one("SELECT * FROM model_versions WHERE id = %s", (payload.model_version_id,))
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (payload.dataset_version_id,))
    if not model:
        raise HTTPException(status_code=404, detail="model version not found")
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    run = create_evaluation_run(
        project_id=project_id,
        model_version_id=payload.model_version_id,
        dataset_version_id=payload.dataset_version_id,
        binding_id=payload.binding_id,
        source_split=payload.source_split,
        imgsz=payload.imgsz,
        batch=payload.batch,
        device=payload.device,
    )
    start_evaluation_background(run["id"])
    return run


@router.get("/{project_id}/evaluation-runs")
def list_project_evaluation_runs(project_id: int) -> list[dict]:
    _require_project(project_id)
    return fetch_all(
        """
        SELECT er.*, mv.run_id AS model_run_id, d.name AS dataset_name, dv.version AS dataset_version_name
        FROM evaluation_runs er
        LEFT JOIN model_versions mv ON mv.id = er.model_version_id
        LEFT JOIN dataset_versions dv ON dv.id = er.dataset_version_id
        LEFT JOIN datasets d ON d.id = dv.dataset_id
        WHERE er.project_id = %s
        ORDER BY er.id DESC
        """,
        (project_id,),
    )


@router.get("/evaluation-runs/{evaluation_id}")
def get_evaluation_run(evaluation_id: int) -> dict:
    run = fetch_one(
        """
        SELECT er.*, mv.run_id AS model_run_id, mv.model_name AS model_name, mv.best_pt_path, mv.last_pt_path,
               mv.training_run_id, tr.display_name AS source_training_display_name,
               mv.dataset_name AS model_dataset_name, mv.dataset_version AS model_dataset_version,
               mv.base_model AS model_base_model, mv.model_format AS model_format,
               d.name AS dataset_name, dv.version AS dataset_version_name
        FROM evaluation_runs er
        LEFT JOIN model_versions mv ON mv.id = er.model_version_id
        LEFT JOIN training_runs tr ON tr.id = mv.training_run_id
        LEFT JOIN dataset_versions dv ON dv.id = er.dataset_version_id
        LEFT JOIN datasets d ON d.id = dv.dataset_id
        WHERE er.id = %s
        """,
        (evaluation_id,),
    )
    if not run:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    run = decorate_evaluation_run(run)

    report_artifacts = []
    run_path = Path(run["run_path"])
    if run_path.exists():
        for file_path in sorted(run_path.rglob("*")):
            if not file_path.is_file():
                continue
            report_artifacts.append(
                {
                    "name": file_path.name,
                    "relative_path": file_path.relative_to(run_path).as_posix(),
                    "url": _file_url(str(file_path)),
                }
            )

    run["artifacts"] = report_artifacts

    # 附加 AI 报告内容
    report_content = ""
    if run.get("report_path"):
        rp = Path(run["report_path"])
        if rp.exists():
            report_content = rp.read_text(encoding="utf-8")

    run["report_content"] = report_content
    return run


@router.get("/evaluation-runs/{evaluation_id}/samples")
def list_evaluation_samples(
    evaluation_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(48, ge=1, le=200),
) -> dict:
    run = fetch_one("SELECT * FROM evaluation_runs WHERE id = %s", (evaluation_id,))
    if not run:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    total_row = fetch_one(
        "SELECT COUNT(*) AS c FROM evaluation_samples WHERE evaluation_run_id = %s",
        (evaluation_id,),
    )
    offset = (page - 1) * page_size
    rows = fetch_all(
        """
        SELECT * FROM evaluation_samples
        WHERE evaluation_run_id = %s
        ORDER BY id ASC LIMIT %s OFFSET %s
        """,
        (evaluation_id, page_size, offset),
    )
    for row in rows:
        row["image_url"] = _file_url(row.get("image_path", ""))
        row["prediction_image_url"] = _file_url(row.get("prediction_image_path", ""))
    return {"items": rows, "total": total_row["c"] if total_row else 0, "page": page, "page_size": page_size}


@router.delete("/evaluation-runs/{evaluation_id}")
def delete_evaluation_run(evaluation_id: int) -> dict:
    run = fetch_one("SELECT * FROM evaluation_runs WHERE id = %s", (evaluation_id,))
    if not run:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    with db() as cur:
        cur.execute("DELETE FROM evaluation_samples WHERE evaluation_run_id = %s", (evaluation_id,))
        cur.execute("DELETE FROM evaluation_runs WHERE id = %s", (evaluation_id,))
    return {"message": "deleted"}


@router.get("/evaluation-runs/{evaluation_id}/log")
def get_evaluation_log(evaluation_id: int) -> dict:
    """获取评估运行的日志。"""
    run = fetch_one("SELECT * FROM evaluation_runs WHERE id = %s", (evaluation_id,))
    if not run:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    log_path = Path(run["log_path"]) if run.get("log_path") else None
    log_text = ""
    if log_path and log_path.exists():
        log_text = log_path.read_text(encoding="utf-8")
    return {"log": log_text}


@router.get("/evaluation-runs/{evaluation_id}/progress")
def get_evaluation_progress(evaluation_id: int) -> dict:
    """获取评估运行的进度（状态 + 日志尾部）。"""
    run = fetch_one("SELECT * FROM evaluation_runs WHERE id = %s", (evaluation_id,))
    if not run:
        raise HTTPException(status_code=404, detail="evaluation run not found")
    tail = ""
    log_path = Path(run["log_path"]) if run.get("log_path") else None
    if log_path and log_path.exists():
        try:
            with log_path.open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 4096))
                raw = f.read().decode("utf-8", errors="replace")
            tail = "\n".join(raw.splitlines()[-30:])
        except Exception:
            tail = ""
    return {
        "status": run["status"],
        "log_tail": tail,
        "precision": run.get("precision"),
        "recall": run.get("recall"),
        "map50": run.get("map50"),
        "map50_95": run.get("map50_95"),
    }


@router.get("/evaluation-runs/{evaluation_id}/ai-report")
def get_evaluation_ai_report(evaluation_id: int) -> dict:
    """获取评估运行的 AI 分析报告。"""
    run = fetch_one(
        "SELECT report_path, summary FROM evaluation_runs WHERE id = %s",
        (evaluation_id,),
    )
    if not run or not run.get("report_path"):
        raise HTTPException(status_code=404, detail="ai report not found")
    path = Path(run["report_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="report file not found")
    content = path.read_text(encoding="utf-8")
    return {
        "record": {
            "evaluation_run_id": evaluation_id,
            "report_path": run["report_path"],
            "summary": run.get("summary", ""),
        },
        "content": content,
    }


@router.post("/evaluation-runs/{evaluation_id}/ai-report")
def regenerate_evaluation_ai_report(evaluation_id: int) -> dict:
    """重新生成评估运行的 AI 分析报告。"""
    from app.agents.evaluation_analyst_agent import generate_evaluation_report
    try:
        return generate_evaluation_report(evaluation_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{project_id}")
def delete_project(project_id: int) -> dict:
    _require_project(project_id)
    with db() as cur:
        # Child tables referenced by evaluation_runs
        cur.execute(
            "DELETE FROM evaluation_samples WHERE evaluation_run_id IN (SELECT id FROM evaluation_runs WHERE project_id = %s)",
            (project_id,),
        )
        # Child tables referenced by training_runs
        cur.execute(
            "DELETE FROM training_metrics WHERE training_run_id IN (SELECT id FROM training_runs WHERE project_id = %s)",
            (project_id,),
        )
        # Child tables referenced by agent_sessions
        cur.execute(
            "DELETE FROM agent_messages WHERE session_id IN (SELECT id FROM agent_sessions WHERE project_id = %s)",
            (project_id,),
        )
        # Direct project children
        cur.execute("DELETE FROM evaluation_runs WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM training_runs WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM model_versions WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM agent_sessions WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM iteration_plans WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM project_dataset_bindings WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM projects WHERE id = %s", (project_id,))
    return {"message": "项目已删除"}


def _require_project(project_id: int) -> dict:
    project = fetch_one("SELECT * FROM projects WHERE id = %s", (project_id,))
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


def _project_counts(project_id: int) -> dict:
    row = fetch_one(
        """
        SELECT
            (SELECT COUNT(*) FROM project_dataset_bindings WHERE project_id = %s AND is_active = 1) AS dataset_count,
            (SELECT COUNT(*) FROM training_runs WHERE project_id = %s) AS training_count,
            (SELECT COUNT(*) FROM evaluation_runs WHERE project_id = %s) AS evaluation_count,
            (SELECT COUNT(*) FROM model_versions WHERE project_id = %s) AS model_count,
            (SELECT MAX(map50) FROM model_versions WHERE project_id = %s) AS best_map50
        """,
        (project_id, project_id, project_id, project_id, project_id),
    )
    return row or {"dataset_count": 0, "training_count": 0, "evaluation_count": 0, "model_count": 0, "best_map50": None}


def _project_datasets(project_id: int) -> list[dict]:
    return fetch_all(
        """
        SELECT b.*, dv.version, dv.root_path, dv.data_yaml_path, dv.image_count,
               dv.label_file_count, dv.instance_count, dv.class_count, dv.status,
               d.name AS dataset_name, d.description AS dataset_description,
               (SELECT de.id FROM dataset_exports de WHERE de.dataset_version_id = b.dataset_version_id ORDER BY de.id DESC LIMIT 1) AS latest_export_id
        FROM project_dataset_bindings b
        JOIN dataset_versions dv ON dv.id = b.dataset_version_id
        JOIN datasets d ON d.id = dv.dataset_id
        WHERE b.project_id = %s AND b.is_active = 1
        ORDER BY b.id DESC
        """,
        (project_id,),
    )


def _file_url(path_value: str) -> str:
    if not path_value:
        return ""
    return file_to_url(path_value)
