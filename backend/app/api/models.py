"""模型仓库 API — 列表、详情、导出、导入、晋升、删除。"""

import shutil
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.config import MODEL_REGISTRY_DIR, RUNS_DIR
from app.core.database import db, fetch_all, fetch_one, utc_now
from app.core.log_capture import append_log
from app.core.path_utils import delete_model_cascade, file_to_url
from app.presentation import decorate_model
from app.registry.model_registry import promote_model

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
def list_models(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict:
    total = fetch_one("SELECT COUNT(*) AS c FROM model_versions")
    rows = fetch_all(
        """
        SELECT mv.*, p.name AS project_name, tr.display_name AS source_training_display_name
        FROM model_versions mv
        LEFT JOIN projects p ON p.id = mv.project_id
        LEFT JOIN training_runs tr ON tr.id = mv.training_run_id
        ORDER BY mv.id DESC LIMIT %s OFFSET %s
        """,
        (page_size, (page-1)*page_size),
    )
    rows = [decorate_model(row) for row in rows]
    return {"items": rows, "total": total["c"] if total else 0, "page": page, "page_size": page_size}


@router.get("/{model_id}")
def get_model(model_id: int) -> dict:
    row = fetch_one(
        """
        SELECT mv.*, p.name AS project_name, tr.display_name AS source_training_display_name
        FROM model_versions mv
        LEFT JOIN projects p ON p.id = mv.project_id
        LEFT JOIN training_runs tr ON tr.id = mv.training_run_id
        WHERE mv.id = %s
        """,
        (model_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail="model not found")
    return decorate_model(row)


@router.put("/{model_id}")
def update_model(model_id: int, payload: dict) -> dict:
    row = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not row:
        raise HTTPException(status_code=404, detail="model not found")
    name = payload.get("model_name", "").strip()
    notes = payload.get("notes", "")
    if not name:
        raise HTTPException(status_code=400, detail="model_name is required")
    with db() as cur:
        cur.execute("UPDATE model_versions SET model_name = %s, notes = %s WHERE id = %s", (name, notes, model_id))
        # 同步备注到关联训练
        if "notes" in payload:
            cur.execute(
                "UPDATE training_runs SET notes = %s WHERE id = (SELECT training_run_id FROM model_versions WHERE id = %s)",
                (notes, model_id),
            )
    return get_model(model_id)


@router.get("/{model_id}/artifacts")
def list_model_artifacts(model_id: int) -> dict:
    row = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not row:
        raise HTTPException(status_code=404, detail="model not found")

    registry_path = Path(row["registry_path"])
    if not registry_path.exists():
        raise HTTPException(status_code=404, detail="registry path not found")

    artifacts = []
    for file_path in sorted(registry_path.rglob("*")):
        if not file_path.is_file():
            continue
        artifacts.append({
            "name": file_path.name,
            "relative_path": file_path.relative_to(registry_path).as_posix(),
            "size": file_path.stat().st_size,
            "url": file_to_url(file_path),
        })

    return {
        "model_id": model_id,
        "registry_path": str(registry_path),
        "artifacts": artifacts,
        "best_weight_url": f"/api/models/{model_id}/download/best",
        "last_weight_url": f"/api/models/{model_id}/download/last",
    }


@router.get("/{model_id}/download/{weight_name}")
def download_weight(model_id: int, weight_name: str):
    row = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not row:
        raise HTTPException(status_code=404, detail="model not found")
    if weight_name not in {"best", "last"}:
        raise HTTPException(status_code=400, detail="weight_name must be best or last")

    path_value = row["best_pt_path"] if weight_name == "best" else row["last_pt_path"]
    if not path_value:
        raise HTTPException(status_code=404, detail=f"{weight_name}.pt 不存在")
    file_path = Path(path_value)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="weight file not found")

    return FileResponse(str(file_path), filename=file_path.name, media_type="application/octet-stream")


@router.post("/{model_id}/candidate")
def mark_candidate(model_id: int) -> dict:
    try:
        return promote_model(model_id, production=False)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{model_id}/production")
def mark_production(model_id: int) -> dict:
    try:
        return promote_model(model_id, production=True)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{model_id}")
def delete_model(model_id: int) -> dict:
    row = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not row:
        raise HTTPException(status_code=404, detail="model not found")
    with db() as cur:
        delete_model_cascade(cur, model_id)
    return {"message": "deleted"}


# ---------------------------------------------------------------------------
# 模型导出
# ---------------------------------------------------------------------------

EXPORT_FORMATS = {
    "onnx": {"suffix": ".onnx", "label": "ONNX", "description": "通用部署格式，支持 ONNX Runtime"},
    "torchscript": {"suffix": ".torchscript", "label": "TorchScript", "description": "PyTorch JIT 格式"},
    "engine": {"suffix": ".engine", "label": "TensorRT", "description": "NVIDIA GPU 加速推理"},
    "tflite": {"suffix": ".tflite", "label": "TFLite", "description": "TensorFlow Lite，移动端部署"},
    "paddle": {"suffix": "_paddle_model", "label": "PaddlePaddle", "description": "百度 Paddle 推理格式"},
    "ncnn": {"suffix": "_ncnn_model", "label": "NCNN", "description": "移动端轻量推理框架"},
    "coreml": {"suffix": ".mlpackage", "label": "CoreML", "description": "Apple 设备部署"},
    "saved_model": {"suffix": "_saved_model", "label": "SavedModel", "description": "TensorFlow SavedModel"},
}


def _next_external_training_run_id(cur) -> int:
    row = cur.execute(
        "SELECT MIN(training_run_id) AS min_id FROM model_versions WHERE training_run_id <= 0"
    ).fetchone()
    current = row["min_id"] if row and row["min_id"] is not None else 0
    return int(current) - 1


@router.get("/export/formats")
def list_export_formats() -> list[dict]:
    return [
        {"format": fmt, "label": info["label"], "description": info["description"]}
        for fmt, info in EXPORT_FORMATS.items()
    ]


@router.post("/{model_id}/export")
def export_model(model_id: int, payload: dict) -> dict:
    """异步导出模型为 ONNX/TensorRT 等格式。"""
    row = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not row:
        raise HTTPException(status_code=404, detail="模型不存在")
    export_format = payload.get("format", "onnx")
    if export_format not in EXPORT_FORMATS:
        raise HTTPException(status_code=400, detail=f"不支持的格式: {export_format}")
    model_path = row.get("best_pt_path") or row.get("last_pt_path")
    if not model_path or not Path(model_path).exists():
        raise HTTPException(status_code=400, detail="模型权重文件不存在")

    # 标记导出中
    with db() as cur:
        cur.execute("UPDATE model_versions SET notes = '' WHERE id = %s", (model_id,))

    # 后台异步导出
    import threading
    def _export_bg():
        _do_export(model_id, export_format, payload, row)
    t = threading.Thread(target=_export_bg, daemon=True)
    t.start()
    return {"model_id": model_id, "status": "exporting", "format": export_format}


def _do_export(model_id: int, export_format: str, payload: dict, row: dict):
    imgsz = int(payload.get("imgsz", 640))
    half = bool(payload.get("half", False))
    registry_path = Path(row["registry_path"]) if row.get("registry_path") else MODEL_REGISTRY_DIR / f"model_{model_id}"
    export_dir = registry_path / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    log_path = export_dir / "export.log"
    if log_path.exists():
        log_path.unlink()

    try:
        from ultralytics import YOLO
        model_path = row.get("best_pt_path") or row.get("last_pt_path")
        append_log(log_path, f"=== 导出 {export_format.upper()} 开始 (imgsz={imgsz}) ===")
        model = YOLO(model_path)
        export_kwargs = {"format": export_format, "imgsz": imgsz}
        if half and export_format in ("onnx", "engine"):
            export_kwargs["half"] = True
        # 捕获导出过程输出，显示转换进度
        import sys, io
        old_stdout = sys.stdout
        capture = io.StringIO()
        sys.stdout = capture
        t0 = time.time()
        try:
            exported = model.export(**export_kwargs)
        finally:
            sys.stdout = old_stdout
            for line in capture.getvalue().splitlines():
                if line.strip():
                    append_log(log_path, line.strip())
        elapsed = round(time.time() - t0, 2)
        if isinstance(exported, (list, tuple)):
            exported_path = Path(exported[0])
        else:
            exported_path = Path(str(exported))
        append_log(log_path, f"导出完成: {exported_path.name} ({elapsed}s)")

        # 复制文件
        dest_files = []
        if exported_path.is_file():
            dest = export_dir / exported_path.name
            shutil.copy2(exported_path, dest)
            dest_files.append({"name": exported_path.name, "size": dest.stat().st_size})
        elif exported_path.is_dir():
            for f in exported_path.rglob("*"):
                if f.is_file():
                    rel = f.relative_to(exported_path)
                    dest = export_dir / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)
                    dest_files.append({"name": rel.as_posix(), "size": dest.stat().st_size})

        # 注册为新模型版本
        now = utc_now()
        new_run_id = f"export_{model_id}_{export_format}_{int(time.time())}"
        new_registry = MODEL_REGISTRY_DIR / row.get("dataset_name", "unknown") / new_run_id
        new_registry.mkdir(parents=True, exist_ok=True)
        new_export_dir = new_registry / "exports"
        new_export_dir.mkdir(parents=True, exist_ok=True)
        exported_weight_path = ""
        for file_info in dest_files:
            src = export_dir / file_info["name"]
            if not src.exists():
                continue
            dst = new_export_dir / file_info["name"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if not exported_weight_path and dst.suffix.lower() in {".onnx", ".engine", ".torchscript", ".tflite"}:
                exported_weight_path = str(dst)
        if not exported_weight_path and dest_files:
            first = new_export_dir / dest_files[0]["name"]
            if first.exists():
                exported_weight_path = str(first)
        # 如果有 best.pt 也拷过来
        best_src = Path(row.get("best_pt_path") or "")
        copied_pt_path = ""
        if best_src.exists():
            copied_pt_path = str(new_registry / best_src.name)
            shutil.copy2(best_src, copied_pt_path)

        export_model_name = _safe_model_display_name(row)
        with db() as cur:
            external_run_id = _next_external_training_run_id(cur)
            cur.execute("""
                INSERT INTO model_versions(training_run_id, project_id, run_id, dataset_name, dataset_version,
                    base_model, epochs, imgsz, batch, precision, recall, map50, map50_95, best_epoch,
                    best_pt_path, last_pt_path, registry_path, model_name, model_format, notes, is_candidate, is_production, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, %s) RETURNING id
            """, (
                external_run_id, row.get("project_id"), new_run_id,
                row.get("dataset_name"), row.get("dataset_version"),
                copied_pt_path or row.get('base_model', ''),
                row.get("epochs"), imgsz, row.get("batch"),
                row.get("precision"), row.get("recall"), row.get("map50"), row.get("map50_95"),
                row.get("best_epoch"),
                exported_weight_path or copied_pt_path,
                copied_pt_path,
                str(new_registry),
                f"{export_model_name} [{EXPORT_FORMATS[export_format]['label']}]",
                export_format,
                f"从 {row.get('run_id')} 导出 {export_format}",
                now,
            ))
            new_id = cur.fetchone()["id"]
        append_log(log_path, f"已注册为新模型: id={new_id} run_id={new_run_id}")
        append_log(log_path, "=== 导出完成 ===")
    except Exception as exc:
        append_log(log_path, f"[ERROR] {exc}")
        import traceback
        append_log(log_path, traceback.format_exc())


def _safe_model_display_name(row: dict) -> str:
    raw_name = str(row.get("model_name") or row.get("run_id") or "").replace("\\", "/")
    if raw_name and "/" not in raw_name:
        return raw_name
    dataset = row.get("dataset_name") or "模型"
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


@router.get("/{model_id}/export/log")
def get_export_log(model_id: int) -> dict:
    row = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not row:
        raise HTTPException(status_code=404, detail="模型不存在")
    registry_path = Path(row["registry_path"]) if row.get("registry_path") else MODEL_REGISTRY_DIR / f"model_{model_id}"
    log_path = registry_path / "exports" / "export.log"
    if not log_path.exists():
        return {"log": ""}
    return {"log": log_path.read_text(encoding="utf-8")}


@router.get("/{model_id}/export/status")
def get_export_status(model_id: int) -> dict:
    row = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not row:
        raise HTTPException(status_code=404, detail="模型不存在")

    registry_path = Path(row["registry_path"]) if row.get("registry_path") else MODEL_REGISTRY_DIR / f"model_{model_id}"
    export_dir = registry_path / "exports"
    log_path = export_dir / "export.log"
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""

    status = "idle"
    if log_text:
        status = "running"
    if "[ERROR]" in log_text:
        status = "failed"
    elif "=== 导出完成 ===" in log_text:
        status = "completed"

    files = []
    if export_dir.exists():
        for file_path in sorted(export_dir.rglob("*")):
            if not file_path.is_file():
                continue
            files.append({
                "name": file_path.name,
                "relative_path": file_path.relative_to(export_dir).as_posix(),
                "size": file_path.stat().st_size,
                "url": file_to_url(file_path),
            })

    exported_model = None
    if status == "completed":
        exported = fetch_one(
            """
            SELECT * FROM model_versions
            WHERE run_id LIKE %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (f"export_{model_id}_%",),
        )
        if exported:
            exported_model = decorate_model(exported)

    return {
        "model_id": model_id,
        "status": status,
        "log": log_text,
        "files": files,
        "exported_model": exported_model,
    }


# ---------------------------------------------------------------------------
# 模型导入
# ---------------------------------------------------------------------------

IMPORT_DIR = MODEL_REGISTRY_DIR / "imported"
IMPORT_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/import")
async def import_model(
    file: UploadFile = File(...),
    model_name: str = Form(""),
    project_id: int = Form(0),
    notes: str = Form(""),
) -> dict:
    """导入外部模型文件（.pt/.onnx/.torchscript/.engine）。"""
    filename = file.filename or "model.pt"
    suffix = Path(filename).suffix.lower()
    if suffix not in (".pt", ".onnx", ".torchscript", ".engine"):
        raise HTTPException(status_code=400, detail=f"不支持的格式: {suffix}")

    name = model_name.strip() or Path(filename).stem
    model_dir = IMPORT_DIR / name
    model_dir.mkdir(parents=True, exist_ok=True)
    dest_path = model_dir / filename
    content = await file.read()
    dest_path.write_bytes(content)

    class_names = []
    try:
        from ultralytics import YOLO
        m = YOLO(str(dest_path))
        names = getattr(m, "names", None) or {}
        if names:
            class_names = [names.get(i, f"class_{i}") for i in range(max(names.keys()) + 1)]
    except Exception:
        pass

    with db() as cur:
        external_run_id = _next_external_training_run_id(cur)
        cur.execute(
            """INSERT INTO model_versions(
                training_run_id, project_id, run_id, dataset_name, dataset_version,
                base_model, epochs, imgsz, batch,
                precision, recall, map50, map50_95, best_epoch,
                best_pt_path, last_pt_path, registry_path,
                model_name, model_format, notes, is_candidate, is_production, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, %s) RETURNING *""",
            (
                external_run_id, project_id or None, f"import_{name}", name, "", filename,
                0, 0, 0, None, None, None, None, None,
                str(dest_path), "", str(model_dir), name, suffix.lstrip("."), notes, utc_now(),
            ),
        )
        model = dict(cur.fetchone())

    if class_names:
        try:
            import yaml
            (model_dir / "classes.yaml").write_text(
                yaml.dump({"names": class_names}, allow_unicode=True), encoding="utf-8"
            )
        except Exception:
            pass

    return {"model": decorate_model(model), "file": {"name": filename, "size": len(content)}, "class_names": class_names}
