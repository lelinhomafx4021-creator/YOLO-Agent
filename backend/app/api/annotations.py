"""标注管理 API — CRUD、模型预标注、版本历史。"""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.annotation.prelabel_service import prelabel_image
from app.annotation.revision_service import get_revisions, get_revision_snapshot, restore_revision, save_revision
from app.annotation.yolo_txt_io import read_yolo_txt, write_yolo_txt
from app.core.config import resolve_path
from app.core.database import db, fetch_all, fetch_one
from app.dataset.version_metadata import read_class_names, refresh_dataset_version_metadata
from app.schemas.common import AnnotationUpdate, PrelabelRequest

router = APIRouter(prefix="/api/annotations", tags=["annotations"])


# COCO 80 类（yolo11n / yolov8n 等预训练模型的标准类别）
COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]


def _model_class_names(model_path: str) -> list[str]:
    """获取模型类别名；常见 YOLO 基础模型直接用 COCO，避免隐式下载权重。"""
    model_lower = Path(model_path).name.lower()
    official_coco_models = {
        "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
        "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
        "yolov5n.pt", "yolov5s.pt", "yolov5m.pt", "yolov5l.pt", "yolov5x.pt",
    }
    if model_lower in official_coco_models:
        return COCO_CLASSES
    path = resolve_path(model_path)
    if not path.exists():
        return COCO_CLASSES
    try:
        from ultralytics import YOLO
        model = YOLO(str(path))
        names = model.names
        if isinstance(names, dict):
            return [str(names[i]) for i in sorted(names.keys(), key=int)]
        if isinstance(names, list):
            return [str(name) for name in names]
    except Exception:
        return COCO_CLASSES
    return COCO_CLASSES


def _get_image_version(image: dict) -> dict:
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (image["dataset_version_id"],))
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    return version


def _dataset_class_names(version: dict) -> list[str]:
    return read_class_names(resolve_path(version["data_yaml_path"]))


def _validate_class_mapping(class_mapping: dict | None, dataset_classes: list[str]) -> dict[str, int]:
    mapping = {}
    for key, value in (class_mapping or {}).items():
        if value is None or value == "":
            continue
        dataset_class_id = int(value)
        if dataset_class_id < 0 or dataset_class_id >= len(dataset_classes):
            raise HTTPException(status_code=400, detail=f"mapped class_id out of range: {dataset_class_id}")
        mapping[str(int(key))] = dataset_class_id
    if not mapping:
        raise HTTPException(status_code=400, detail="class_mapping is required for prelabel")
    return mapping


@router.get("/model-classes")
def get_model_classes(model_path: str = "yolo11n.pt") -> dict:
    """获取模型类别列表，供预标注映射确认使用。"""
    classes = _model_class_names(model_path)
    return {"model": model_path, "class_count": len(classes), "classes": classes}


def _get_image_or_404(image_id: int) -> dict:
    """
    根据 image_id 从数据库查询图像记录，若不存在则返回 404 错误。

    这是内部辅助函数，用于减少路由处理函数中的重复代码。
    所有需要先验证图像存在的路由都通过此函数获取图像记录。

    Args:
        image_id: 图像记录的主键 ID（对应数据库 image_items 表的 id 字段）。

    Returns:
        查询到的图像记录字典（包含 id, image_path, label_path, annotation_status 等字段）。

    Raises:
        HTTPException 404: 未找到对应图像记录时抛出，detail 为 "image item not found"。
    """
    # 从数据库查询指定 id 的图像记录
    row = fetch_one("SELECT * FROM image_items WHERE id = %s", (image_id,))
    # 若查询结果为空，说明图像不存在，抛出 404 错误
    if not row:
        raise HTTPException(status_code=404, detail="image item not found")
    return row


@router.get("/{image_id}")
def read_annotation(image_id: int) -> dict:
    """
    读取指定图像的标注数据。

    GET /api/annotations/{image_id}

    从数据库获取图像信息，然后读取对应的 YOLO 格式标注文件，
    返回图像元数据和所有标注框。这是最常用的查询接口。

    Args:
        image_id: 图像记录的主键 ID。

    Returns:
        包含图像信息和标注框列表的字典：
        - image: 图像记录数据（数据库行）
        - boxes: YOLO 格式标注框列表，每个框包含类别、坐标等信息
    """
    # 先验证图像存在，同时获取图像记录信息
    image = _get_image_or_404(image_id)
    # 从本地 label_path 读取 YOLO 格式的标注文件，返回标注框列表
    boxes = read_yolo_txt(resolve_path(image["label_path"]))
    return {"image": image, "boxes": boxes}


@router.put("/{image_id}")
def update_annotation(image_id: int, payload: AnnotationUpdate) -> dict:
    """
    更新指定图像的标注数据。

    PUT /api/annotations/{image_id}

    接收前端传来的标注框列表和状态，将其写入 YOLO 格式文件，
    同时更新数据库中的标注状态，并自动保存一条手动修订版本，
    以便后续可以回溯历史版本。

    Args:
        image_id: 图像记录的主键 ID。
        payload: 请求体，包含：
            - boxes: 标注框列表（AnnotationBox 对象数组）
            - status: 标注状态字符串

    Returns:
        包含更新后的 image_id、status 和 boxes 的字典。
    """
    # 验证图像存在并获取记录
    image = _get_image_or_404(image_id)
    if not get_revisions(image_id):
        original_boxes = read_yolo_txt(resolve_path(image["label_path"]))
        save_revision(
            image_item_id=image_id,
            source="import",
            label_path=image["label_path"],
            box_count=len(original_boxes),
            note="original label before first edit",
        )
    # 将 Pydantic 模型转为普通字典，排除值为 None 的字段，以兼容 YOLO 格式写入
    boxes = [box.model_dump(exclude_none=True) for box in payload.boxes]
    # 将标注框数据写入 YOLO 格式的 txt 文件（覆盖写入）
    write_yolo_txt(resolve_path(image["label_path"]), boxes)
    # 在数据库事务中更新该图像的标注状态
    with db() as cur:
        cur.execute(
            "UPDATE image_items SET annotation_status = %s WHERE id = %s",
            (payload.status, image_id),
        )
    # 自动保存一条手动修订版本，用于后续版本历史回溯
    # source="manual" 表示此次变更是由用户手动编辑触发的
    save_revision(
        image_item_id=image_id,
        source="manual",  # 修订来源：手动编辑
        label_path=image["label_path"],
        box_count=len(boxes),  # 记录当前标注框数量，便于快速预览
        note=f"status: {payload.status}",  # 备注信息，记录更新时的状态
    )
    return {"image_id": image_id, "status": payload.status, "boxes": boxes}


@router.post("/{image_id}/prelabel")
def prelabel_annotation(image_id: int, payload: PrelabelRequest) -> dict:
    """
    对指定图像执行模型预标注。

    POST /api/annotations/{image_id}/prelabel

    调用预标注服务，使用指定的模型和置信度阈值对图像进行自动标注，
    并将结果写入 YOLO 格式文件，同时更新数据库状态为 'ai_prelabel'。

    Args:
        image_id: 图像记录的主键 ID。
        payload: 请求体，包含：
            - model_path: 预标注使用的模型权重文件路径
            - conf: 置信度阈值（0~1），低于此阈值的检测结果将被过滤

    Returns:
        包含 image_id、status（固定为 'ai_prelabel'）和 boxes（预标注框列表）的字典。

    Raises:
        HTTPException 400: 预标注过程发生异常时抛出，异常信息透传。
    """
    # 验证图像存在并获取记录
    image = _get_image_or_404(image_id)
    if image.get("annotation_status") == "reviewed":
        raise HTTPException(status_code=409, detail="reviewed annotation will not be overwritten")
    version = _get_image_version(image)
    dataset_classes = _dataset_class_names(version)
    actual_mapping = _validate_class_mapping(payload.class_mapping, dataset_classes)
    if not get_revisions(image_id):
        original_boxes = read_yolo_txt(resolve_path(image["label_path"]))
        save_revision(
            image_item_id=image_id,
            source="import",
            label_path=image["label_path"],
            box_count=len(original_boxes),
            note="original label before first prelabel",
        )
    try:
        # 调用模型预标注服务进行自动标注
        # 传入原始图像路径、标注文件路径、模型路径和置信度阈值
        boxes = prelabel_image(
            resolve_path(image["image_path"]),
            resolve_path(image["label_path"]),
            payload.model_path,
            payload.conf,
            actual_mapping,
            payload.drop_unmapped,
        )
        boxes, summary = boxes
    except Exception as exc:  # noqa: BLE001
        # 捕获所有异常（BLE001 规则忽略），将异常信息以 400 状态码返回
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # 将图像标注状态标记为模型预标注
    with db() as cur:
        cur.execute(
            "UPDATE image_items SET annotation_status = 'ai_prelabel' WHERE id = %s",
            (image_id,),
        )
    # 自动保存一条模型预标注版本的修订记录
    # source="ai_prelabel" 表示此次变更是由模型预标注服务自动触发的
    save_revision(
        image_item_id=image_id,
        source="ai_prelabel",  # 修订来源：模型预标注
        label_path=image["label_path"],
        box_count=len(boxes),
        note=f"model: {payload.model_path}, conf: {payload.conf}, mapped: {summary['mapped_count']}, dropped: {summary['dropped_count']}",
    )
    refresh_dataset_version_metadata(image["dataset_version_id"])
    return {
        "image_id": image_id,
        "status": "ai_prelabel",
        "boxes": boxes,
        "mapping": actual_mapping,
        **summary,
    }


@router.post("/batch-prelabel")
def batch_prelabel(payload: dict) -> dict:
    """
    对数据集版本中所有未复核图片进行批量模型预标注。

    请求体:
      {
        "version_id": 34,
        "model_path": "yolo11n.pt",
        "conf": 0.25,
        "class_mapping": {"15": 0, "16": 1}   // 可选: 模型class → 数据集class
      }

    默认跳过 reviewed 图片；未映射模型类别会被丢弃。
    """
    version_id = payload["version_id"]
    model_path = payload.get("model_path", "yolo11n.pt")
    conf = float(payload.get("conf", 0.25))
    drop_unmapped = bool(payload.get("drop_unmapped", True))

    # 获取数据集类别
    version = fetch_one(
        "SELECT dv.*, d.name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s",
        (version_id,),
    )
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found")

    dataset_classes = _dataset_class_names(version)
    actual_mapping = _validate_class_mapping(payload.get("class_mapping"), dataset_classes)

    # 查所有未标注图片
    images = fetch_all(
        "SELECT * FROM image_items WHERE dataset_version_id = %s AND annotation_status != 'reviewed' ORDER BY id ASC",
        (version_id,),
    )
    if not images:
        return {
            "total": 0,
            "success": 0,
            "failed": 0,
            "mapping": actual_mapping,
            "message": "没有需要预标注的图片",
        }

    total = len(images)
    success = 0
    failed = 0
    mapped_total = 0
    dropped_total = 0
    unmapped_classes: set[int] = set()
    errors = []

    for img in images:
        image_path = resolve_path(img["image_path"])
        label_path = resolve_path(img["label_path"]) if img.get("label_path") else (
            image_path.parent.parent / "labels" / (image_path.stem + ".txt")
        )
        label_path.parent.mkdir(parents=True, exist_ok=True)

        if not image_path.exists():
            failed += 1
            errors.append(f"{image_path.name}: 图片文件不存在")
            continue

        try:
            if not get_revisions(img["id"]):
                original_boxes = read_yolo_txt(label_path)
                save_revision(
                    image_item_id=img["id"],
                    source="import",
                    label_path=label_path,
                    box_count=len(original_boxes),
                    note="original label before batch prelabel",
                )
            else:
                current_boxes = read_yolo_txt(label_path)
                if current_boxes:
                    save_revision(
                        image_item_id=img["id"],
                        source="batch_prelabel_before",
                        label_path=label_path,
                        box_count=len(current_boxes),
                        note="original label before batch prelabel",
                    )

            boxes, summary = prelabel_image(
                image_path,
                label_path,
                model_path,
                conf,
                actual_mapping,
                drop_unmapped,
            )

            with db() as cur:
                cur.execute(
                    "UPDATE image_items SET annotation_status = 'ai_prelabel' WHERE id = %s",
                    (img["id"],),
                )

            save_revision(
                image_item_id=img["id"],
                source="ai_prelabel",
                label_path=label_path,
                box_count=len(boxes),
                note=f"batch model: {model_path}, conf: {conf}, mapped: {summary['mapped_count']}, dropped: {summary['dropped_count']}",
            )
            mapped_total += summary["mapped_count"]
            dropped_total += summary["dropped_count"]
            unmapped_classes.update(summary["unmapped_classes"])
            success += 1
        except Exception as e:
            failed += 1
            errors.append(f"{image_path.name}: {str(e)[:80]}")

    refresh_dataset_version_metadata(version_id)
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "mapped_count": mapped_total,
        "dropped_count": dropped_total,
        "unmapped_classes": sorted(unmapped_classes),
        "errors": errors[:10],
        "model_used": model_path,
        "mapping": actual_mapping,
        "dataset_classes": dataset_classes,
    }


@router.get("/{image_id}/history")
def list_revision_history(image_id: int) -> list[dict]:
    """
    获取指定图像的所有标注修订历史列表。

    GET /api/annotations/{image_id}/history

    先验证图像存在，然后查询并返回该图像的所有版本记录摘要。
    版本记录包含手动编辑和模型预标注两种来源。

    Args:
        image_id: 图像记录的主键 ID。

    Returns:
        修订版本列表，每个元素包含：
        - id: 版本 ID
        - source: 来源（manual / ai_prelabel）
        - box_count: 该版本的标注框数量
        - note: 备注信息
        - created_at: 创建时间戳
    """
    # 只验证图像存在，不关心具体记录内容
    _get_image_or_404(image_id)
    # 调用修订服务查询该图像的所有版本历史
    return get_revisions(image_id)


@router.get("/{image_id}/history/{revision_id}")
def get_revision_detail(image_id: int, revision_id: int) -> dict:
    """
    获取指定修订版本的详细快照数据。

    GET /api/annotations/{image_id}/history/{revision_id}

    根据 revision_id 获取该版本的完整标注数据快照（即当时的标注框列表），
    可用于预览历史版本内容或确认恢复操作的预期结果。

    Args:
        image_id: 图像记录的主键 ID（用于验证图像存在）。
        revision_id: 修订版本的主键 ID（对应 revisions 表的 id 字段）。

    Returns:
        包含修订版本详情和该版本的标注框快照的字典。

    Raises:
        HTTPException 404: revision_id 不存在时抛出。
    """
    # 验证图像存在
    _get_image_or_404(image_id)
    try:
        # 获取指定版本的快照数据
        return get_revision_snapshot(revision_id)
    except ValueError as exc:
        # revision_id 不存在时，revision_service 抛出 ValueError，转为 404 响应
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{image_id}/restore/{revision_id}")
def restore_annotation_revision(image_id: int, revision_id: int) -> dict:
    """
    将指定图像的标注恢复到指定的历史版本。

    POST /api/annotations/{image_id}/restore/{revision_id}

    根据 revision_id 回滚标注数据：将历史版本的标注框写入当前 YOLO 文件，
    并在数据库中生成一条新的恢复操作记录（source='restore'），
    以保留完整的操作审计链。

    Args:
        image_id: 图像记录的主键 ID（用于验证图像存在）。
        revision_id: 要恢复到的历史修订版本 ID。

    Returns:
        包含 image_id、操作消息和恢复后的版本详情的字典。

    Raises:
        HTTPException 404: 图像或版本不存在、或恢复所需文件缺失时抛出。
    """
    # 验证图像存在
    _get_image_or_404(image_id)
    try:
        # 执行版本恢复：将 revision_id 对应的历史快照写回 YOLO 文件
        # 并在数据库中生成一条 source='restore' 的操作记录
        rev = restore_revision(image_id, revision_id)
        return {"image_id": image_id, "message": "restored", "revision": rev}
    except (ValueError, FileNotFoundError) as exc:
        # ValueError: revision_id 不存在
        # FileNotFoundError: YOLO 标注文件丢失
        raise HTTPException(status_code=404, detail=str(exc)) from exc
