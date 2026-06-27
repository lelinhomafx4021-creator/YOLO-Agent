"""路径工具 — 统一的 URL 生成和文件路径处理。"""

from pathlib import Path

from app.core.config import DATASETS_DIR, MODEL_REGISTRY_DIR, RUNS_DIR


def file_to_url(file_path: str | Path) -> str:
    """将文件系统路径转换为前端可访问的 URL。

    按优先级匹配：MODEL_REGISTRY_DIR → RUNS_DIR → DATASETS_DIR。
    不匹配时返回空字符串。
    """
    resolved = Path(file_path).resolve()
    for prefix, mount in [
        (MODEL_REGISTRY_DIR.resolve(), "/model_registry"),
        (RUNS_DIR.resolve(), "/runs"),
        (DATASETS_DIR.resolve(), "/images"),
    ]:
        try:
            if resolved.is_relative_to(prefix):
                return mount + "/" + resolved.relative_to(prefix).as_posix()
        except Exception:
            continue
    return ""


def parse_yolo_boxes(result) -> tuple[list[dict], list[str]]:
    """从 Ultralytics 推理结果中提取检测框和类别名。

    返回:
        (boxes, class_names)
        boxes: [{class_id, confidence, x_center, y_center, width, height}, ...]
        class_names: ["class_0", "class_1", ...]
    """
    boxes = []
    class_names = []
    if not result or result.boxes is None:
        return boxes, class_names

    for i in range(len(result.boxes)):
        xywhn = result.boxes.xywhn[i].tolist()
        cls_id = int(result.boxes.cls[i].item())
        conf_val = float(result.boxes.conf[i].item())
        boxes.append({
            "class_id": cls_id,
            "confidence": round(conf_val, 4),
            "x_center": round(xywhn[0], 6),
            "y_center": round(xywhn[1], 6),
            "width": round(xywhn[2], 6),
            "height": round(xywhn[3], 6),
        })

    names = getattr(result, "names", None) or {}
    if names:
        class_names = [names.get(i, f"class_{i}") for i in range(max(names.keys()) + 1)]

    return boxes, class_names


def delete_model_cascade(cur, model_id: int) -> None:
    """级联删除模型及其关联记录。"""
    row = cur.execute("SELECT training_run_id FROM model_versions WHERE id = %s", (model_id,)).fetchone()
    if row:
        trid = row["training_run_id"]
        cur.execute("DELETE FROM training_metrics WHERE training_run_id = %s", (trid,))
    cur.execute(
        "DELETE FROM evaluation_samples WHERE evaluation_run_id IN (SELECT id FROM evaluation_runs WHERE model_version_id = %s)",
        (model_id,),
    )
    cur.execute("DELETE FROM evaluation_runs WHERE model_version_id = %s", (model_id,))
    cur.execute("DELETE FROM model_versions WHERE id = %s", (model_id,))
