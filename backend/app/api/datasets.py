import json
import shutil
import zipfile
from pathlib import Path
from typing import Optional

import yaml

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.core.config import DATA_DIR, DATASETS_DIR, IMAGE_EXTENSIONS, relative_path, resolve_path
from app.core.database import db, fetch_all, fetch_one, utc_now
from app.dataset.importer import create_dataset, get_version_artifact, import_yolo_dataset
from app.dataset.importer import next_version as next_dataset_version
from app.dataset.statistics import fingerprint_directory
from app.dataset.version_metadata import (
    DEFAULT_REVIEW_SUGGESTIONS,
    normalize_class_names,
    read_class_names,
    refresh_dataset_version_metadata,
    write_dataset_yaml,
)
from app.presentation import decorate_model, decorate_training_run
from app.schemas.common import DatasetCreate, DatasetImportRequest

router = APIRouter(prefix="/api", tags=["datasets"])


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


@router.get("/overview")
def get_overview() -> dict:
    # 单条 SQL 获取版本 + 审计信息（审计字段已合并到 dataset_versions）
    versions = fetch_all("""
        SELECT dv.*, d.name AS dataset_name,
               COALESCE(dv.missing_labels,0) + COALESCE(dv.orphan_labels,0)
               + COALESCE(dv.invalid_bboxes,0) + COALESCE(dv.empty_labels,0) AS issue_count
        FROM dataset_versions dv
        JOIN datasets d ON d.id = dv.dataset_id
        ORDER BY dv.id DESC
    """)
    total_images = sum(v.get("image_count", 0) for v in versions)
    issue_count = sum(v.get("issue_count", 0) for v in versions)

    # 单条 SQL 获取最近训练 + 关联信息（消除 Python 循环）
    recent_runs = fetch_all("""
        SELECT tr.id, tr.run_id, tr.display_name, tr.status, tr.finished_at,
               p.name AS project_name,
               COALESCE(d.name, tr.dataset_name, '') AS dataset_name,
               mv.map50, mv.model_name AS model_name, mv.base_model AS model_base_model, mv.model_format AS model_format
        FROM training_runs tr
        LEFT JOIN projects p ON p.id = tr.project_id
        LEFT JOIN dataset_versions dv ON dv.id = tr.dataset_version_id
        LEFT JOIN datasets d ON d.id = dv.dataset_id
        LEFT JOIN model_versions mv ON mv.training_run_id = tr.id
        ORDER BY tr.id DESC LIMIT 8
    """)

    # 单条 SQL 获取最近模型
    recent_models = fetch_all("""
        SELECT mv.id, mv.run_id, mv.model_name, mv.dataset_name, mv.base_model, mv.model_format, mv.map50_95, mv.is_production,
               tr.display_name AS source_training_display_name,
               mv.created_at, p.name AS project_name
        FROM model_versions mv
        LEFT JOIN training_runs tr ON tr.id = mv.training_run_id
        LEFT JOIN projects p ON p.id = mv.project_id
        ORDER BY mv.id DESC LIMIT 5
    """)

    project_count = fetch_one("SELECT COUNT(*) AS c FROM projects")
    version_count = fetch_one("SELECT COUNT(*) AS c FROM dataset_versions")
    training_count = fetch_one("SELECT COUNT(*) AS c FROM training_runs")
    model_count = fetch_one("SELECT COUNT(*) AS c FROM model_versions")
    recent_runs = [decorate_training_run(row) for row in recent_runs]
    recent_models = [decorate_model(row) for row in recent_models]
    return {
        "project_count": project_count["c"] if project_count else 0,
        "dataset_count": version_count["c"] if version_count else 0,
        "total_images": total_images,
        "training_count": training_count["c"] if training_count else 0,
        "model_count": model_count["c"] if model_count else 0,
        "recent_runs": recent_runs,
        "recent_models": recent_models,
    }



@router.put("/datasets/{dataset_id}")
def update_dataset_api(dataset_id: int, payload: DatasetCreate) -> dict:
    ds = fetch_one("SELECT * FROM datasets WHERE id = %s", (dataset_id,))
    if not ds:
        raise HTTPException(status_code=404, detail="dataset not found")
    with db() as cur:
        cur.execute("UPDATE datasets SET name = %s, description = %s WHERE id = %s RETURNING *",
                     (payload.name, payload.description, dataset_id))
        return dict(cur.fetchone())


@router.put("/collections/rename")
def rename_collection(payload: dict) -> dict:
    """重命名合集：将所有 collection_name = old_name 的数据集改为 new_name。
    如果 collection_name 为空，则按 dataset name 匹配（去掉后缀）。"""
    old_name = (payload.get("old_name") or "").strip()
    new_name = (payload.get("new_name") or "").strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name 和 new_name 不能为空")
    existing = fetch_one("SELECT id FROM datasets WHERE collection_name = %s LIMIT 1", (new_name,))
    if existing:
        raise HTTPException(status_code=409, detail=f"合集「{new_name}」已存在")
    with db() as cur:
        # 先匹配 collection_name
        cur.execute(
            "UPDATE datasets SET collection_name = %s WHERE collection_name = %s",
            (new_name, old_name),
        )
        affected = cur.cursor.rowcount if hasattr(cur.cursor, 'rowcount') else 0
        # 如果没匹配到，按名称匹配（兼容旧数据 collection_name 为空的情况）
        if affected == 0:
            cur.execute(
                "UPDATE datasets SET collection_name = %s WHERE name = %s OR name LIKE %s",
                (new_name, old_name, old_name + '_%'),
            )
    return {"old_name": old_name, "new_name": new_name, "message": "合集已重命名"}


@router.get("/collections")
def list_collections() -> list[dict]:
    """列出所有合集，带统计信息"""
    rows = fetch_all("""
        SELECT d.collection_name,
               COUNT(*) AS dataset_count,
               SUM(dv.image_count) AS total_images,
               COUNT(DISTINCT dv.id) AS version_count
        FROM datasets d
        JOIN dataset_versions dv ON dv.dataset_id = d.id
        WHERE d.collection_name != ''
        GROUP BY d.collection_name
        ORDER BY d.collection_name
    """)
    return rows


@router.post("/datasets")
def create_dataset_api(payload: DatasetCreate) -> dict:
    try:
        return create_dataset(payload.name, payload.description)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/dataset-versions")
def list_dataset_versions(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> dict:
    total = fetch_one("SELECT COUNT(*) AS c FROM dataset_versions")
    rows = fetch_all(
        """
        SELECT dv.*, d.name AS dataset_name, d.collection_name,
               COALESCE(SUM(CASE WHEN ii.annotation_status IN ('unlabeled', 'ai_prelabel') THEN 1 ELSE 0 END), 0) AS pending_count,
               COALESCE(SUM(CASE WHEN ii.annotation_status = 'reviewed' THEN 1 ELSE 0 END), 0) AS reviewed_count,
               (SELECT de.id FROM dataset_exports de WHERE de.dataset_version_id = dv.id ORDER BY de.id DESC LIMIT 1) AS latest_export_id
        FROM dataset_versions dv
        JOIN datasets d ON d.id = dv.dataset_id
        LEFT JOIN image_items ii ON ii.dataset_version_id = dv.id
        GROUP BY dv.id, d.name
        ORDER BY dv.id DESC
        LIMIT %s OFFSET %s
        """,
        (page_size, (page - 1) * page_size),
    )
    return {"items": rows, "total": total["c"] if total else 0, "page": page, "page_size": page_size}


@router.post("/datasets/{dataset_id}/versions")
def import_dataset_version(dataset_id: int, payload: DatasetImportRequest) -> dict:
    try:
        return import_yolo_dataset(dataset_id, Path(payload.source_path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/versions/upload")
async def upload_dataset_version(dataset_id: int, file: UploadFile = File(...)) -> dict:
    filename = file.filename or "dataset.zip"
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="only .zip dataset packages are supported")

    upload_root = DATA_DIR / "uploads" / f"dataset_{dataset_id}_{Path(filename).stem}"
    if upload_root.exists():
        shutil.rmtree(upload_root)
    upload_root.mkdir(parents=True, exist_ok=True)

    zip_path = upload_root / filename
    with zip_path.open("wb") as target:
        while chunk := await file.read(1024 * 1024):
            target.write(chunk)

    extract_root = upload_root / "extracted"
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            _safe_extract_zip(archive, extract_root)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="invalid zip file") from exc

    # 兼容常见文件夹命名：image→images, annotation→labels
    _normalize_folder_names(extract_root)

    # 检查是否有子目录包含 data.yaml（ZIP 可能多包了一层）
    sub_dirs = [d for d in extract_root.iterdir() if d.is_dir() and (d / "data.yaml").exists()]
    if sub_dirs:
        extract_root = sub_dirs[0]

    # 如果没有标准 images/labels 目录结构，自动整理扁平文件
    has_labels = any((extract_root / d).is_dir() for d in ["labels", "train/labels", "val/labels"])
    has_images = any((extract_root / d).is_dir() for d in ["images", "train/images", "val/images"])
    if not has_labels or not has_images:
        _reorganize_flat_folder(extract_root)
        _normalize_folder_names(extract_root)

    dataset_root = _find_yolo_root(extract_root)
    if dataset_root is None:
        _generate_data_yaml_if_missing(extract_root)
        dataset_root = extract_root

    try:
        return import_yolo_dataset(dataset_id, dataset_root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/versions/upload-folder")
async def upload_dataset_folder(dataset_id: int, files: list[UploadFile] = File(...)) -> dict:
    """上传完整 YOLO 数据集文件夹"""
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    upload_root = DATA_DIR / "uploads" / f"dataset_{dataset_id}_folder_{len(files)}"
    if upload_root.exists():
        shutil.rmtree(upload_root)
    upload_root.mkdir(parents=True, exist_ok=True)

    for file in files:
        relative_name = _safe_upload_relative_name(file.filename or "")
        if not relative_name:
            continue
        target = upload_root.joinpath(*relative_name.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)

    # 兼容常见文件夹命名：image→images, annotation→labels
    _normalize_folder_names(upload_root)

    # 如果没有标准 images/labels 目录结构，自动整理扁平文件
    has_labels = any((upload_root / d).is_dir() for d in ["labels", "train/labels", "val/labels"])
    has_images = any((upload_root / d).is_dir() for d in ["images", "train/images", "val/images"])
    if not has_labels or not has_images:
        _reorganize_flat_folder(upload_root)
        _normalize_folder_names(upload_root)

    dataset_root = _find_yolo_root(upload_root)
    if dataset_root is None:
        _generate_data_yaml_if_missing(upload_root)
        dataset_root = upload_root

    try:
        return import_yolo_dataset(dataset_id, dataset_root)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/datasets/{dataset_id}/annotation/upload-folder")
async def upload_annotation_folder(
    dataset_id: int,
    files: list[UploadFile] = File(...),
    class_names: str = Form(""),
) -> dict:
    dataset = fetch_one("SELECT * FROM datasets WHERE id = %s", (dataset_id,))
    if not dataset:
        raise HTTPException(status_code=404, detail="dataset not found")
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    version = next_dataset_version(dataset_id)
    version_root = DATASETS_DIR / dataset["name"] / version
    if version_root.exists():
        shutil.rmtree(version_root)

    images_root = version_root / "images" / "unlabeled"
    labels_root = version_root / "labels" / "unlabeled"
    images_root.mkdir(parents=True, exist_ok=True)
    labels_root.mkdir(parents=True, exist_ok=True)

    image_count = 0
    for file in files:
        relative_name = _safe_upload_relative_name(file.filename or "")
        if not relative_name or Path(relative_name).suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        target = images_root / Path(relative_name).name
        stem = target.stem
        suffix = target.suffix
        counter = 1
        while target.exists():
            target = images_root / f"{stem}_{counter}{suffix}"
            counter += 1
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        (labels_root / target.with_suffix(".txt").name).write_text("", encoding="utf-8")
        image_count += 1

    if image_count == 0:
        shutil.rmtree(version_root, ignore_errors=True)
        raise HTTPException(status_code=400, detail="no supported image files found")

    names = normalize_class_names(class_names)
    write_dataset_yaml(
        version_root / "data.yaml",
        version_root,
        "images/unlabeled",
        "images/unlabeled",
        "images/unlabeled",
        names,
    )
    report_path = version_root / "label_audit_report.json"
    report_payload = {
        "image_count": image_count,
        "label_file_count": image_count,
        "instance_count": 0,
        "missing_labels": 0,
        "orphan_labels": 0,
        "invalid_bboxes": 0,
        "empty_labels": image_count,
        "class_distribution": {name: 0 for name in names},
        "suggestions": DEFAULT_REVIEW_SUGGESTIONS,
    }
    report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fingerprint = fingerprint_directory(version_root)

    with db() as cur:
        cur.execute(
            """
            INSERT INTO dataset_versions(
                dataset_id, version, root_path, data_yaml_path, image_count,
                label_file_count, instance_count, class_count, fingerprint, status, dtype, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s, 'annotation', 'annotation', %s) RETURNING id
            """,
            (
                dataset_id,
                version,
                relative_path(version_root),
                relative_path(version_root / "data.yaml"),
                image_count,
                image_count,
                len(names),
                fingerprint,
                utc_now(),
            ),
        )
        version_id = cur.fetchone()["id"]
        cur.execute(
            """
            UPDATE dataset_versions
            SET empty_labels = %s, class_distribution_json = %s, suggestions_json = %s, audit_report_path = %s
            WHERE id = %s
            """,
            (
                image_count,
                json.dumps(report_payload["class_distribution"], ensure_ascii=False),
                json.dumps(report_payload["suggestions"], ensure_ascii=False),
                str(report_path),
                version_id,
            ),
        )
        for image_path in sorted(images_root.iterdir()):
            if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            label_path = labels_root / image_path.with_suffix(".txt").name
            cur.execute(
                """
                INSERT INTO image_items(dataset_version_id, split, image_path, label_path, annotation_status, width, height)
                VALUES (%s, 'unlabeled', %s, %s, 'unlabeled', 0, 0)
                """,
                (version_id, relative_path(image_path), relative_path(label_path)),
            )

    refresh_dataset_version_metadata(version_id)
    row = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (version_id,))
    return row or {}


@router.post("/dataset-versions/{version_id}/append-images")
async def append_images_to_version(
    version_id: int,
    files: list[UploadFile] = File(...),
) -> dict:
    """向已有数据集版本追加图片（分批上传的后续批次）。

    自动检测版本的 split 目录结构：
    - 如果已有 images/unlabeled/ → 追加到 unlabeled
    - 如果已有 images/ 根目录下图片 → 追加到 images/
    - 否则默认创建 images/ 结构
    """
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (version_id,))
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")

    root = resolve_path(version["root_path"])

    # 自动检测 split 子目录
    split_dir = "unlabeled"  # 默认
    images_root = root / "images" / "unlabeled"
    labels_root = root / "labels" / "unlabeled"

    # 如果 unlabeled 不存在，检查是否有其他子目录结构
    if not images_root.exists():
        images_dir = root / "images"
        if images_dir.exists():
            subdirs = [d for d in images_dir.iterdir() if d.is_dir()]
            if subdirs:
                split_dir = subdirs[0].name
                images_root = images_dir / split_dir
                labels_root = root / "labels" / split_dir
            else:
                # images/ 下有文件但没有子目录 → 使用 images/ 根
                images_root = images_dir
                labels_root = root / "labels"
                split_dir = ""
        else:
            # 完全没有 images 目录 → 创建标准结构
            split_dir = "unlabeled"

    if split_dir:
        images_root = root / "images" / split_dir
        labels_root = root / "labels" / split_dir

    # 确保目录存在
    images_root.mkdir(parents=True, exist_ok=True)
    labels_root.mkdir(parents=True, exist_ok=True)

    added = 0
    errors = []
    for file in files:
        try:
            name = Path(file.filename or "").name
            if not name or Path(name).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            target = images_root / name
            stem, suffix = target.stem, target.suffix
            counter = 1
            while target.exists():
                target = images_root / f"{stem}_{counter}{suffix}"
                counter += 1
            content = await file.read(10 * 1024 * 1024)  # 10MB max per file
            target.write_bytes(content)
            label_path = labels_root / target.with_suffix(".txt").name
            if not label_path.exists():
                label_path.write_text("", encoding="utf-8")
            actual_split = split_dir if split_dir else "unlabeled"
            with db() as cur:
                cur.execute(
                    "INSERT INTO image_items(dataset_version_id, split, image_path, label_path, annotation_status, width, height) VALUES (%s, %s, %s, %s, 'unlabeled', 0, 0)",
                    (version_id, actual_split, relative_path(target), relative_path(label_path)),
                )
            added += 1
        except Exception as exc:
            errors.append(f"{getattr(file, 'filename', '?')}: {exc}")

    refresh_dataset_version_metadata(version_id)
    result = {"version_id": version_id, "added": added}
    if errors:
        result["errors"] = errors[:10]  # 最多返回前 10 个错误
    return result


@router.get("/dataset-versions/{version_id}/annotation-progress")
def get_annotation_progress(version_id: int) -> dict:
    """获取数据集的标注进度。

    返回各类标注状态的图片数量，以及"下一张未标注"的 image_id，
    方便标注工作台快速跳转到待标注位置。
    """
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (version_id,))
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")

    counts = fetch_all(
        """SELECT annotation_status, COUNT(*) AS c
           FROM image_items WHERE dataset_version_id = %s
           GROUP BY annotation_status""",
        (version_id,),
    )
    status_counts = {"unlabeled": 0, "ai_prelabel": 0, "reviewed": 0}
    for row in counts:
        status_counts[row["annotation_status"]] = row["c"]

    total = sum(status_counts.values())
    annotated = status_counts["reviewed"] + status_counts["ai_prelabel"]

    # 找下一张未标注的图片
    next_unlabeled = fetch_one(
        """SELECT id FROM image_items
           WHERE dataset_version_id = %s AND annotation_status IN ('unlabeled', 'ai_prelabel')
           ORDER BY id ASC LIMIT 1""",
        (version_id,),
    )
    # 找下一张未标注的索引（在所有图片中的位置）
    next_index = None
    if next_unlabeled:
        idx_row = fetch_one(
            """SELECT COUNT(*) AS c FROM image_items
               WHERE dataset_version_id = %s AND id < %s""",
            (version_id, next_unlabeled["id"]),
        )
        next_index = idx_row["c"] if idx_row else 0

    return {
        "version_id": version_id,
        "total": total,
        "annotated": annotated,
        "unlabeled": status_counts["unlabeled"],
        "ai_prelabel": status_counts["ai_prelabel"],
        "reviewed": status_counts["reviewed"],
        "next_unlabeled_image_id": next_unlabeled["id"] if next_unlabeled else None,
        "next_unlabeled_index": next_index,
    }


@router.post("/dataset-versions/{version_id}/dtype")
def change_dtype(version_id: int, payload: dict | None = None) -> dict:
    """切换数据集类型：annotation→inference 等"""
    payload = payload or {}
    new_dtype = payload.get("dtype", "")
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (version_id,))
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    with db() as cur:
        cur.execute("UPDATE dataset_versions SET dtype = %s WHERE id = %s", (new_dtype, version_id))
    return {"id": version_id, "dtype": new_dtype}


@router.get("/dataset-versions/{version_id}/data-yaml")
def get_data_yaml(version_id: int) -> dict:
    """读取数据集的 data.yaml 内容，用于前端展示。"""
    from app.dataset.version_metadata import read_class_names
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (version_id,))
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")
    yaml_path = Path(version["data_yaml_path"])
    raw = ""
    classes = []
    nc = 0
    if yaml_path.exists():
        raw = yaml_path.read_text(encoding="utf-8")
        classes = read_class_names(yaml_path)
        nc = len(classes)
    return {
        "version_id": version_id,
        "path": str(yaml_path),
        "content": raw,
        "class_names": classes,
        "nc": nc,
        "exists": yaml_path.exists(),
    }

@router.post("/dataset-versions/{version_id}/split-into")
def split_into_independent(version_id: int, payload: dict | None = None) -> dict:
    """将一个数据集拆成 3 个独立数据集（train/val/test），可按数量控制大小。

    payload:
      train_count: int  - train 数据集取多少张（0=按比例）
      val_count: int    - val 数据集取多少张
      test_count: int   - test 数据集取多少张
      train_ratio: float - 如果上面都是 0，按比例拆分
      val_ratio: float
      test_ratio: float
    """
    payload = payload or {}
    version = fetch_one(
        "SELECT dv.*, d.name AS dataset_name FROM dataset_versions dv "
        "JOIN datasets d ON d.id = dv.dataset_id WHERE dv.id = %s",
        (version_id,),
    )
    if not version:
        raise HTTPException(status_code=404, detail="dataset version not found")

    # 获取图片：标注中的数据集只取已复核的，其余取全部有标注的
    is_annotation_ds = (version.get("dtype") or "").strip() == "annotation"
    only_reviewed = payload.get("only_reviewed", False) or is_annotation_ds

    if only_reviewed:
        rows = fetch_all(
            "SELECT * FROM image_items WHERE dataset_version_id = %s AND annotation_status = 'reviewed' ORDER BY RANDOM()",
            (version_id,),
        )
    else:
        rows = fetch_all(
            "SELECT * FROM image_items WHERE dataset_version_id = %s ORDER BY RANDOM()",
            (version_id,),
        )

    if not rows:
        msg = "还没有已标注的图片，请先完成标注后再拆分" if only_reviewed else "没有图片可拆分"
        raise HTTPException(status_code=400, detail=msg)

    import random
    random.shuffle(rows)

    train_count = int(payload.get("train_count", 0))
    val_count = int(payload.get("val_count", 0))
    test_count = int(payload.get("test_count", 0))
    total = len(rows)

    # 如果指定了数量，按数量拆分
    if train_count > 0 or val_count > 0 or test_count > 0:
        # 按数量拆分时严格使用用户填写的数量；未填写的 split 保持 0。
        # 这样可以先拆一小批 reviewed 图片训练小模型，不会把剩余图片自动塞进 val/test。
        specified = train_count + val_count + test_count
        if specified <= 0:
            raise HTTPException(status_code=400, detail="split count must be greater than 0")
        if specified > total:
            raise HTTPException(status_code=400, detail=f"split count {specified} exceeds available images {total}")
    else:
        # 按比例拆分
        train_ratio = float(payload.get("train_ratio", 0.7))
        val_ratio = float(payload.get("val_ratio", 0.2))
        test_ratio = float(payload.get("test_ratio", 0.1))
        if train_ratio <= 0 or val_ratio < 0 or test_ratio < 0 or abs((train_ratio + val_ratio + test_ratio) - 1) > 0.01:
            raise HTTPException(status_code=400, detail="ratios must sum to 1")
        raw_counts = {
            "train": total * train_ratio,
            "val": total * val_ratio,
            "test": total * test_ratio,
        }
        split_counts = {name: int(value) for name, value in raw_counts.items()}
        remaining = total - sum(split_counts.values())
        for name, _ in sorted(raw_counts.items(), key=lambda item: item[1] - int(item[1]), reverse=True):
            if remaining <= 0:
                break
            split_counts[name] += 1
            remaining -= 1
        if split_counts["train"] <= 0:
            donor = "val" if split_counts["val"] > split_counts["test"] else "test"
            if split_counts[donor] > 0:
                split_counts[donor] -= 1
                split_counts["train"] = 1
        train_count = split_counts["train"]
        val_count = split_counts["val"]
        test_count = split_counts["test"]

    # 截取
    train_rows = rows[:train_count]
    val_rows = rows[train_count:train_count + val_count]
    test_rows = rows[train_count + val_count:train_count + val_count + test_count]

    base_name = version["dataset_name"]
    collection = (version.get("collection_name") or "").strip()
    if not collection:
        # 从名称推断合集名（去掉后缀）
        import re as _re
        collection = _re.sub(r'_(train|val|test|inference)$', '', base_name)

    dtype_map = {"train": "train", "val": "val", "test": "test"}
    type_label_map = {"train": "训练集", "val": "验证集", "test": "测试集"}
    root_path = resolve_path(version["root_path"])
    results = {}

    for split_name, split_rows in [("train", train_rows), ("val", val_rows), ("test", test_rows)]:
        if not split_rows:
            continue

        # 创建独立数据集 — 命名: 物种-类型
        ds_name = f"{collection}-{type_label_map[split_name]}"
        now = utc_now()
        with db() as cur:
            existing = cur.execute("SELECT id FROM datasets WHERE name = %s", (ds_name,)).fetchone()
            if not existing:
                cur.execute(
                    "INSERT INTO datasets(name, description, collection_name, created_at) VALUES (%s, %s, %s, %s)",
                    (ds_name, f"从 {base_name} 自动拆分", collection, now),
                )
                ds_id = cur.execute("SELECT id FROM datasets WHERE name = %s", (ds_name,)).fetchone()["id"]
            else:
                ds_id = existing["id"]

        # 创建版本目录
        new_ver = next_dataset_version(ds_id)
        new_root = DATASETS_DIR / ds_name / new_ver
        new_images = new_root / "images"
        new_labels = new_root / "labels"
        new_images.mkdir(parents=True, exist_ok=True)
        new_labels.mkdir(parents=True, exist_ok=True)

        # 复制文件
        import shutil as _shutil
        copied = 0
        for item in split_rows:
            src_img = resolve_path(item["image_path"])
            src_lbl = resolve_path(item["label_path"])
            if src_img.exists():
                _shutil.copy2(src_img, new_images / src_img.name)
                copied += 1
            if src_lbl.exists():
                _shutil.copy2(src_lbl, new_labels / src_lbl.name)

        # 写 data.yaml
        class_names = read_class_names(root_path / "data.yaml") if (root_path / "data.yaml").exists() else []
        write_dataset_yaml(new_root / "data.yaml", new_root, "images", "images", "images", class_names)

        # 写入数据库
        fingerprint = fingerprint_directory(new_root)
        with db() as cur:
            cur.execute(
                """INSERT INTO dataset_versions(dataset_id, version, root_path, data_yaml_path,
                   image_count, label_file_count, instance_count, class_count, fingerprint, status, dtype, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'imported', %s, %s) RETURNING id""",
                (ds_id, new_ver, str(new_root), str(new_root / "data.yaml"),
                 copied, copied, 0, len(class_names), fingerprint, dtype_map[split_name], now),
            )
            new_vid = cur.fetchone()["id"]
            for item in split_rows:
                src_img = resolve_path(item["image_path"])
                src_lbl = resolve_path(item["label_path"])
                cur.execute(
                    """INSERT INTO image_items(dataset_version_id, split, image_path, label_path,
                       annotation_status, width, height, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (new_vid, split_name, str(new_images / src_img.name),
                     str(new_labels / src_lbl.name) if src_lbl.exists() else "",
                     item.get("annotation_status", "reviewed"),
                     item.get("width", 0), item.get("height", 0), now),
                )

        results[split_name] = {"dataset_id": ds_id, "dataset_name": ds_name, "version": new_ver, "count": copied}

    return {"source": base_name, "total": total, "splits": results}



@router.delete("/dataset-versions/{version_id}")
def delete_version(version_id: int) -> dict:
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (version_id,))
    if not version:
        raise HTTPException(status_code=404, detail="version not found")
    with db() as cur:
        cur.execute("DELETE FROM annotation_revisions WHERE image_item_id IN (SELECT id FROM image_items WHERE dataset_version_id = %s)", (version_id,))
        cur.execute("DELETE FROM image_items WHERE dataset_version_id = %s", (version_id,))
        cur.execute("DELETE FROM dataset_exports WHERE dataset_version_id = %s", (version_id,))
        cur.execute("DELETE FROM project_dataset_bindings WHERE dataset_version_id = %s", (version_id,))
        cur.execute("DELETE FROM dataset_versions WHERE id = %s", (version_id,))
    return {"message": "deleted"}



def _normalize_folder_names(upload_root: Path) -> None:
    """兼容常见文件夹命名：image→images, annotation/annot→labels"""
    renames = {
        "image": "images",
        "annot": "labels",
        "annotation": "labels",
        "img": "images",
    }
    for old_name, new_name in renames.items():
        old_path = upload_root / old_name
        new_path = upload_root / new_name
        if old_path.is_dir() and not new_path.exists():
            old_path.rename(new_path)
            # 同步更新 data.yaml 中的路径引用
            _fix_data_yaml_refs(upload_root, old_name, new_name)


def _fix_data_yaml_refs(upload_root: Path, old_name: str, new_name: str) -> None:
    """修复 data.yaml 中对已重命名文件夹的引用"""
    for yaml_file in upload_root.rglob("data.yaml"):
        try:
            content = yaml_file.read_text(encoding="utf-8")
            if old_name in content:
                content = content.replace(old_name + "/", new_name + "/")
                content = content.replace(f"train: {old_name}", f"train: {new_name}")
                content = content.replace(f"val: {old_name}", f"val: {new_name}")
                yaml_file.write_text(content, encoding="utf-8")
        except Exception:
            pass


def _reorganize_flat_folder(upload_root: Path) -> None:
    """把扁平文件夹整理为标准 YOLO 结构：images/ + labels/。

    扫描 upload_root 下所有文件，按扩展名分类：
    - .jpg/.jpeg/.png/.bmp/.gif/.webp → images/
    - .txt → labels/
    已在 images/ 或 labels/ 子目录中的文件不动。
    """
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tif', '.tiff'}
    images_dir = upload_root / "images"
    labels_dir = upload_root / "labels"
    images_dir.mkdir(exist_ok=True)
    labels_dir.mkdir(exist_ok=True)

    # 收集需要移动的文件
    files_to_move = []
    for f in upload_root.rglob("*"):
        if not f.is_file():
            continue
        # 跳过已在 images/ 或 labels/ 下的文件
        try:
            rel = f.relative_to(upload_root)
        except ValueError:
            continue
        parts = rel.parts
        if parts and parts[0] in ("images", "labels"):
            continue

        ext = f.suffix.lower()
        if ext in IMAGE_EXTS:
            files_to_move.append((f, images_dir / f.name))
        elif ext == ".txt":
            files_to_move.append((f, labels_dir / f.name))

    # 执行移动，处理文件名冲突
    for src, dst in files_to_move:
        if dst.exists():
            stem = dst.stem
            suffix = dst.suffix
            counter = 1
            while dst.exists():
                dst = dst.parent / f"{stem}_{counter}{suffix}"
                counter += 1
        shutil.move(str(src), str(dst))


def _auto_detect_classes(upload_root: Path) -> list[str]:
    """扫描 label txt 文件，自动检测类别 ID 并返回类别名列表。

    遍历 upload_root 下所有 .txt 文件（labels 目录或根目录），
    解析每行第一个数字（class_id），收集所有出现过的 class_id，
    按 ID 排序后生成 class_0, class_1, ... 名称。
    """
    class_ids = set()
    for txt_path in upload_root.rglob("*.txt"):
        try:
            for line in txt_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines():
                parts = line.strip().split()
                if parts:
                    cid = int(float(parts[0]))
                    class_ids.add(cid)
        except (ValueError, IndexError):
            continue
    if not class_ids:
        return ["object"]
    # 按 ID 排序生成类别名称
    return [f"class_{i}" for i in sorted(class_ids)]


def _generate_data_yaml_if_missing(upload_root: Path) -> Path:
    """如果 upload_root 下没有 data.yaml，自动扫描 label 文件检测类别并生成。

    返回 data.yaml 的路径。
    """
    yaml_path = upload_root / "data.yaml"
    if yaml_path.exists():
        return yaml_path

    names = _auto_detect_classes(upload_root)

    # 尝试找到 images 目录
    images_dir = None
    for candidate in ["images", "train/images", "val/images", "test/images"]:
        if (upload_root / candidate).is_dir():
            images_dir = candidate
            break
    if not images_dir:
        images_dir = "images"

    # 尝试找到 labels 目录
    labels_dir = None
    for candidate in ["labels", "train/labels", "val/labels", "test/labels"]:
        if (upload_root / candidate).is_dir():
            labels_dir = candidate
            break
    if not labels_dir:
        labels_dir = "labels"

    content = {
        "path": str(upload_root),
        "train": f"{images_dir}/train" if (upload_root / images_dir / "train").is_dir() else images_dir,
        "val": f"{images_dir}/val" if (upload_root / images_dir / "val").is_dir() else images_dir,
        "names": {i: name for i, name in enumerate(names)},
        "nc": len(names),
    }
    yaml_path.write_text(yaml.dump(content, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return yaml_path


def _safe_extract_zip(archive: zipfile.ZipFile, target_dir: Path) -> None:
    target_dir = target_dir.resolve()
    for member in archive.infolist():
        destination = (target_dir / member.filename).resolve()
        if not str(destination).startswith(str(target_dir)):
            raise HTTPException(status_code=400, detail="zip contains unsafe paths")
    archive.extractall(target_dir)


def _find_yolo_root(root: Path) -> Path | None:
    if (root / "data.yaml").exists():
        return root
    matches = list(root.rglob("data.yaml"))
    if not matches:
        return None
    return matches[0].parent


def _safe_upload_relative_name(filename: str) -> str:
    relative_name = filename.replace("\\", "/").lstrip("/")
    parts = [part for part in relative_name.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise HTTPException(status_code=400, detail="upload contains unsafe paths")
    return "/".join(parts)



@router.get("/dataset-versions/{version_id}/audit")
def get_dataset_audit(version_id: int) -> dict:
    refresh_dataset_version_metadata(version_id)
    row = fetch_one("SELECT missing_labels, orphan_labels, invalid_bboxes, empty_labels, class_distribution_json, suggestions_json, audit_report_path FROM dataset_versions WHERE id = %s", (version_id,))
    if not row or not row.get("audit_report_path"):
        raise HTTPException(status_code=404, detail="audit report not found")
    artifact = get_version_artifact(version_id, "label_audit_report.json")
    return {"record": row, "artifact": artifact}


@router.get("/dataset-versions/{version_id}/images")
def list_dataset_images(
    version_id: int,
    split: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
) -> dict:
    conditions = ["dataset_version_id = %s"]
    params: list = [version_id]
    if split:
        conditions.append("split = %s")
        params.append(split)
    if status:
        conditions.append("annotation_status = %s")
        params.append(status)

    where = " AND ".join(conditions)
    total_row = fetch_one(f"SELECT COUNT(*) AS c FROM image_items WHERE {where}", tuple(params))
    total = total_row["c"] if total_row else 0

    offset = (page - 1) * page_size
    rows = fetch_all(
        f"SELECT * FROM image_items WHERE {where} ORDER BY id ASC LIMIT %s OFFSET %s",
        tuple(params + [page_size, offset]),
    )
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


# ---- 类别配置 ----

@router.get("/dataset-versions/{version_id}/class-config")
def get_class_config(version_id: int) -> dict:
    from app.dataset.version_metadata import get_dataset_version_class_config
    try:
        return get_dataset_version_class_config(version_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/dataset-versions/{version_id}/class-config")
def update_class_config(version_id: int, payload: dict) -> dict:
    from app.dataset.version_metadata import update_dataset_version_classes
    raw_class_names = payload.get("class_names") or payload.get("class_text", "")
    try:
        return update_dataset_version_classes(version_id, raw_class_names)
    except ValueError as exc:
        status = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.get("/dataset-versions/{version_id}/ai-quality")
def get_dataset_ai_quality(
    version_id: int,
    checks: str = Query(default="quality,duplicates", description="逗号分隔: quality,duplicates,consistency"),
):
    """对数据集运行 AI 辅助质量分析（模糊/曝光/重复/标注一致性）。"""
    from app.dataset.ai_quality import analyze_dataset_images
    check_list = [c.strip() for c in checks.split(",") if c.strip()]
    result = analyze_dataset_images(version_id, check_list)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/dataset-versions/{version_id}/images/{image_id}/quality")
def get_single_image_quality(version_id: int, image_id: int):
    """获取单张图片的质量检测结果。"""
    from app.dataset.ai_quality import check_image_quality
    img = fetch_one(
        "SELECT * FROM image_items WHERE id = %s AND dataset_version_id = %s",
        (image_id, version_id),
    )
    if not img:
        raise HTTPException(status_code=404, detail="image not found")
    path = resolve_path(img["image_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="image file not found")
    result = check_image_quality(path)
    result["image_id"] = img["id"]
    result["image_name"] = path.name
    return result
