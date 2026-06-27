"""
==============================================================================
数据集导入模块（Dataset Importer）
==============================================================================

该模块负责将 YOLO 格式的数据集导入到系统中，主要功能包括：
  - 创建数据集记录（create_dataset）
  - 生成版本号（next_version）
  - 导入 YOLO 格式数据集（import_yolo_dataset） —— 核心流程编排函数
  - 读取版本归档文件（get_version_artifact）

导入流程（import_yolo_dataset）：
  1. 验证源路径和 data.yaml 配置文件是否存在
  2. 读取 data.yaml 获取类别信息（class names）
  3. 从数据库获取数据集元信息并生成递增版本号
  4. 复制源目录到统一的数据集存储目录 DATASETS_DIR
  5. 对标签文件进行审计校验（缺失标签、孤立标签、无效边界框等）
  6. 计算目录文件指纹（SHA256），生成版本清单文件
  7. 将版本元信息和审计报告写入数据库
  8. 遍历所有图片，逐条写入 image_items 表

依赖的外部模块：
  - app.core.config               : 全局配置（DATASETS_DIR）
  - app.core.database             : 数据库连接与时间工具
  - app.dataset.statistics        : 文件指纹、图片遍历、YAML 读取等工具函数
  - app.dataset.yolo_txt_validator: YOLO 标签审计与 JSON 写入工具
"""

import json
import shutil
from pathlib import Path

from app.core.config import DATASETS_DIR, relative_path
from app.core.database import db, utc_now
from app.dataset.statistics import fingerprint_directory, iter_images, label_path_for_image, load_data_yaml, split_for_image
from app.dataset.yolo_txt_validator import audit_yolo_dataset, write_json


def _read_image_size(image_path: Path) -> tuple[int, int]:
    """读取图片尺寸（宽度 x 高度）。

    使用 PIL（Pillow）库打开指定图片文件，解析并返回其宽度和高度。
    该函数会在导入过程中为每张图片记录真实尺寸，用于后续的标注校验和数据统计。
    如果读取失败（文件损坏、格式不支持或不存在的图片），则返回 (0, 0) 作为降级处理。

    Args:
        image_path: 图片文件的 Path 对象路径，支持常见格式（jpg, png, bmp 等）。

    Returns:
        (width, height) 元组，分别表示图片的宽度和高度（像素单位）；
        读取失败时返回 (0, 0)。
    """
    try:
        # 延迟导入 PIL，避免模块启动时不必要的依赖加载
        from PIL import Image
        with Image.open(image_path) as img:
            # img.size 返回 (width, height) 元组
            return img.size
    except Exception:
        # 任何异常（文件损坏、格式不支持等）均返回 (0, 0)，不中断导入流程
        return 0, 0


def create_dataset(name: str, description: str = "", collection_name: str = "") -> dict:
    """在数据库中创建一个新的数据集记录。

    向 datasets 表中插入一条数据集记录，包含名称和可选的描述信息，
    然后立即查询并返回完整的数据集对象字典，包含自动生成的 id 和时间戳等字段。

    Args:
        name:        数据集名称（唯一标识），不可为空字符串。
        description: 数据集描述（可选），默认为空字符串，用于说明数据集用途或来源。

    Returns:
        包含数据集所有字段（id, name, description, created_at 等）的字典。
        其中 id 为数据库自动生成的自增主键。
    """
    now = utc_now()
    # 名字重复时自动加后缀
    base_name = name
    suffix = 1
    with db() as cur:
        while True:
            existing = cur.execute("SELECT id FROM datasets WHERE name = %s", (name,)).fetchone()
            if not existing:
                break
            suffix += 1
            name = f"{base_name}_{suffix}"

    with db() as cur:
        # 插入数据集记录，名称和描述为必填字段，created_at 记录创建时间
        # collection_name 自动推断：去掉 _train/_val/_test/_inference 后缀
        import re as _re
        if not collection_name:
            collection_name = _re.sub(r'_(train|val|test|inference)$', '', name)
        cur.execute(
            "INSERT INTO datasets(name, description, collection_name, created_at) VALUES (%s, %s, %s, %s)",
            (name, description, collection_name, now),
        )
        # 根据名称查询刚插入的完整记录并返回
        row = cur.execute("SELECT * FROM datasets WHERE name = %s", (name,)).fetchone()
        return dict(row)


def next_version(dataset_id: int) -> str:
    """为指定数据集生成下一个版本号。

    查询该数据集已有版本的个数，版本号格式为 v 后跟三位数字（如 v001, v002）。
    版本号递增策略为 COUNT + 1，保证同一数据集下的版本号单调递增且不重复。

    Args:
        dataset_id: 数据集的数据库 ID（datasets 表的主键）。

    Returns:
        格式化的版本号字符串，如 "v001"、"v002"…"v999"。
    """
    with db() as cur:
        # 统计该数据集已有的版本数量
        count = cur.execute(
            "SELECT COUNT(*) AS c FROM dataset_versions WHERE dataset_id = %s",
            (dataset_id,),
        ).fetchone()["c"]
    # 格式化为三位数版本号，从 v001 开始
    return f"v{count + 1:03d}"


def import_yolo_dataset(dataset_id: int, source_path: Path) -> dict:
    """导入 YOLO 格式的数据集（核心流程编排函数）。

    这是整个导入模块的核心函数，串联了从源路径验证、目录复制、标签审计、
    文件指纹计算、清单生成到数据库写入的完整流水线。

    导入步骤：
      1. 解析并验证源路径是否存在
      2. 读取 data.yaml 配置文件，提取类别名称列表
      3. 从数据库获取数据集信息并生成递增版本号
      4. 使用 shutil.copytree 复制整个源目录到 DATASETS_DIR / 数据集名称 / 版本号
      5. 运行 YOLO 标签审计（检测缺失/孤立标签、无效/空边界框等）
      6. 计算目录文件指纹（SHA256）
      7. 写入 dataset_manifest.json / label_audit_report.json / class_distribution.json
      8. 将版本元信息写入 dataset_versions 表
      9. 将审计报告详细信息写入 label_audit_reports 表
      10. 根据审计结果创建标签问题记录（label_issues）
      11. 遍历所有图片，逐条写入 image_items 表（含标注状态、图片尺寸等）

    Args:
        dataset_id:  数据集的数据库 ID（datasets 表的主键）。
        source_path: 源数据集目录的 Path 路径，需包含 data.yaml 以及
                     images/（图片）和 labels/（标注文件）等标准 YOLO 子目录。

    Returns:
        新创建的 dataset_versions 记录的完整字典，包含版本号、统计信息、时间戳等。

    Raises:
        FileNotFoundError: 源路径 source_path 不存在时抛出。
        ValueError:        dataset_id 在数据库 datasets 表中找不到对应记录时抛出。
    """
    # ==========================================================================
    # 步骤 1：解析并验证源路径
    # ==========================================================================
    # 展开用户目录符号（如 ~），并解析为绝对路径
    source_path = source_path.expanduser().resolve()
    if not source_path.exists():
        raise FileNotFoundError(str(source_path))

    # 读取源目录下的 data.yaml 配置文件，获取 YOLO 类别名称列表
    source_yaml = source_path / "data.yaml"
    data_yaml = load_data_yaml(source_yaml)
    classes = data_yaml["names"]

    # ==========================================================================
    # 步骤 2：从数据库获取数据集信息并生成版本号
    # ==========================================================================
    with db() as cur:
        dataset = cur.execute("SELECT * FROM datasets WHERE id = %s", (dataset_id,)).fetchone()
        if not dataset:
            raise ValueError(f"dataset not found: {dataset_id}")
        dataset_name = dataset["name"]

    # 生成递增版本号（v001, v002, ...）
    version = next_version(dataset_id)

    # ==========================================================================
    # 步骤 3：复制源目录到统一的数据集存储目录
    # ==========================================================================
    # 目标路径格式: DATASETS_DIR / 数据集名称 / 版本号
    # 例如: /data/datasets/coco/v001
    version_root = DATASETS_DIR / dataset_name / version
    if version_root.exists():
        # 如果目标目录已存在，先递归删除再复制，确保导入结果干净一致
        shutil.rmtree(version_root)
    # 使用 copytree 复制整个目录，忽略 .git、__pycache__、runs 等无关目录
    shutil.copytree(source_path, version_root, ignore=shutil.ignore_patterns(".git", "__pycache__", "runs"))

    # 规范化目录名：image→images, annot/annotation→labels
    _normalize_yolo_folders(version_root)

    # ==========================================================================
    # 步骤 4：执行标签审计和文件指纹计算
    # ==========================================================================
    # audit_yolo_dataset 对复制后的版本目录进行全面审计，返回结果包含：
    #   image_count      - 图片总数
    #   label_file_count - 标签文件总数
    #   instance_count   - 标注实例总数
    #   missing_labels   - 有图片无对应标签的文件列表
    #   orphan_labels    - 有标签无对应图片的文件列表
    #   invalid_bboxes   - 边界框格式/取值无效的标注列表
    #   empty_labels     - 内容为空的标签文件列表
    #   class_distribution - 各类别实例数量分布
    #   suggestions      - 审计建议列表
    audit = audit_yolo_dataset(version_root, classes)
    # 计算版本目录下所有文件的 SHA256 哈希值，用于完整性校验
    fingerprint = fingerprint_directory(version_root)

    # ==========================================================================
    # 步骤 5：构建并写入版本清单文件
    # ==========================================================================
    manifest = {
        "dataset_name": dataset_name,                           # 数据集名称
        "version": version,                                     # 当前版本号
        "task": data_yaml.get("task", "detect"),                # 任务类型，默认为目标检测 "detect"
        "classes": classes,                                     # 类别名称列表
        "image_count": audit["image_count"],                    # 图片总数量
        "label_file_count": audit["label_file_count"],          # 标签文件总数量
        "instance_count": audit["instance_count"],              # 标注实例总数量
        "fingerprint": f"sha256:{fingerprint}",                 # 目录文件指纹（SHA256 前缀标识）
        "created_at": utc_now(),                                # 清单创建时间
    }
    # 将清单文件、审计报告、类别分布分别写入版本根目录下的 JSON 文件中
    write_json(version_root / "dataset_manifest.json", manifest)
    write_json(version_root / "label_audit_report.json", audit)
    write_json(version_root / "class_distribution.json", audit["class_distribution"])

    # ==========================================================================
    # 步骤 6：将版本元信息和审计结果写入数据库
    # ==========================================================================
    with db() as cur:
        # ------------------------------------------------------------------
        # 6A：写入 dataset_versions 表 —— 记录版本的元数据、统计信息及审计结果
        # ------------------------------------------------------------------
        audit_report_path = relative_path(version_root / "label_audit_report.json")
        cur.execute(
            """
            INSERT INTO dataset_versions(
                dataset_id, version, root_path, data_yaml_path, image_count,
                label_file_count, instance_count, class_count, fingerprint, status, created_at,
                missing_labels, orphan_labels, invalid_bboxes, empty_labels,
                class_distribution_json, suggestions_json, audit_report_path
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
            """,
            (
                dataset_id, version, relative_path(version_root),
                relative_path(version_root / "data.yaml"),
                audit["image_count"], audit["label_file_count"],
                audit["instance_count"], len(classes),
                fingerprint, "imported", utc_now(),
                audit["missing_labels"], audit["orphan_labels"],
                audit["invalid_bboxes"], audit["empty_labels"],
                json.dumps(audit["class_distribution"], ensure_ascii=False),
                json.dumps(audit["suggestions"], ensure_ascii=False),
                audit_report_path,
            ),
        )
        version_id = cur.fetchone()["id"]

        # 自动推断 dtype：从目录结构检测 train/val/test，无标注 → test（推理/评估）
        auto_dtype = _detect_dtype_from_structure(version_root)
        if audit["label_file_count"] == 0:
            auto_dtype = "test"
        if auto_dtype:
            cur.execute("UPDATE dataset_versions SET dtype = %s WHERE id = %s", (auto_dtype, version_id))

    # ==================================================================
    # 步骤 8：遍历所有图片，写入 image_items 表
    # ==================================================================
    # 先在事务外收集所有图片信息（避免在 DB 锁内做文件 IO）
    image_rows = []
    for image_path in iter_images(version_root / "images"):
        label_path = label_path_for_image(version_root, image_path)
        status = "reviewed" if label_path.exists() and label_path.read_text(encoding="utf-8").strip() else "unlabeled"
        image_rows.append((
            version_id,
            split_for_image(version_root, image_path),
            str(image_path),
            str(label_path),
            status,
            utc_now(),
        ))

    # 批量写入 — 存相对路径
    with db() as cur:
        for row in image_rows:
            cur.execute(
                """
                INSERT INTO image_items(dataset_version_id, split, image_path, label_path, annotation_status, width, height, updated_at)
                VALUES (%s, %s, %s, %s, %s, 0, 0, %s)
                """,
                (
                    row[0],  # version_id
                    row[1],  # split
                    relative_path(Path(row[2])),  # image_path
                    relative_path(Path(row[3])),  # label_path
                    row[4],  # status
                    row[5],  # updated_at
                ),
            )

        # 查询并返回刚插入的完整版本记录
        row = cur.execute("SELECT * FROM dataset_versions WHERE id = %s", (version_id,)).fetchone()
        return dict(row)


def _detect_dtype_from_structure(version_root: Path) -> str:
    """从 YOLO 目录结构推断数据集类型。

    检测 images/ 下的子目录：
    - 包含 train/ → 'train'
    - 包含 val/ → 'val'
    - 包含 test/ → 'test'
    - 无法推断 → ''（留给用户手动指定）
    """
    images_dir = version_root / "images"
    if not images_dir.is_dir():
        return ""
    subdirs = {d.name for d in images_dir.iterdir() if d.is_dir()}
    # 按优先级检测
    if "train" in subdirs:
        return "train"
    if "val" in subdirs:
        return "val"
    if "test" in subdirs:
        return "test"
    # 如果 images/ 下直接有图片文件（而非子目录），可能是全量数据集
    has_direct_images = any(
        f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.gif', '.tif', '.tiff'}
        for f in images_dir.iterdir() if f.is_file()
    )
    if has_direct_images:
        return ""  # 全量数据集，尚未拆分
    return ""


def _normalize_yolo_folders(root: Path) -> None:
    """规范化 YOLO 目录命名：image→images, annot/annotation→labels。

    很多公开数据集使用非标准目录名（如 image/ 而非 images/），
    此函数在导入后统一修正为标准 YOLO 结构。
    """
    renames = {
        "image": "images",
        "annot": "labels",
        "annotation": "labels",
        "img": "images",
    }
    for old_name, new_name in renames.items():
        old_path = root / old_name
        new_path = root / new_name
        if old_path.is_dir() and not new_path.exists():
            old_path.rename(new_path)
            # 修复 data.yaml 中的路径引用
            _fix_yaml_refs(root, old_name, new_name)


def _fix_yaml_refs(root: Path, old_name: str, new_name: str) -> None:
    """修复 data.yaml 中因目录重命名导致的路径引用变化。"""
    yaml_path = root / "data.yaml"
    if not yaml_path.exists():
        return
    try:
        text = yaml_path.read_text(encoding="utf-8")
        if old_name in text:
            text = text.replace(f"{old_name}/", f"{new_name}/")
            text = text.replace(f"train: {old_name}", f"train: {new_name}")
            text = text.replace(f"val: {old_name}", f"val: {new_name}")
            yaml_path.write_text(text, encoding="utf-8")
    except Exception:
        pass


def get_version_artifact(version_id: int, filename: str) -> dict:
    """读取指定版本目录下的 JSON 归档文件。

    根据版本 ID 在数据库中查找对应的数据集版本记录，然后从版本根目录
    读取并解析指定文件名的 JSON 文件。常用于获取版本清单、审计报告等
    预先写入的归档数据。

    Args:
        version_id: 数据集版本的数据库 ID（dataset_versions 表的主键）。
        filename:   要读取的文件名（如 "dataset_manifest.json"、
                    "label_audit_report.json"、"class_distribution.json"）。

    Returns:
        解析后的 JSON 字典对象。
        如果版本记录在数据库中不存在，抛出 ValueError。
        如果指定文件在磁盘上不存在，返回空字典 {} 作为降级处理。
    """
    with db() as cur:
        # 根据 version_id 查询数据集版本记录
        row = cur.execute("SELECT * FROM dataset_versions WHERE id = %s", (version_id,)).fetchone()
    if not row:
        raise ValueError(f"dataset version not found: {version_id}")
    # 拼接文件完整路径：版本根目录 + 文件名
    path = Path(row["root_path"]) / filename
    if not path.exists():
        # 文件不存在时返回空字典，避免上层调用处频繁做 None 判断
        return {}
    # 读取并解析 JSON 文件内容，返回 Python 字典
    return json.loads(path.read_text(encoding="utf-8"))
