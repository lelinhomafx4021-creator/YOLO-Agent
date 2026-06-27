import json
from pathlib import Path
from typing import Any

import yaml

from app.annotation.yolo_txt_io import read_yolo_txt
from app.core.config import resolve_path, relative_path
from app.core.database import db, fetch_all, fetch_one

DEFAULT_REVIEW_SUGGESTIONS = [
    "先完成类别配置与图片复核，再导出标准 YOLO 训练/验证/测试集。",
    "正式测试建议使用独立 test 数据，不要只依赖训练集内部分割。",
]


def normalize_class_names(raw: Any) -> list[str]:
    items: list[str] = []
    if isinstance(raw, str):
        text = raw.replace("\r", "\n").replace(",", "\n").replace("，", "\n")
        items = [part.strip() for part in text.split("\n")]
    elif isinstance(raw, dict):
        ordered = sorted(raw.items(), key=lambda item: int(item[0]))
        items = [str(value).strip() for _, value in ordered]
    elif isinstance(raw, (list, tuple)):
        items = [str(value).strip() for value in raw]

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned if cleaned else []


def read_class_names(data_yaml_path: Path) -> list[str]:
    try:
        data = yaml.safe_load(data_yaml_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    return normalize_class_names(data.get("names"))


def write_dataset_yaml(
    data_yaml_path: Path,
    root_path: Path,
    train_value: str,
    val_value: str,
    test_value: str,
    class_names: list[str],
) -> None:
    payload = {
        "path": str(root_path),
        "train": train_value,
        "val": val_value,
        "test": test_value,
        "names": class_names,
    }
    data_yaml_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def refresh_dataset_version_metadata(version_id: int) -> dict[str, Any]:
    version = fetch_one("SELECT * FROM dataset_versions WHERE id = %s", (version_id,))
    if not version:
        raise ValueError("dataset version not found")

    data_yaml_path = resolve_path(version["data_yaml_path"])
    class_names = read_class_names(data_yaml_path)
    rows = fetch_all(
        """
        SELECT annotation_status, split, image_path, label_path
        FROM image_items
        WHERE dataset_version_id = %s
        ORDER BY id ASC
        """,
        (version_id,),
    )

    class_distribution = {name: 0 for name in class_names}
    instance_count = 0
    empty_labels = 0
    pending_count = 0
    reviewed_count = 0
    split_counts: dict[str, int] = {}
    max_class_id = -1

    for row in rows:
        status = row.get("annotation_status") or ""
        if status in {"unlabeled", "ai_prelabel"}:
            pending_count += 1
        if status == "reviewed":
            reviewed_count += 1

        split = row.get("split") or "unspecified"
        split_counts[split] = split_counts.get(split, 0) + 1

        boxes = read_yolo_txt(resolve_path(row["label_path"]))
        if not boxes:
            empty_labels += 1
            continue

        instance_count += len(boxes)
        for box in boxes:
            class_id = int(box.get("class_id", -1))
            max_class_id = max(max_class_id, class_id)
            label = class_names[class_id] if 0 <= class_id < len(class_names) else f"class_{class_id}"
            class_distribution[label] = class_distribution.get(label, 0) + 1

    image_count = len(rows)
    # label_file_count = 有非空标注文件的图片数
    label_file_count = sum(
        1 for r in rows
        if resolve_path(r["label_path"]).exists() and resolve_path(r["label_path"]).read_text(encoding="utf-8").strip()
    )

    audit_payload = {
        "image_count": image_count,
        "label_file_count": label_file_count,
        "instance_count": instance_count,
        "missing_labels": 0,
        "orphan_labels": 0,
        "invalid_bboxes": 0,
        "empty_labels": empty_labels,
        "class_distribution": class_distribution,
        "suggestions": DEFAULT_REVIEW_SUGGESTIONS,
    }

    report_path = _resolve_report_path(version_id, version)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(audit_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with db() as cur:
        cur.execute(
            """
            UPDATE dataset_versions
            SET image_count = %s, label_file_count = %s,
                class_count = %s, instance_count = %s,
                missing_labels = 0, orphan_labels = 0, invalid_bboxes = 0,
                empty_labels = %s,
                class_distribution_json = %s,
                suggestions_json = %s,
                audit_report_path = %s
            WHERE id = %s
            """,
            (
                image_count, label_file_count,
                len(class_names), instance_count,
                empty_labels,
                json.dumps(class_distribution, ensure_ascii=False),
                json.dumps(DEFAULT_REVIEW_SUGGESTIONS, ensure_ascii=False),
                relative_path(report_path),
                version_id,
            ),
        )

    return {
        "version_id": version_id,
        "class_names": class_names,
        "class_count": len(class_names),
        "instance_count": instance_count,
        "pending_count": pending_count,
        "reviewed_count": reviewed_count,
        "split_counts": split_counts,
        "max_class_id": max_class_id,
        "audit_payload": audit_payload,
    }


def update_dataset_version_classes(version_id: int, raw_class_names: Any) -> dict[str, Any]:
    version = fetch_one(
        """
        SELECT dv.*, d.name AS dataset_name
        FROM dataset_versions dv
        JOIN datasets d ON d.id = dv.dataset_id
        WHERE dv.id = %s
        """,
        (version_id,),
    )
    if not version:
        raise ValueError("dataset version not found")

    class_names = normalize_class_names(raw_class_names)
    current = refresh_dataset_version_metadata(version_id)
    if current["max_class_id"] >= len(class_names):
        raise ValueError(
            f"existing labels use class_id {current['max_class_id']}, but only {len(class_names)} classes were provided"
        )

    data_yaml_path = Path(version["data_yaml_path"])
    yaml_data = {}
    if data_yaml_path.exists():
        try:
            yaml_data = yaml.safe_load(data_yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            yaml_data = {}
    write_dataset_yaml(
        data_yaml_path,
        Path(version["root_path"]),
        str(yaml_data.get("train") or "images/train"),
        str(yaml_data.get("val") or "images/val"),
        str(yaml_data.get("test") or "images/test"),
        class_names,
    )
    refreshed = refresh_dataset_version_metadata(version_id)
    refreshed["dataset_name"] = version.get("dataset_name", "")
    refreshed["status"] = version.get("status", "")
    return refreshed


def get_dataset_version_class_config(version_id: int) -> dict[str, Any]:
    version = fetch_one(
        """
        SELECT dv.*, d.name AS dataset_name
        FROM dataset_versions dv
        JOIN datasets d ON d.id = dv.dataset_id
        WHERE dv.id = %s
        """,
        (version_id,),
    )
    if not version:
        raise ValueError("dataset version not found")

    refreshed = refresh_dataset_version_metadata(version_id)
    refreshed.update(
        {
            "dataset_id": version["dataset_id"],
            "dataset_name": version.get("dataset_name", ""),
            "version": version.get("version", ""),
            "status": version.get("status", ""),
            "image_count": version.get("image_count", 0),
        }
    )
    return refreshed


def _resolve_report_path(version_id: int, version: dict[str, Any]) -> Path:
    if version.get("audit_report_path"):
        return resolve_path(version["audit_report_path"])
    return resolve_path(version["root_path"]) / "label_audit_report.json"
