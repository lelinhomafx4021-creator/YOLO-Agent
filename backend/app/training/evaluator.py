import json
import sys
import traceback
from pathlib import Path
from threading import Thread
from typing import Any

import yaml

from app.core.config import RUNS_DIR
from app.core.database import db, fetch_all, fetch_one, utc_now
from app.core.log_capture import LogCapture, append_log


def create_evaluation_run(
    project_id: int,
    model_version_id: int,
    dataset_version_id: int,
    binding_id: int | None = None,
    source_split: str = "test",
    imgsz: int = 640,
    batch: int = 8,
    device: str = "",
) -> dict:
    proj_name = "proj"
    if project_id:
        from app.core.database import fetch_one as _fo
        p = _fo("SELECT name FROM projects WHERE id = %s", (project_id,))
        if p: proj_name = p["name"][:8]
    cnt = _fo("SELECT COUNT(*) AS c FROM evaluation_runs WHERE project_id = %s", (project_id,))
    n = (cnt["c"] if cnt else 0) + 1
    ts = utc_now().replace('-','').replace(':','').replace('Z','')[:11]
    run_id = f"{proj_name}-E{n}-{ts}"
    run_path = RUNS_DIR / run_id
    log_path = run_path / "eval.log"
    run_path.mkdir(parents=True, exist_ok=True)

    with db() as cur:
        cur.execute(
            """
            INSERT INTO evaluation_runs(
                project_id, model_version_id, dataset_version_id, binding_id, run_id,
                status, run_path, log_path, error, created_at
            ) VALUES (%s, %s, %s, %s, %s, 'created', %s, %s, '', %s) RETURNING *
            """,
            (project_id, model_version_id, dataset_version_id, binding_id, run_id, str(run_path), str(log_path), utc_now()),
        )
        run = dict(cur.fetchone())

    (run_path / "params.json").write_text(
        json.dumps(
            {"source_split": source_split, "imgsz": imgsz, "batch": batch, "device": device},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return run


def start_evaluation_background(evaluation_run_id: int) -> None:
    Thread(target=_run_evaluation, args=(evaluation_run_id,), daemon=True).start()


def _append_log(path: Path, line: str) -> None:
    append_log(path, line)


def _run_evaluation(evaluation_run_id: int) -> None:
    with db() as cur:
        run = cur.execute("SELECT * FROM evaluation_runs WHERE id = %s", (evaluation_run_id,)).fetchone()
        if run is None:
            raise ValueError(f"Evaluation run {evaluation_run_id} not found.")
        run = dict(run)
        model = cur.execute("SELECT * FROM model_versions WHERE id = %s", (run["model_version_id"],)).fetchone()
        version = cur.execute("SELECT * FROM dataset_versions WHERE id = %s", (run["dataset_version_id"],)).fetchone()
        if model is None:
            raise ValueError(f"Model version {run['model_version_id']} not found.")
        model = dict(model)
        if version is None:
            raise ValueError(f"Dataset version {run['dataset_version_id']} not found.")
        version = dict(version)
        cur.execute(
            "UPDATE evaluation_runs SET status = 'running', started_at = %s WHERE id = %s",
            (utc_now(), evaluation_run_id),
        )

    run_path = Path(run["run_path"])
    log_path = Path(run["log_path"])

    try:
        params_path = run_path / "params.json"
        params = json.loads(params_path.read_text(encoding="utf-8")) if params_path.exists() else {}
        source_split = params.get("source_split") or "test"
        imgsz = int(params.get("imgsz") or 640)
        batch = int(params.get("batch") or 8)
        device = params.get("device") or ""
        if not device:
            try:
                import torch
                device = "0" if torch.cuda.is_available() else "cpu"
            except Exception:
                device = "cpu"

        _append_log(log_path, f"=== 测试开始 {run['run_id']} ===")
        _append_log(log_path, f"模型: {model.get('best_pt_path') or model.get('last_pt_path')}")
        _append_log(log_path, f"数据: split={source_split} imgsz={imgsz} batch={batch}")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed; install backend requirements first.") from exc

        model_path = model.get("best_pt_path") or model.get("last_pt_path")
        if not model_path or not Path(model_path).exists():
            raise FileNotFoundError(f"model weight not found: {model_path}")

        eval_yaml = _build_eval_yaml(version, source_split, run_path)
        yolo = YOLO(model_path)

        # 用 LogCapture 捕获 val() 输出
        capture = LogCapture(log_path, sys.stdout)
        old_stdout = sys.stdout
        sys.stdout = capture

        try:
            val_kwargs: dict[str, Any] = {
                "data": str(eval_yaml),
                "split": "test",
                "imgsz": imgsz,
                "batch": batch,
                "project": str(run_path),
                "name": "val",
                "exist_ok": True,
            }
            val_kwargs["device"] = device
            _append_log(log_path, "--- 开始验证 ---")
            metrics_obj = yolo.val(**val_kwargs)
            metrics = _extract_metrics(metrics_obj)
            _append_log(log_path, f"验证完成: P={metrics.get('precision', '-')} R={metrics.get('recall', '-')} mAP50={metrics.get('map50', '-')}")

            _append_log(log_path, "--- 开始推理预测 ---")
            image_source = _image_source_for_split(version, source_split)
            predict_kwargs: dict[str, Any] = {
                "source": str(image_source),
                "project": str(run_path),
                "name": "predict",
                "exist_ok": True,
                "save": True,
                "save_txt": True,
                "save_conf": True,
            }
            if device:
                predict_kwargs["device"] = device
            yolo.predict(**predict_kwargs)
        finally:
            sys.stdout = old_stdout
            capture.flush()

        _append_log(log_path, "保存逐图结果...")
        _save_samples(evaluation_run_id, version["id"], source_split, run_path)

        with db() as cur:
            cur.execute(
                """
                UPDATE evaluation_runs
                SET status = 'completed', precision = %s, recall = %s, map50 = %s,
                    map50_95 = %s, finished_at = %s
                WHERE id = %s
                """,
                (
                    metrics.get("precision"),
                    metrics.get("recall"),
                    metrics.get("map50"),
                    metrics.get("map50_95"),
                    utc_now(),
                    evaluation_run_id,
                ),
            )
        # 训练完成后自动生成 AI 评估报告
        try:
            from app.agents.evaluation_analyst_agent import generate_evaluation_report
            report_result = generate_evaluation_report(evaluation_run_id)
            _append_log(log_path, f"AI 评估报告已生成: {report_result.get('report_path', '')}")
        except Exception as report_exc:
            _append_log(log_path, f"[WARN] AI 评估报告生成失败: {report_exc}")

        _append_log(log_path, "=== 测试完成 ===")
    except Exception as exc:
        error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        _append_log(log_path, f"[ERROR] {error}")
        _append_log(log_path, f"[TRACEBACK]\n{traceback.format_exc()}")
        with db() as cur:
            cur.execute(
                "UPDATE evaluation_runs SET status = 'failed', error = %s, finished_at = %s WHERE id = %s",
                (error, utc_now(), evaluation_run_id),
            )


def _build_eval_yaml(version: dict, source_split: str, run_path: Path) -> Path:
    source_yaml = Path(version["data_yaml_path"])
    raw = yaml.safe_load(source_yaml.read_text(encoding="utf-8")) if source_yaml.exists() else {}
    root = Path(version["root_path"])
    image_source = _image_source_for_split(version, source_split)
    payload = {
        "path": str(root),
        "train": raw.get("train", str(image_source)),
        "val": raw.get("val", str(image_source)),
        "test": str(image_source),
        "names": raw.get("names", []),
    }
    target = run_path / "eval_data.yaml"
    target.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return target


def _image_source_for_split(version: dict, source_split: str) -> Path:
    root = Path(version["root_path"])
    if source_split:
        split_dir = root / "images" / source_split
        if split_dir.exists():
            return split_dir
    return root / "images"


def _extract_metrics(metrics_obj: Any) -> dict[str, float | None]:
    box = getattr(metrics_obj, "box", None)
    return {
        "precision": _metric_value(box, ("mp", "p")),
        "recall": _metric_value(box, ("mr", "r")),
        "map50": _metric_value(box, ("map50",)),
        "map50_95": _metric_value(box, ("map", "map50_95")),
    }


def _metric_value(obj: Any, names: tuple[str, ...]) -> float | None:
    for name in names:
        value = getattr(obj, name, None)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _save_samples(evaluation_run_id: int, dataset_version_id: int, source_split: str, run_path: Path) -> None:
    if source_split:
        images = fetch_all(
            "SELECT * FROM image_items WHERE dataset_version_id = %s AND split = %s ORDER BY id ASC",
            (dataset_version_id, source_split),
        )
    else:
        images = fetch_all(
            "SELECT * FROM image_items WHERE dataset_version_id = %s ORDER BY id ASC",
            (dataset_version_id,),
        )
    predict_dir = run_path / "predict"
    label_dir = predict_dir / "labels"
    now = utc_now()
    with db() as cur:
        for image in images:
            image_path = Path(image["image_path"])
            pred_label = label_dir / f"{image_path.stem}.txt"
            pred_image = predict_dir / image_path.name
            cur.execute(
                """
                INSERT INTO evaluation_samples(
                    evaluation_run_id, image_item_id, image_path, label_path,
                    prediction_label_path, prediction_image_path,
                    confidence_summary, match_summary, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    evaluation_run_id,
                    image["id"],
                    str(image_path),
                    image.get("label_path") or "",
                    str(pred_label) if pred_label.exists() else "",
                    str(pred_image) if pred_image.exists() else "",
                    _prediction_summary(pred_label),
                    "",
                    now,
                ),
            )


def _prediction_summary(label_path: Path) -> str:
    if not label_path.exists():
        return "0 个预测框"
    lines = [line for line in label_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return f"{len(lines)} 个预测框"
