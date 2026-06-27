"""
YOLO TXT 标注文件验证器

本模块提供 YOLO 格式数据集标注文件的校验功能，包括：
- 解析单个标签文件，逐行校验格式、数值范围、重复边界框等
- 审计整个数据集版本（训练/验证集），统计缺失标签、孤儿标签文件、无效边界框等
- 输出审计报告（JSON 格式），附带不平衡检测和处理建议

依赖：
    - app.core.config.IMAGE_EXTENSIONS : 支持的图片扩展名列表
    - app.dataset.statistics            : 图片遍历、标签路径推导、数据集拆分判断
"""

import json  # JSON 序列化/反序列化，用于输出审计报告
from collections import Counter  # 计数器，用于统计类别分布和拆分计数
from pathlib import Path  # 跨平台路径操作
from typing import Any  # 类型注解，用于任意类型的字典值

from app.core.config import IMAGE_EXTENSIONS  # 支持的图片扩展名（如 .jpg, .png）
from app.dataset.statistics import iter_images, label_path_for_image, split_for_image  # 数据集的图片遍历、标签路径推导、拆分识别


def parse_label_file(path: Path, class_count: int) -> tuple[list[dict[str, Any]], list[str]]:
    """
    解析一个 YOLO 格式的标签文件（*.txt）。

    YOLO 标签每行格式：<class_id> <x_center> <y_center> <width> <height>
    所有坐标值均为归一化到 [0, 1] 的浮点数。

    参数:
        path:        标签文件路径
        class_count: 数据集总类别数，用于校验 class_id 是否越界

    返回:
        (boxes, errors) 元组：
            boxes:  有效边界框列表，每个元素为字典
                    {"class_id": int, "x_center": float, "y_center": float, "width": float, "height": float}
            errors: 错误信息列表，每个字符串描述一行的问题
    """
    boxes: list[dict[str, Any]] = []
    errors: list[str] = []

    # 文件不存在或为空的情况：分别返回 "missing_label" 或 "empty_label" 标记
    if not path.exists():
        return boxes, ["missing_label"]
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return boxes, ["empty_label"]

    seen = set()  # 用于检测重复的边界框（基于精确到 5 位小数的坐标）

    # 逐行解析标签文件
    for line_no, line in enumerate(text.splitlines(), start=1):
        parts = line.split()
        # 每行必须恰好 5 列：class_id + 4 个坐标值（x_center, y_center, width, height）
        if len(parts) != 5:
            errors.append(f"line_{line_no}: expected 5 columns")
            continue

        # 解析数值，捕获转换异常（如空字符串、非数字字符等）
        try:
            class_id = int(parts[0])
            x, y, w, h = [float(v) for v in parts[1:]]
        except ValueError:
            errors.append(f"line_{line_no}: invalid numeric value")
            continue

        # 类别 ID 必须在 [0, class_count) 范围内，越界说明标注类别不存在于数据集中
        if class_id < 0 or class_id >= class_count:
            errors.append(f"line_{line_no}: class_id out of range")

        # 归一化坐标必须在 [0, 1] 范围内，超出说明坐标值异常
        if not all(0 <= v <= 1 for v in (x, y, w, h)):
            errors.append(f"line_{line_no}: bbox value out of [0, 1]")

        # 宽度和高度必须为正数，否则边界框无实际面积
        if w <= 0 or h <= 0:
            errors.append(f"line_{line_no}: bbox width/height must be positive")

        # 面积过小的边界框（面积 < 0.00005）视为无效，可能是标注错误或噪声
        if w * h < 0.00005:
            errors.append(f"line_{line_no}: bbox too small")

        # 检查完全重复的边界框（坐标四舍五入到 5 位小数后比较），避免重复计数
        key = (class_id, round(x, 5), round(y, 5), round(w, 5), round(h, 5))
        if key in seen:
            errors.append(f"line_{line_no}: duplicated bbox")
        seen.add(key)

        # 记录有效边界框
        boxes.append({"class_id": class_id, "x_center": x, "y_center": y, "width": w, "height": h})

    return boxes, errors


def audit_yolo_dataset(version_root: Path, classes: list[str]) -> dict[str, Any]:
    """
    审计 YOLO 数据集的一个版本（例如 train 或 val 目录）。

    遍历指定版本根目录下的所有图片，逐一检查对应的标签文件，
    统计缺失标签、孤儿标签、无效边界框等信息，并生成审计报告。

    参数:
        version_root: 数据集版本的根路径，通常包含 images/ 和 labels/ 子目录
        classes:      类别名称列表，index 对应 class_id

    返回:
        包含以下键的字典：
            - image_count       : 图片总数
            - label_file_count  : 标签文件总数
            - instance_count    : 有效标注实例总数
            - missing_label_images : 缺少标签文件的图片路径列表（最多 200 条）
            - orphan_label_files   : 无对应图片的孤儿标签文件路径列表（最多 200 条）
            - invalid_items        : 包含无效边界框的标签文件列表（最多 200 条）
            - empty_label_files    : 内容为空的标签文件路径列表（最多 200 条）
            - missing_labels  : 缺少标签的图片数
            - orphan_labels   : 孤儿标签文件数
            - invalid_bboxes  : 无效边界框总数（各文件错误数之和）
            - empty_labels    : 空标签文件数
            - split_counts    : 训练/验证等拆分计数
            - class_distribution : 每个类别的实例数分布
            - suggestions     : 基于审计结果给出的处理建议列表
    """
    class_count = len(classes)
    images_root = version_root / "images"
    labels_root = version_root / "labels"

    # 收集所有图片路径，以及 labels/ 目录下所有 .txt 标签文件路径
    image_paths = list(iter_images(images_root))
    label_paths = [p for p in labels_root.rglob("*.txt") if p.is_file()] if labels_root.exists() else []

    # 根据图片路径推导期望的标签路径集合，与实际存在的标签路径集合做差集，
    # 从而找出缺少标签的图片（expected - actual）和孤儿标签（actual - expected）
    expected_labels = {label_path_for_image(version_root, img).resolve() for img in image_paths}
    actual_labels = {p.resolve() for p in label_paths}

    # 初始化各类统计容器
    missing_label_images: list[str] = []
    orphan_label_files: list[str] = []
    invalid_items: list[dict[str, Any]] = []
    empty_label_files: list[str] = []
    split_counts: Counter[str] = Counter()        # 统计各拆分（train/val/test）的图片数
    class_distribution: Counter[str] = Counter()  # 统计每个类别的实例数
    instance_count = 0

    # 逐张图片校验标签
    for image_path in image_paths:
        # 记录图片所属的拆分（训练集、验证集或测试集），通过目录结构识别
        split_counts[split_for_image(version_root, image_path)] += 1

        # 推导对应的标签文件路径，并检查是否存在
        label_path = label_path_for_image(version_root, image_path)
        if not label_path.exists():
            # 标签文件不存在：记录为缺失标签的图片
            missing_label_images.append(image_path.relative_to(version_root).as_posix())
            continue

        # 解析标签文件并收集错误
        boxes, errors = parse_label_file(label_path, class_count)

        # 空标签文件单独统计（文件存在但没有内容）
        if "empty_label" in errors:
            empty_label_files.append(label_path.relative_to(version_root).as_posix())

        # "empty_label" 已单独统计，其他格式/数值错误才计入 invalid_items
        meaningful_errors = [e for e in errors if e not in {"empty_label"}]
        if meaningful_errors:
            invalid_items.append({
                "label_path": label_path.relative_to(version_root).as_posix(),
                "errors": meaningful_errors,
            })

        # 累加类别分布统计：遍历有效边界框，按 class_id 映射到类别名称进行计数
        for box in boxes:
            if 0 <= box["class_id"] < class_count:
                class_distribution[classes[box["class_id"]]] += 1
                instance_count += 1

    # 找出那些存在标签文件但没有对应图片的孤儿标签（实际存在但非期望的标签文件）
    for label_path in sorted(actual_labels - expected_labels):
        orphan_label_files.append(Path(label_path).relative_to(version_root).as_posix())

    # 根据审计结果生成处理建议
    suggestions: list[str] = []
    if missing_label_images:
        suggestions.append(f"{len(missing_label_images)} images have no label file; decide whether they are negative samples.")
    if orphan_label_files:
        suggestions.append(f"{len(orphan_label_files)} label files have no matching image; remove or relink them.")
    if invalid_items:
        suggestions.append(f"{len(invalid_items)} label files contain invalid bbox/class rows; fix before training.")
    if class_distribution:
        counts = class_distribution.values()
        min_count, max_count = min(counts), max(counts)
        # 不平衡检测：如果某个类别实例数为 0，或最大类别数是最小类别数的 5 倍以上，认为分布不平衡
        if min_count == 0 or max_count / max(min_count, 1) >= 5:
            suggestions.append("Class distribution is imbalanced; collect or augment minority classes before serious training.")
    else:
        # 没有任何有效标注实例，数据集无法用于训练检测器
        suggestions.append("No object instances found; dataset cannot train a detector yet.")

    # 组装最终审计报告
    return {
        "image_count": len(image_paths),
        "label_file_count": len(label_paths),
        "instance_count": instance_count,
        "missing_label_images": missing_label_images[:200],  # 限制输出条目数，避免报告过大
        "orphan_label_files": orphan_label_files[:200],
        "invalid_items": invalid_items[:200],
        "empty_label_files": empty_label_files[:200],
        "missing_labels": len(missing_label_images),
        "orphan_labels": len(orphan_label_files),
        "invalid_bboxes": sum(len(item["errors"]) for item in invalid_items),
        "empty_labels": len(empty_label_files),
        "split_counts": dict(split_counts),
        "class_distribution": {name: class_distribution.get(name, 0) for name in classes},
        "suggestions": suggestions,
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    """
    将字典数据以格式化的 JSON 写入文件。

    自动创建父目录（如果不存在），使用 UTF-8 编码，
    并确保非 ASCII 字符不被转义（ensure_ascii=False），
    以便中文等字符在 JSON 文件中直接显示。

    参数:
        path: 输出文件路径
        data: 要写入的字典数据
    """
    # 确保目标目录存在，如果父目录不存在则自动递归创建
    path.parent.mkdir(parents=True, exist_ok=True)
    # 以格式化 JSON 写入文件，indent=2 提供可读性较好的缩进
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
