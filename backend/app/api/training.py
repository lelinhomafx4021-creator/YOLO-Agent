import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.agents.training_analyst_agent import generate_training_report
from app.core.config import RUNS_DIR
from app.core.database import db, fetch_all, fetch_one
from app.core.path_utils import file_to_url
from app.schemas.common import TrainingCreate
from app.training.trainer import create_training_run, start_training_background


router = APIRouter(prefix="/api/training-runs", tags=["training"])

ARTIFACT_NAMES = [
    "results.csv",
    "results.png",
    "confusion_matrix.png",
    "PR_curve.png",
    "F1_curve.png",
    "args.yaml",
    "metrics.json",
    "dataset_manifest.json",
    "labels.jpg",
    "train_batch0.jpg",
    "val_batch0_pred.jpg",
    "ai_training_report.md",
    "weights/best.pt",
    "weights/last.pt",
]


@router.get("/{training_run_id}/log/stream")
async def stream_training_log(training_run_id: int, request: Request):
    """SSE 实时推送训练日志。"""
    row = fetch_one("SELECT log_path, status FROM training_runs WHERE id = %s", (training_run_id,))
    if not row:
        raise HTTPException(status_code=404, detail="training run not found")

    log_path = Path(row["log_path"])

    async def generate():
        last_size = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                if log_path.exists():
                    size = log_path.stat().st_size
                    if size > last_size:
                        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last_size)
                            new_text = f.read(size - last_size)
                            last_size = size
                            for line in new_text.splitlines():
                                if line.strip():
                                    yield f"data: {line}\n\n"
                # 检查训练是否结束
                current = fetch_one("SELECT status FROM training_runs WHERE id = %s", (training_run_id,))
                if current and current["status"] in ("completed", "failed"):
                    yield f"event: done\ndata: {current['status']}\n\n"
                    break
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("")
def list_training_runs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> dict:
    total = fetch_one("SELECT COUNT(*) AS c FROM training_runs")
    rows = fetch_all(
        "SELECT * FROM training_runs ORDER BY id DESC LIMIT %s OFFSET %s",
        (page_size, (page - 1) * page_size),
    )
    return {"items": rows, "total": total["c"] if total else 0, "page": page, "page_size": page_size}


@router.post("")
def create_training_run_api(payload: TrainingCreate) -> dict:
    try:
        run = create_training_run(**payload.model_dump())
        start_training_background(run["id"])
        return run
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/dry-run")
def create_training_dry_run(payload: TrainingCreate) -> dict:
    try:
        return create_training_run(**payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{training_run_id}")
def get_training_run(training_run_id: int) -> dict:
    row = fetch_one("SELECT * FROM training_runs WHERE id = %s", (training_run_id,))
    if not row:
        raise HTTPException(status_code=404, detail="training run not found")
    return row


@router.get("/{training_run_id}/detail")
def get_training_run_detail(training_run_id: int) -> dict:
    run = fetch_one("SELECT * FROM training_runs WHERE id = %s", (training_run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="training run not found")

    dataset_version = fetch_one(
        """
        SELECT dv.*, d.name AS dataset_name
        FROM dataset_versions dv
        JOIN datasets d ON d.id = dv.dataset_id
        WHERE dv.id = %s
        """,
        (run["dataset_version_id"],),
    )
    model = fetch_one("SELECT * FROM model_versions WHERE training_run_id = %s", (training_run_id,))
    report = None
    if run.get("report_path"):
        report = {"training_run_id": training_run_id, "report_path": run["report_path"], "summary": run.get("summary", "")}
    metrics = fetch_all(
        "SELECT * FROM training_metrics WHERE training_run_id = %s ORDER BY epoch ASC",
        (training_run_id,),
    )

    artifact_root = Path(model["registry_path"]) if model and model.get("registry_path") else Path(run["run_path"])
    artifacts = []
    for name in ARTIFACT_NAMES:
        file_path = artifact_root / name
        if not file_path.exists():
            continue
        artifacts.append(
            {
                "name": name,
                "file_name": file_path.name,
                "path": str(file_path),
                "url": _artifact_url(file_path),
            }
        )

    report_content = ""
    if report and report.get("report_path"):
        report_path = Path(report["report_path"])
        if report_path.exists():
            report_content = report_path.read_text(encoding="utf-8")

    return {
        "run": run,
        "dataset_version": dataset_version,
        "model": model,
        "metrics": metrics,
        "artifacts": artifacts,
        "report": report,
        "report_content": report_content,
    }


@router.get("/{training_run_id}/log")
def get_training_log(training_run_id: int) -> dict:
    row = fetch_one("SELECT * FROM training_runs WHERE id = %s", (training_run_id,))
    if not row:
        raise HTTPException(status_code=404, detail="training run not found")
    path = Path(row["log_path"])
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"training_run_id": training_run_id, "log": text}


@router.get("/{training_run_id}/progress")
def get_training_progress(training_run_id: int) -> dict:
    run = fetch_one("SELECT * FROM training_runs WHERE id = %s", (training_run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="training run not found")

    metrics = fetch_all(
        "SELECT * FROM training_metrics WHERE training_run_id = %s ORDER BY epoch ASC",
        (training_run_id,),
    )

    # 训练中 training_metrics 表还没数据，直接从 results.csv 读实时指标
    live_metrics = []
    if not metrics and run["status"] == "running":
        try:
            import csv
            csv_path = Path(run["run_path"]) / "results.csv"
            if csv_path.exists():
                with csv_path.open("r") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        epoch = int(float(row.get("epoch", "0").strip()))
                        live_metrics.append({
                            "epoch": epoch,
                            "train_box_loss": _parse_float(row.get("train/box_loss")),
                            "train_cls_loss": _parse_float(row.get("train/cls_loss")),
                            "train_dfl_loss": _parse_float(row.get("train/dfl_loss")),
                            "precision": _parse_float(row.get("metrics/precision(B)")),
                            "recall": _parse_float(row.get("metrics/recall(B)")),
                            "map50": _parse_float(row.get("metrics/mAP50(B)")),
                            "map50_95": _parse_float(row.get("metrics/mAP50-95(B)")),
                        })
                metrics = live_metrics
        except Exception:
            pass

    tail = ""
    path = Path(run["log_path"])
    if path.exists():
        try:
            with path.open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 4096))
                raw = f.read().decode("utf-8", errors="replace")
            lines = raw.splitlines()
            tail = "\n".join(lines[-20:])
        except Exception:
            tail = ""

    return {
        "run_id": run["run_id"],
        "status": run["status"],
        "epochs_total": run["epochs"],
        "epochs_completed": len(metrics),
        "metrics": metrics,
        "latest_log_tail": tail,
    }


def _parse_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(str(val).strip())
    except (ValueError, TypeError):
        return None


@router.delete("/{training_run_id}")
def delete_training_run(training_run_id: int) -> dict:
    run = fetch_one("SELECT * FROM training_runs WHERE id = %s", (training_run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="training run not found")
    with db() as cur:
        cur.execute("DELETE FROM training_metrics WHERE training_run_id = %s", (training_run_id,))
        model = fetch_one("SELECT id FROM model_versions WHERE training_run_id = %s", (training_run_id,))
        if model:
            cur.execute("DELETE FROM evaluation_samples WHERE evaluation_run_id IN (SELECT id FROM evaluation_runs WHERE model_version_id = %s)", (model["id"],))
            cur.execute("DELETE FROM evaluation_runs WHERE model_version_id = %s", (model["id"],))
            cur.execute("DELETE FROM model_versions WHERE id = %s", (model["id"],))
        cur.execute("DELETE FROM training_runs WHERE id = %s", (training_run_id,))
    return {"message": "deleted"}


@router.put("/{training_run_id}")
def update_training_run(training_run_id: int, payload: dict) -> dict:
    run = fetch_one("SELECT * FROM training_runs WHERE id = %s", (training_run_id,))
    if not run:
        raise HTTPException(status_code=404, detail="training run not found")
    allowed = {"epochs", "imgsz", "batch", "device", "base_model", "run_name", "notes", "optimizer", "lr0"}
    updates = {k: v for k, v in payload.items() if k in allowed and v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="no valid fields to update")
    sets = ", ".join(f"{k} = %s" for k in updates)
    vals = list(updates.values()) + [training_run_id]
    with db() as cur:
        cur.execute(f"UPDATE training_runs SET {sets} WHERE id = %s", vals)
        # 同步备注到关联模型
        if "notes" in updates:
            cur.execute(
                "UPDATE model_versions SET notes = %s WHERE training_run_id = %s",
                (updates["notes"], training_run_id),
            )
        return dict(cur.execute("SELECT * FROM training_runs WHERE id = %s", (training_run_id,)).fetchone())


def _artifact_url(file_path: Path) -> str:
    return file_to_url(file_path)


# ---- AI 报告 ----

@router.get("/{training_run_id}/ai-report")
def get_ai_report(training_run_id: int) -> dict:
    run = fetch_one("SELECT report_path, summary FROM training_runs WHERE id = %s", (training_run_id,))
    if not run or not run.get("report_path"):
        raise HTTPException(status_code=404, detail="ai report not found")
    path = Path(run["report_path"])
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    return {"record": {"training_run_id": training_run_id, "report_path": run["report_path"], "summary": run.get("summary", "")}, "content": content}


@router.post("/{training_run_id}/ai-report")
def regenerate_ai_report(training_run_id: int) -> dict:
    try:
        return generate_training_report(training_run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
