"""
数据集统计与工具函数模块。

该模块提供了数据集目录结构的遍历、标签路径解析、数据 YAML 文件加载，
以及目录指纹计算等基础工具函数。这些函数主要用于 YOLO 格式数据集的
预处理、校验和统计场景。
"""

import hashlib  # 用于计算目录指纹的 SHA-256 哈希摘要
from pathlib import Path  # 跨平台路径处理

import yaml  # 用于解析 data.yaml 配置文件

from app.core.config import IMAGE_EXTENSIONS  # 项目中定义的允许图片扩展名集合


def load_data_yaml(path: Path) -> dict:
    """
    加载并解析 data.yaml 文件。

    读取 YOLO 格式训练所需的 data.yaml 配置文件，返回其内容字典。
    如果配置中的 names 字段是字典（类 ID -> 名称映射），则将其转换为
    按类 ID 升序排列的名称列表。

    Args:
        path: data.yaml 文件的路径。

    Returns:
        解析后的字典，必须包含非空的 names 列表。

    Raises:
        FileNotFoundError: 文件不存在时抛出。
        ValueError: names 字段缺失、不是列表或为空时抛出。
    """
    # 检查文件是否存在，不存在则直接报错
    if not path.exists():
        raise FileNotFoundError(f"data.yaml not found: {path}")
    # 以 UTF-8 编码打开并解析 YAML 文件，空文件返回空字典
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    names = data.get("names", [])
    # 如果 names 是字典（如 {0: "person", 1: "car"}），按 key 排序后转成列表
    if isinstance(names, dict):
        data["names"] = [names[key] for key in sorted(names.keys(), key=lambda x: int(x))]
    # 校验 names 字段必须为非空列表
    if not isinstance(data.get("names"), list) or not data["names"]:
        raise ValueError("data.yaml must contain non-empty names list")
    return data


def iter_images(root: Path):
    """
    递归遍历目录下所有图片文件。

    使用后缀名匹配 IMAGE_EXTENSIONS 中定义的扩展名（如 .jpg, .png 等），
    逐张 yield 图片路径。适用于数据集图片目录的批量扫描。

    Args:
        root: 要搜索的根目录路径。

    Yields:
        匹配的图片文件路径（Path 对象）。
    """
    # 递归遍历根目录下的所有文件
    for path in root.rglob("*"):
        # 仅保留文件且后缀名属于允许的图片扩展名集合
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            yield path


def label_path_for_image(version_root: Path, image_path: Path) -> Path:
    """
    根据图片路径推导对应的标签文件路径。

    将图片在 images/ 下的相对位置映射到 labels/ 目录下，并将后缀替换为 .txt。
    例如：version_root/images/train/0001.jpg -> version_root/labels/train/0001.txt

    Args:
        version_root: 数据集版本根目录（包含 images/ 和 labels/ 子目录）。
        image_path: 图片文件的完整路径。

    Returns:
        对应的标签文件路径。
    """
    # 计算图片相对于 images/ 目录的路径，如 "train/0001.jpg"
    rel = image_path.relative_to(version_root / "images")
    # 将 images/ 替换为 labels/，并将后缀改为 .txt
    return version_root / "labels" / rel.with_suffix(".txt")


def split_for_image(version_root: Path, image_path: Path) -> str:
    """
    获取图片所属的数据集划分名称。

    通过图片路径相对于 images/ 目录的第一级子目录名来确定划分，
    例如：images/train/0001.jpg -> "train"。

    Args:
        version_root: 数据集版本根目录（包含 images/ 子目录）。
        image_path: 图片文件的完整路径。

    Returns:
        划分名称字符串（如 "train", "val", "test"）；若无法确定则返回 "unknown"。
    """
    # 计算图片相对于 images/ 目录的路径
    rel = image_path.relative_to(version_root / "images")
    # 取路径的第一级（如 train/val/test）作为划分名称，若为空则返回 unknown
    return rel.parts[0] if rel.parts else "unknown"


def fingerprint_directory(root: Path) -> str:
    """
    计算目录内容的 SHA-256 指纹。

    遍历目录下所有文件，对每个文件的相对路径、文件大小和最后修改时间
    进行哈希计算，生成一个唯一摘要。可用于检测目录内容是否发生变化。

    注意：只依赖文件的元数据（路径、大小、mtime），不读取文件内容，
    适用于快速变更检测场景。

    Args:
        root: 要计算指纹的根目录路径。

    Returns:
        四十位的十六进制 SHA-256 摘要字符串。
    """
    # 创建 SHA-256 哈希对象
    digest = hashlib.sha256()
    # 对所有文件按路径排序后逐个处理，确保指纹可复现
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        # 将绝对路径转为相对于 root 的 POSIX 风格路径字符串
        rel = path.relative_to(root).as_posix()
        stat = path.stat()
        # 将相对路径、文件大小和最后修改时间依次喂入哈希计算
        digest.update(rel.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(int(stat.st_mtime)).encode("ascii"))
    # 返回 64 位十六进制摘要字符串
    return digest.hexdigest()
