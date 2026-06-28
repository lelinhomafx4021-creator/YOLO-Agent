import re
from pathlib import Path


_WEIGHT_SUFFIXES = (".pt", ".onnx", ".engine", ".torchscript", ".yaml", ".tflite")
_DEFAULT_TRAINING_NAME_RE = re.compile(r"^\u8bad\u7ec3\s*\d+$")
_TRAINING_SEQUENCE_RE = re.compile(r"\u8bad\u7ec3\s*(\d+)$")


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _base_stem(value: object) -> str:
    raw = str(value or "").replace("\\", "/")
    stem = Path(raw).name or raw
    for suffix in _WEIGHT_SUFFIXES:
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return stem or "model"


def build_training_run_id(project_name: str, sequence: int, created_at: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", _normalize_text(project_name).lower()).strip("-")
    if not token:
        token = "project"
    stamp = "".join(ch for ch in str(created_at or "") if ch.isdigit())[:12]
    return f"{token}-t{int(sequence):02d}-{stamp or 'run'}"


def _prefix_project_name(project_name: object, label: object) -> str:
    project = _normalize_text(project_name)
    name = _normalize_text(label)
    if not project or not name or name.startswith(f"{project} / "):
        return name
    return f"{project} / {name}"


def build_training_display_name(project_name: str | None, sequence: int, explicit_name: str | None = None) -> str:
    name = _normalize_text(explicit_name) or "\u8bad\u7ec3 " + str(int(sequence))
    if explicit_name and not _DEFAULT_TRAINING_NAME_RE.match(name):
        return name
    return _prefix_project_name(project_name, name)


def _extract_training_sequence(label: object, fallback: object = None) -> int | None:
    text = _normalize_text(label)
    match = _TRAINING_SEQUENCE_RE.search(text)
    if match:
        return int(match.group(1))
    try:
        if fallback is not None:
            return int(fallback)
    except (TypeError, ValueError):
        return None
    return None


def _project_name_from_training_label(label: object) -> str:
    text = _normalize_text(label)
    if " / " not in text:
        return ""
    return text.rsplit(" / ", 1)[0].strip()


def build_training_model_display_name(project_name: object, sequence: object, fallback_label: object = None) -> str:
    seq = _extract_training_sequence(fallback_label, sequence)
    project = _normalize_text(project_name) or _project_name_from_training_label(fallback_label)
    if seq is not None:
        return f"{project}-\u8bad\u7ec3\u3010{seq}\u3011" if project else f"\u8bad\u7ec3\u3010{seq}\u3011"
    fallback = _normalize_text(fallback_label)
    if project and fallback.startswith(f"{project} / "):
        fallback = fallback[len(project) + 3 :]
    return f"{project}-{fallback}" if project and fallback else fallback or project or "model"


def infer_model_source_type(row: dict) -> str:
    run_id = _normalize_text(row.get("run_id"))
    if run_id.startswith("import_"):
        return "imported"
    if run_id.startswith("export_"):
        return "exported"
    return "training"


def source_type_label(source_type: str) -> str:
    return {
        "training": "\u8bad\u7ec3\u4ea7\u51fa",
        "imported": "\u5916\u90e8\u5bfc\u5165",
        "exported": "\u5bfc\u51fa\u6a21\u578b",
    }.get(source_type, "\u6a21\u578b\u8bb0\u5f55")


def dataset_display_name(row: dict) -> str:
    dataset_name = _normalize_text(row.get("dataset_name") or row.get("model_dataset_name"))
    version = _normalize_text(row.get("dataset_version_name") or row.get("dataset_version") or row.get("version"))
    if dataset_name and version:
        return f"{dataset_name} / {version}"
    return dataset_name or version or "-"


def safe_training_display_name(row: dict) -> str:
    explicit = _normalize_text(row.get("display_name") or row.get("training_display_name"))
    if explicit:
        if _DEFAULT_TRAINING_NAME_RE.match(explicit):
            return _prefix_project_name(row.get("project_name"), explicit)
        return explicit
    if row.get("id"):
        return build_training_display_name(row.get("project_name"), int(row["id"]))
    run_id = _normalize_text(row.get("run_id"))
    return run_id or "-"


def safe_model_display_name(row: dict) -> str:
    explicit = _normalize_text(row.get("model_name") or row.get("display_model_name") or row.get("model_display_name"))
    fmt = _normalize_text(row.get("model_format")).upper()
    source_type = infer_model_source_type(row)

    if source_type == "training":
        training_name = safe_training_display_name(
            {
                "display_name": row.get("source_training_display_name") or row.get("training_display_name"),
                "id": row.get("training_run_id"),
                "run_id": row.get("source_training_run_id") or row.get("run_id"),
                "project_name": row.get("project_name"),
            }
        )
        name = build_training_model_display_name(row.get("project_name"), row.get("training_run_id"), training_name)
    elif explicit and "/" not in explicit and not explicit.lower().endswith(_WEIGHT_SUFFIXES):
        name = explicit
    elif source_type == "imported":
        stem = _base_stem(explicit or row.get("best_pt_path") or row.get("base_model") or row.get("run_id"))
        name = f"\u5bfc\u5165\u6a21\u578b / {stem}"
    else:
        stem = _base_stem(explicit or row.get("best_pt_path") or row.get("run_id"))
        name = f"\u5bfc\u51fa\u6a21\u578b / {stem}"

    if fmt and fmt != "YOLO" and f"[{fmt}]" not in name:
        name = f"{name} [{fmt}]"
    return name


def decorate_training_run(row: dict) -> dict:
    item = dict(row)
    item["training_display_name"] = safe_training_display_name(item)
    item["dataset_display_name"] = dataset_display_name(item)
    item["technical_run_id"] = _normalize_text(item.get("run_id"))
    output_name = _normalize_text(item.get("output_model_display_name") or item.get("display_model_name"))
    if not output_name and (item.get("model_name") or item.get("model_run_id")):
        output_name = safe_model_display_name(
            {
                "model_name": item.get("model_name"),
                "run_id": item.get("model_run_id") or item.get("run_id"),
                "dataset_name": item.get("dataset_name"),
                "dataset_version": item.get("dataset_version_name") or item.get("dataset_version"),
                "base_model": item.get("model_base_model") or item.get("base_model"),
                "model_format": item.get("model_format"),
                "training_display_name": item["training_display_name"],
                "training_run_id": item.get("id"),
                "project_name": item.get("project_name"),
            }
        )
    item["output_model_display_name"] = output_name or ""
    return item


def decorate_model(row: dict) -> dict:
    item = dict(row)
    item["source_type"] = infer_model_source_type(item)
    item["source_type_label"] = source_type_label(item["source_type"])
    item["dataset_display_name"] = dataset_display_name(item)
    item["source_training_display_name"] = safe_training_display_name(
        {
            "display_name": item.get("source_training_display_name"),
            "id": item.get("training_run_id"),
            "run_id": item.get("run_id"),
            "project_name": item.get("project_name"),
        }
    ) if item["source_type"] == "training" else ""
    item["model_display_name"] = safe_model_display_name(item)
    item["display_model_name"] = item["model_display_name"]
    return item


def decorate_evaluation_run(row: dict) -> dict:
    item = dict(row)
    item["dataset_display_name"] = dataset_display_name(item)
    item["model_display_name"] = safe_model_display_name(
        {
            "model_name": item.get("model_name"),
            "run_id": item.get("model_run_id"),
            "dataset_name": item.get("model_dataset_name") or item.get("dataset_name"),
            "dataset_version": item.get("model_dataset_version") or item.get("dataset_version_name"),
            "base_model": item.get("model_base_model"),
            "model_format": item.get("model_format"),
            "source_training_display_name": item.get("source_training_display_name"),
            "training_run_id": item.get("training_run_id"),
            "project_name": item.get("project_name"),
        }
    )
    return item
