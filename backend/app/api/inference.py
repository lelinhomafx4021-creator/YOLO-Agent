"""Inference API — upload images, run YOLO prediction, view results."""

import json
import shutil
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import DATA_DIR, IMAGE_EXTENSIONS
from app.core.database import fetch_one
from app.core.log_capture import append_log
from app.core.path_utils import parse_yolo_boxes

router = APIRouter(prefix="/api", tags=["inference"])

# ONNX 等导出格式的扩展名映射
_EXPORT_WEIGHTS = ["best.onnx", "best.engine", "best.tflite", "best_saved_model", "best_openvino_model"]


def _find_pt_weight(model: dict) -> Path | None:
    """仅查找 .pt 权重文件（作为 ONNX 加载失败时的回退）。"""
    registry = Path(model.get("registry_path", ""))
    if registry.exists():
        weights_dir = registry / "weights"
        if weights_dir.is_dir():
            for pt_name in ("best.pt", "last.pt"):
                pt = weights_dir / pt_name
                if pt.exists():
                    return pt
    for key in ("best_pt_path", "last_pt_path"):
        p = model.get(key, "")
        if p and Path(p).exists():
            return Path(p)
    return None


def _find_weight(model: dict) -> Path | None:
    """为推理选择最佳权重文件。优先 best.pt（稳定可靠）。"""
    # 1. 优先 .pt（最大兼容性，不需要额外运行时）
    pt = _find_pt_weight(model)
    if pt:
        return pt
    # 2. 回退到 ONNX/TensorRT 导出
    registry = Path(model.get("registry_path", ""))
    if registry.exists():
        for search_dir in (registry / "exports", registry):
            if not search_dir.exists():
                continue
            for pattern in ("*.engine", "*.onnx"):
                for f in search_dir.rglob(pattern):
                    return f
        weights_dir = registry / "weights"
        if weights_dir.is_dir():
            for f in weights_dir.iterdir():
                if f.suffix in (".engine", ".onnx"):
                    return f
    return None

INFERENCE_DIR = DATA_DIR / "inferences"
INFERENCE_DIR.mkdir(exist_ok=True)
INFERENCE_LOG_DIR = DATA_DIR / "inference_logs"
INFERENCE_LOG_DIR.mkdir(exist_ok=True)


def _run_single_prediction(
    file: UploadFile,
    yolo,
    conf: float,
    iou: float,
    session_dir: Path,
) -> dict:
    """Process a single uploaded file: validate, run YOLO, return result dict."""
    ext = Path(file.filename).suffix.lower()
    if ext not in IMAGE_EXTENSIONS:
        return {"filename": file.filename, "error": f"不支持的文件格式: {ext}"}

    stem = Path(file.filename).stem
    safe_stem = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in stem)
    image_dir = session_dir / safe_stem
    image_dir.mkdir(parents=True, exist_ok=True)

    input_path = image_dir / f"input{ext}"
    input_path.write_bytes(file.file.read())

    t0 = time.time()
    try:
        results = yolo.predict(
            str(input_path), conf=conf, iou=iou,
            save=True, project=str(image_dir.resolve()), name="pred", exist_ok=True,
        )
        elapsed = time.time() - t0
    except Exception as e:
        return {"filename": file.filename, "error": f"推理失败: {e}"}

    # Parse detection boxes
    result = results[0] if results else None
    boxes, _ = parse_yolo_boxes(result)

    # Find annotated image saved by Ultralytics
    pred_url = None
    pred_dir = image_dir / "pred"
    if pred_dir.exists():
        for f in pred_dir.iterdir():
            if f.suffix.lower() in IMAGE_EXTENSIONS:
                pred_url = f"/inferences/{session_dir.name}/{safe_stem}/pred/{f.name}"
                break
    # 兜底：无预测图时复制原图，确保前端始终有图可显示
    if not pred_url:
        fallback = image_dir / "pred" / f"input{ext}"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, fallback)
        pred_url = f"/inferences/{session_dir.name}/{safe_stem}/pred/input{ext}"

    # Determine original image dimensions
    image_width = 0
    image_height = 0
    if result and result.boxes is not None:
        try:
            image_height, image_width = result.boxes.orig_shape[:2]
        except Exception:
            pass

    return {
        "filename": file.filename,
        "boxes": boxes,
        "box_count": len(boxes),
        "elapsed_seconds": round(elapsed, 2),
        "prediction_image_url": pred_url,
        "image_width": image_width,
        "image_height": image_height,
    }


@router.post("/inference/predict")
async def predict(
    model_id: int = Form(...),
    files: list[UploadFile] = File(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
    save_result: bool = Form(False),
    batch_name: str = Form(""),
):
    """Upload multiple images, run YOLO prediction using a registered model.

    Returns per-image boxes (class_id, confidence, x_center, y_center, width, height),
    prediction_image_url, elapsed_time, and batch totals.
    """
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个文件")

    # Fetch model from registry
    model = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    # 选择权重文件：优先 ONNX/TensorRT 导出，否则用 best.pt
    weight_path = _find_weight(model)
    if not weight_path:
        raise HTTPException(status_code=400, detail="模型权重文件不存在或已被删除")

    # Load YOLO model — ONNX 加载失败时自动回退到 .pt
    class_names = []
    try:
        from ultralytics import YOLO as _YOLO
        yolo = _YOLO(str(weight_path))
    except Exception as e:
        # ONNX 加载失败 → 尝试用 best.pt 回退
        fallback = _find_pt_weight(model)
        if fallback and fallback != weight_path:
            append_log(log_path, f"ONNX 加载失败({e})，回退到 {fallback.name}")
            yolo = _YOLO(str(fallback))
    try:
        _names = getattr(yolo, "names", None) or {}
        if _names:
            class_names = [_names.get(i, f"class_{i}") for i in range(max(_names.keys()) + 1)]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"模型加载失败: {e}") from e

    # Create a single batch session directory
    session_id = f"inf_{uuid.uuid4().hex[:8]}"
    session_dir = INFERENCE_DIR / session_id
    session_dir.mkdir(parents=True)
    log_path = INFERENCE_LOG_DIR / f"{session_id}.log"

    append_log(log_path, f"=== 推理开始 批次={batch_name or session_id} ===")
    append_log(log_path, f"模型: {model.get('dataset_name', '')} - {model.get('base_model', '')}")
    append_log(log_path, f"图片数: {len(files)} 置信度: {conf} IOU: {iou}")

    # Process each file
    results_list = []
    total_elapsed = 0.0
    for i, file in enumerate(files):
        append_log(log_path, f"[{i + 1}/{len(files)}] {file.filename} ...")
        result = _run_single_prediction(
            file=file,
            yolo=yolo,
            conf=conf,
            iou=iou,
            session_dir=session_dir,
        )
        results_list.append(result)
        if "error" in result:
            append_log(log_path, f"  ✗ {result['error']}")
        else:
            append_log(log_path, f"  ✓ {result['box_count']} 个目标, {result['elapsed_seconds']}s")
        # Only count elapsed for successful predictions
        if "elapsed_seconds" in result and "error" not in result:
            total_elapsed += result["elapsed_seconds"]

    total_boxes = sum(r.get("box_count", 0) for r in results_list)
    append_log(log_path, f"=== 推理完成 总计 {len(results_list)} 张, {total_boxes} 个目标, 耗时 {round(total_elapsed, 2)}s ===")

    # Build batch response
    batch_data = {
        "session_id": session_id,
        "batch_name": batch_name or f"推理_{session_id[:8]}",
        "results": results_list,
        "total_images": len(results_list),
        "total_boxes": sum(r.get("box_count", 0) for r in results_list),
        "total_elapsed": round(total_elapsed, 2),
        "model_name": f"{model.get('dataset_name', '?')} - {model.get('base_model', '?')}",
        "class_names": class_names,
    }

    # Save batch metadata
    if save_result:
        with open(session_dir / "result.json", "w", encoding="utf-8") as f:
            json.dump(batch_data, f, ensure_ascii=False, indent=2)

    return batch_data


@router.get("/inference/history")
def list_inference_history(limit: int = 20):
    """List recent inference sessions with their metadata."""
    if not INFERENCE_DIR.exists():
        return []

    dirs = sorted(
        INFERENCE_DIR.iterdir(),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    history = []
    for d in dirs[:limit]:
        result_file = d / "result.json"
        if result_file.exists():
            try:
                data = json.loads(result_file.read_text("utf-8"))
                # 补充 session_id（从目录名提取）
                data["session_id"] = data.get("session_id") or d.name
                history.append(data)
            except Exception:
                pass
    return history


@router.get("/inference/{session_id}/log")
def get_inference_log(session_id: str):
    """获取推理批次的日志。"""
    log_path = INFERENCE_LOG_DIR / f"{session_id}.log"
    if not log_path.exists():
        return {"log": ""}
    return {"log": log_path.read_text(encoding="utf-8")}
