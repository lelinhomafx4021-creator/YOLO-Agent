"""
训练产出物收集模块

该模块负责在 YOLO 训练任务完成后，收集训练过程中产生的各类产出物（artifacts），
包括：训练结果 CSV/图表、模型权重文件、数据集清单等，并将训练指标持久化到数据库中。

工作流程：
  1. 根据 training_run_id 从数据库查询训练任务和数据集信息
  2. 将训练产出物从运行目录复制到模型注册目录（MODEL_REGISTRY_DIR）
  3. 解析 results.csv 提取最佳 epoch 的各项指标
  4. 将指标写入 metrics.json 并回填到 training_metrics 表
  5. 向 model_versions 表插入一条模型版本记录
"""

import csv
import json
import shutil
from pathlib import Path
from typing import Any

from app.core.config import MODEL_REGISTRY_DIR  # 模型注册目录的全局配置
from app.core.database import db, utc_now  # 数据库连接与 UTC 时间工具


def _last_float(row: dict[str, str], candidates: list[str]) -> float | None:
    """
    从 CSV 字典行的候选字段列表中提取最后一个非空浮点数值。

    遍历 candidates 列表，返回第一个存在于 row 中且值非空的字段的浮点数。
    如果所有候选字段均不存在或无法解析，则返回 None。

    参数:
        row: CSV 行字典，键为列名，值为字符串。
        candidates: 候选字段名列表，按优先级从高到低排列。

    返回:
        解析成功的浮点数，或 None。
    """
    for key in candidates:
        if key in row and row[key] not in {"", None}:
            try:
                return float(row[key])
            except ValueError:
                continue
    return None


def parse_results_csv(path: Path) -> dict[str, Any]:
    """
    解析 YOLO 训练结果 CSV 文件（results.csv），提取最佳 epoch 的评估指标。

    读取 CSV 文件中的所有行，以 mAP50-95 为主要指标选出最佳行，
    返回包含最佳 epoch、精确率、召回率、mAP50、mAP50-95 的字典。

    参数:
        path: results.csv 文件的路径。

    返回:
        包含训练指标的字典，若文件不存在或内容为空则返回空字典。
        键: best_epoch, precision, recall, map50, map50_95, epochs_recorded。
    """
    # 检查文件是否存在
    if not path.exists():
        return {}
    # 使用 csv.DictReader 读取所有行
    with path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    # 如果无数据行则返回空字典
    if not rows:
        return {}
    # 以 mAP50-95 为指标选取最佳 epoch 的行（支持新旧两种列名）
    best_row = max(
        rows,
        key=lambda row: _last_float(row, ["metrics/mAP50-95(B)", "metrics/mAP50-95"]) or -1,
    )
    # 返回提取的各项指标
    return {
        "best_epoch": int(float(best_row.get("epoch", len(rows) - 1))),
        "precision": _last_float(best_row, ["metrics/precision(B)", "metrics/precision"]),
        "recall": _last_float(best_row, ["metrics/recall(B)", "metrics/recall"]),
        "map50": _last_float(best_row, ["metrics/mAP50(B)", "metrics/mAP50"]),
        "map50_95": _last_float(best_row, ["metrics/mAP50-95(B)", "metrics/mAP50-95"]),
        "epochs_recorded": len(rows),
    }


def collect_artifacts(training_run_id: int) -> dict[str, Any]:
    """
    收集指定训练任务的产出物并注册模型版本。

    这是模块的核心函数，执行以下步骤：
      1. 查询训练任务、数据集版本及数据集信息
      2. 在模型注册目录下创建以数据集名 + run_id 命名的子目录
      3. 复制训练产出物（图表、配置文件、权重文件等）到注册目录
      4. 解析 results.csv 生成 metrics.json
      5. 回填每 epoch 的训练指标到 training_metrics 表
      6. 向 model_versions 表插入一条记录并返回该记录

    参数:
        training_run_id: 训练运行记录的主键 ID。

    返回:
        新创建的 model_versions 表记录字典。
    """
    # ---- 1. 从数据库查询训练任务和数据集信息 ----
    with db() as cur:
        run_row = cur.execute("SELECT * FROM training_runs WHERE id = %s", (training_run_id,)).fetchone()
        if not run_row:
            raise ValueError(f"training run not found: {training_run_id}")
        run = dict(run_row)
        ver_row = cur.execute("SELECT * FROM dataset_versions WHERE id = %s", (run["dataset_version_id"],)).fetchone()
        if not ver_row:
            raise ValueError(f"dataset version not found: {run['dataset_version_id']}")
        version = dict(ver_row)
        ds_row = cur.execute("SELECT * FROM datasets WHERE id = %s", (version["dataset_id"],)).fetchone()
        if not ds_row:
            raise ValueError(f"dataset not found: {version['dataset_id']}")
        dataset = dict(ds_row)

    # ---- 2. 确定源路径和目标路径 ----
    run_path = Path(run["run_path"])  # 训练产出的源目录
    # 目标注册目录：{MODEL_REGISTRY_DIR}/{数据集名称}/{训练运行 ID}
    registry_path = MODEL_REGISTRY_DIR / dataset["name"] / run["run_id"]
    registry_path.mkdir(parents=True, exist_ok=True)

    # ---- 3. 复制训练图表与配置文件 ----
    # 需要复制的非权重产出物清单
    for name in [
        "results.csv", "results.png", "confusion_matrix.png", "PR_curve.png",
        "F1_curve.png", "args.yaml", "labels.jpg", "train_batch0.jpg", "val_batch0_pred.jpg",
    ]:
        source = run_path / name
        if source.exists():
            shutil.copy2(source, registry_path / name)  # copy2 保留元数据

    # ---- 4. 复制模型权重文件 ----
    # 创建 weights 子目录，分别复制 best.pt 和 last.pt
    weights_target = registry_path / "weights"
    weights_target.mkdir(parents=True, exist_ok=True)
    best_source = run_path / "weights" / "best.pt"
    last_source = run_path / "weights" / "last.pt"
    best_target = weights_target / "best.pt"
    last_target = weights_target / "last.pt"
    if best_source.exists():
        shutil.copy2(best_source, best_target)
    if last_source.exists():
        shutil.copy2(last_source, last_target)

    # ---- 5. 复制数据集清单文件（如果存在） ----
    manifest_source = Path(version["root_path"]) / "dataset_manifest.json"
    if manifest_source.exists():
        shutil.copy2(manifest_source, registry_path / "dataset_manifest.json")

    # ---- 6. 解析 results.csv 并生成 metrics.json ----
    metrics = parse_results_csv(registry_path / "results.csv")
    (registry_path / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ---- 7. 回填逐 epoch 的训练指标到数据库 ----
    _backfill_metrics(training_run_id, registry_path / "results.csv")

    # ---- 8. 向 model_versions 表插入模型版本记录 ----
    # 自动生成模型名称：{数据集名}_{基础模型}_v{序号}
    base_model_short = Path(run["base_model"]).name.replace(".pt", "").replace(".yaml", "")
    model_count = 0
    with db() as cur:
        existing = cur.execute("SELECT COUNT(*) AS c FROM model_versions WHERE dataset_name = %s", (dataset["name"],)).fetchone()
        model_count = existing["c"] if existing else 0
    model_name = f"{dataset['name']}_{base_model_short}_v{model_count + 1}"

    with db() as cur:
        cur.execute(
            """
            INSERT INTO model_versions(
                training_run_id, project_id, run_id, model_name, dataset_name, dataset_version, base_model,
                epochs, imgsz, batch, precision, recall, map50, map50_95, best_epoch,
                best_pt_path, last_pt_path, registry_path, is_candidate, is_production, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, %s)
            ON CONFLICT (training_run_id) DO UPDATE SET
                project_id = EXCLUDED.project_id,
                model_name = EXCLUDED.model_name,
                precision = EXCLUDED.precision, recall = EXCLUDED.recall,
                map50 = EXCLUDED.map50, map50_95 = EXCLUDED.map50_95,
                best_epoch = EXCLUDED.best_epoch,
                best_pt_path = EXCLUDED.best_pt_path, last_pt_path = EXCLUDED.last_pt_path,
                registry_path = EXCLUDED.registry_path, created_at = EXCLUDED.created_at
            """,
            (
                training_run_id, run.get("project_id"), run["run_id"], model_name, dataset["name"], version["version"], run["base_model"],
                run["epochs"], run["imgsz"], run["batch"], metrics.get("precision"),
                metrics.get("recall"), metrics.get("map50"), metrics.get("map50_95"),
                metrics.get("best_epoch"), str(best_target), str(last_target), str(registry_path), utc_now(),
            ),
        )
        # 查询并返回刚插入的模型版本记录
        model = cur.execute("SELECT * FROM model_versions WHERE training_run_id = %s", (training_run_id,)).fetchone()
        return dict(model)


def _backfill_metrics(training_run_id: int, results_csv: Path) -> None:
    """
    解析 results.csv 并将每一 epoch 的指标回填到 training_metrics 表。

    遍历 CSV 中的每一行数据，提取损失值（box/cls/dfl）、精确率、召回率、
    mAP50 和 mAP50-95，逐行写入或替换到 training_metrics 表中。

    参数:
        training_run_id: 训练运行记录的主键 ID，用于关联指标归属。
        results_csv: results.csv 文件的路径。
    """
    # 检查 CSV 文件是否存在
    if not results_csv.exists():
        return
    import csv
    with results_csv.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return

    now = utc_now()
    with db() as cur:
        # 先清除旧数据再插入，避免 ON CONFLICT 约束问题
        cur.execute("DELETE FROM training_metrics WHERE training_run_id = %s", (training_run_id,))
        for row in rows:
            epoch = int(float(row.get("epoch", 0)))
            # 逐行插入/替换训练指标
            cur.execute(
                """INSERT INTO training_metrics(
                    training_run_id, epoch,
                    train_box_loss, train_cls_loss, train_dfl_loss,
                    val_box_loss, val_cls_loss, val_dfl_loss,
                    precision, recall, map50, map50_95, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    training_run_id, epoch,
                    _float(row, ["train/box_loss"]),
                    _float(row, ["train/cls_loss"]),
                    _float(row, ["train/dfl_loss"]),
                    _float(row, ["val/box_loss"]),
                    _float(row, ["val/cls_loss"]),
                    _float(row, ["val/dfl_loss"]),
                    _float(row, ["metrics/precision(B)", "metrics/precision"]),
                    _float(row, ["metrics/recall(B)", "metrics/recall"]),
                    _float(row, ["metrics/mAP50(B)", "metrics/mAP50"]),
                    _float(row, ["metrics/mAP50-95(B)", "metrics/mAP50-95"]),
                    now,
                ),
            )


def _float(row: dict, candidates: list[str]) -> float | None:
    """
    从字典行的候选字段列表中提取第一个非空浮点数值。

    遍历 candidates 列表，返回第一个存在于 row 中且值非空的字段的浮点数。
    与 _last_float 的区别：此函数仅用于提取单值字段，不需要"向后搜索"语义。

    参数:
        row: 数据行字典，键为列名，值为字符串。
        candidates: 候选字段名列表，按优先级从高到低排列。

    返回:
        解析成功的浮点数，或 None。
    """
    for key in candidates:
        if key in row and row[key] not in {"", None}:
            try:
                return float(row[key])
            except ValueError:
                continue
    return None
