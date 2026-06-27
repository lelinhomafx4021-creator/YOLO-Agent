#!/usr/bin/env python3
"""
Seed demo data: "安全帽检测" (Helmet Detection) dataset.

Creates:
  - A project named "安全帽检测"
  - A dataset named "安全帽检测" (2 classes: helmet, no_helmet)
  - 10 synthetic 640x480 blank-blue PNG images with random colored rectangles
  - Corresponding YOLO .txt labels
  - data.yaml configuration
  - Imports the dataset through the standard import pipeline (copy, audit,
    fingerprint, manifest, DB insert, label-issue creation)
  - Binds the dataset version to the project

Idempotent: safe to re-run.  Existing records are detected and skipped.
Uses PIL/Pillow for image generation, PyYAML for data.yaml, and the
existing app.importer module so the result is identical to a real upload.
"""

import os
import sys
import random
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Respect the environment — default to sqlite if DB_BACKEND is not set
# so the script works both with and without PostgreSQL.
# ---------------------------------------------------------------------------
os.environ.setdefault("DB_BACKEND", "postgres")

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import db, fetch_all, fetch_one, utc_now, init_db
from app.dataset.importer import create_dataset, import_yolo_dataset
from app.dataset.version_metadata import write_dataset_yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CLASS_NAMES = ["helmet", "no_helmet"]
CLASS_NAMES_CN = ["安全帽", "无安全帽"]
PROJECT_NAME = "安全帽检测"
DATASET_NAME = "安全帽检测"
IMAGE_COUNT = 10
IMAGE_W, IMAGE_H = 640, 480

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("ERROR: PIL (Pillow) is required.  Install with: pip install Pillow")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _ensure_project(name: str, description: str) -> dict:
    """Return existing project or create a new one."""
    existing = fetch_one("SELECT * FROM projects WHERE name = %s", (name,))
    if existing:
        print(f"  [SKIP] Project '{name}' already exists (id={existing['id']})")
        return existing

    now = utc_now()
    with db() as cur:
        cur.execute(
            "INSERT INTO projects (name, description, task_type, status, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (name, description, "detect", "active", now, now),
        )
        row = cur.execute("SELECT * FROM projects WHERE name = %s", (name,)).fetchone()
        project = dict(row)
    print(f"  [CREATE] Project '{name}' (id={project['id']})")
    return project


def _ensure_dataset(name: str, description: str) -> int:
    """Return existing dataset id or create a new dataset."""
    existing = fetch_one("SELECT * FROM datasets WHERE name = %s", (name,))
    if existing:
        print(f"  [SKIP] Dataset '{name}' already exists (id={existing['id']})")
        return existing["id"]

    ds = create_dataset(name, description)
    print(f"  [CREATE] Dataset '{name}' (id={ds['id']})")
    return ds["id"]


def _generate_synthetic_dataset(target_dir: Path) -> None:
    """Create a YOLO-format dataset under *target_dir* with synthetic images."""
    images_train = target_dir / "images" / "train"
    labels_train = target_dir / "labels" / "train"
    images_train.mkdir(parents=True, exist_ok=True)
    labels_train.mkdir(parents=True, exist_ok=True)

    rng = random.Random(42)  # fixed seed for reproducibility

    for i in range(1, IMAGE_COUNT + 1):
        # Blank blue canvas
        img = Image.new("RGB", (IMAGE_W, IMAGE_H), (100, 150, 200))
        draw = ImageDraw.Draw(img)
        boxes: list[str] = []

        # 1-4 random rectangles per image
        for _ in range(rng.randint(1, 4)):
            class_id = rng.randint(0, len(CLASS_NAMES) - 1)

            x1 = rng.randint(10, IMAGE_W - 60)
            y1 = rng.randint(10, IMAGE_H - 60)
            bw = rng.randint(30, 120)
            bh = rng.randint(30, 120)
            x2 = min(x1 + bw, IMAGE_W - 1)
            y2 = min(y1 + bh, IMAGE_H - 1)
            bw_actual = x2 - x1
            bh_actual = y2 - y1
            if bw_actual < 5 or bh_actual < 5:
                continue

            # Random fill colour with white outline
            color = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
            draw.rectangle([x1, y1, x2, y2], fill=color, outline="white")

            # YOLO-normalised coordinates
            cx = ((x1 + x2) / 2.0) / IMAGE_W
            cy = ((y1 + y2) / 2.0) / IMAGE_H
            nw = bw_actual / IMAGE_W
            nh = bh_actual / IMAGE_H
            boxes.append(f"{class_id} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")

        stem = f"syn_{i:04d}"
        img.save(images_train / f"{stem}.png", "PNG")

        lbl_path = labels_train / f"{stem}.txt"
        lbl_path.write_text("\n".join(boxes) + ("\n" if boxes else ""), encoding="utf-8")

    # Write data.yaml via the project's own helper (same format as real imports)
    write_dataset_yaml(
        target_dir / "data.yaml",
        target_dir,
        "images/train",
        "images/train",
        "images/train",
        CLASS_NAMES,
    )

    print(f"  [GEN] {IMAGE_COUNT} synthetic images + labels -> {target_dir}")


def _import_dataset_version(dataset_id: int, source_path: Path) -> dict:
    """Import via the standard importer pipeline (copy, audit, DB insert)."""
    version = import_yolo_dataset(dataset_id, source_path)
    print(f"  [IMPORT] Version {version['version']} (id={version['id']})")
    return version


def _bind_project_version(project_id: int, version_id: int) -> None:
    """Insert a project-dataset-version binding if it does not exist."""
    existing = fetch_one(
        "SELECT * FROM project_dataset_bindings "
        "WHERE project_id = %s AND dataset_version_id = %s",
        (project_id, version_id),
    )
    if existing:
        print(f"  [SKIP] Binding already exists (id={existing['id']})")
        return

    now = utc_now()
    with db() as cur:
        cur.execute(
            "INSERT INTO project_dataset_bindings "
            "(project_id, dataset_version_id, role, source_split, note, is_active, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (project_id, version_id, "train", "train", "种子数据演示训练集", 1, now),
        )
    print(f"  [CREATE] Binding project={project_id} <-> version={version_id}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 60)
    print("  种子数据: 安全帽检测 (Helmet Detection)")
    print("=" * 60)

    # Ensure all DB tables exist (calls SQLModel.metadata.create_all internally)
    init_db()

    # ---- 1. Project --------------------------------------------------------
    print("\n[1/4] 项目")
    project = _ensure_project(
        PROJECT_NAME,
        "安全帽检测 demo 项目，包含 helmet（安全帽）和 no_helmet（无安全帽）两个类别。",
    )

    # ---- 2. Dataset --------------------------------------------------------
    print("\n[2/4] 数据集")
    dataset_id = _ensure_dataset(
        DATASET_NAME,
        "安全帽检测数据集，10 张合成图片，含 helmet / no_helmet 标注。",
    )

    # ---- 3. Import version ------------------------------------------------
    print("\n[3/4] 导入版本")
    versions = fetch_all(
        "SELECT * FROM dataset_versions WHERE dataset_id = %s",
        (dataset_id,),
    )
    if versions:
        version = versions[0]
        print(f"  [SKIP] Version {version['version']} already imported (id={version['id']})")
        version_id = version["id"]
    else:
        # Generate dataset in a temporary directory; the importer copies it to
        # DATASETS_DIR/<name>/<version> so the temp can be safely discarded.
        with tempfile.TemporaryDirectory(prefix="yolops_seed_") as tmp:
            tmp_path = Path(tmp)
            _generate_synthetic_dataset(tmp_path)
            version = _import_dataset_version(dataset_id, tmp_path)
            version_id = version["id"]

    # ---- 4. Project binding ------------------------------------------------
    print("\n[4/4] 绑定项目与数据集")
    _bind_project_version(project["id"], version_id)

    print("\n" + "=" * 60)
    print("  完成! 数据已就绪。")
    print("=" * 60)
    print(f"  项目           : {PROJECT_NAME}")
    print(f"  数据集         : {DATASET_NAME}")
    print(f"  类别           : {', '.join(f'{a}({b})' for a, b in zip(CLASS_NAMES, CLASS_NAMES_CN))}")
    print(f"  合成图片数     : {IMAGE_COUNT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
