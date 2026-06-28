"""训练管理 — 创建训练记录、后台执行 YOLO 训练、收集产物与报告。

队列机制 (2026-06-27):
- GPU 互斥锁 _gpu_lock 确保同一时间只有一个训练使用 GPU
- 新训练创建后 status='created'（排队中），由 _maybe_start_next() 调度
- 训练完成/失败后自动启动下一个排队任务
- 服务器重启时自动将残留 running 标记为 failed
"""

import sys
import threading
import traceback
from pathlib import Path
from threading import Thread

from app.agents.training_analyst_agent import generate_training_report
from app.core.config import RUNS_DIR
from app.core.database import db, fetch_all, fetch_one, utc_now
from app.core.log_capture import LogCapture, append_log
from app.presentation import build_training_display_name, build_training_run_id
from app.training.artifact_collector import collect_artifacts

LATEST_PROJECT_MODEL_SENTINEL = "__latest_project_model__"
TRAINING_RUN_MODEL_PREFIX = "__training_run_model__:"

# ── 队列全局状态 ──────────────────────────────────────────────────────────
_gpu_lock = threading.Lock()       # GPU 互斥锁
_queue_initialized = False         # 是否已执行过启动恢复


def create_training_run(
    dataset_version_id: int,
    base_model: str,
    epochs: int,
    imgsz: int,
    batch: int,
    project_id: int | None = None,
    device: str = "",
    run_name: str | None = None,
    optimizer: str = "auto",
    lr0: str = "",
    val_dataset_version_id: int | None = None,
) -> dict:
    """创建训练运行记录并初始化目录。"""
    # 尝试获取项目和数据集名生成有意义ID
    proj_name = "proj"
    project_label = ""
    ds_name = ""
    if project_id:
        p = fetch_one("SELECT name FROM projects WHERE id = %s", (project_id,))
        if p:
            proj_name = p["name"][:8]
            project_label = p["name"]
    v = fetch_one("SELECT d.name FROM dataset_versions dv JOIN datasets d ON d.id=dv.dataset_id WHERE dv.id=%s", (dataset_version_id,))
    if v: ds_name = v["name"]
    # 计数：该项目第几次训练
    cnt = fetch_one("SELECT COUNT(*) AS c FROM training_runs WHERE project_id = %s", (project_id,))
    n = (cnt["c"] if cnt else 0) + 1
    now = utc_now()
    display_name = build_training_display_name(project_label, n, run_name)
    run_id = build_training_run_id(proj_name, n, now)
    run_path = RUNS_DIR / run_id
    log_path = run_path / "train.log"
    run_path.mkdir(parents=True, exist_ok=True)

    with db() as cur:
        cur.execute(
            """
            INSERT INTO training_runs(
                run_id, display_name, project_id, dataset_version_id, val_dataset_version_id, dataset_name, base_model, epochs, imgsz, batch,
                device, optimizer, lr0, status, run_path, log_path, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'created', %s, %s, %s) RETURNING *
            """,
            (run_id, display_name, project_id, dataset_version_id, val_dataset_version_id, ds_name, base_model, epochs, imgsz, batch, device, optimizer, lr0, str(run_path), str(log_path), now),
        )
        return dict(cur.fetchone())


def start_training_background(training_run_id: int) -> None:
    """将训练加入调度队列。如果 GPU 空闲则立即启动，否则排队等待。"""
    _maybe_start_next()


def _maybe_start_next() -> None:
    """检查队列：如果没有运行中的训练，启动下一个排队任务。

    线程安全：通过 _gpu_lock 确保同一时间只有一个线程在调度。
    首次调用时自动恢复因服务器重启而中断的训练。
    """
    global _queue_initialized
    if not _queue_initialized:
        _queue_initialized = True
        _recover_orphaned_runs()

    with _gpu_lock:
        # 检查是否已有运行中的训练
        running = fetch_one(
            "SELECT COUNT(*) AS c FROM training_runs WHERE status = 'running'"
        )
        if running and running["c"] > 0:
            return  # 已有训练在运行，新任务保持 created 排队

        # 找到最早创建的排队训练
        next_run = fetch_one(
            "SELECT * FROM training_runs WHERE status = 'created' ORDER BY created_at ASC LIMIT 1"
        )
        if not next_run:
            return  # 队列为空

        training_run_id = next_run["id"]
        with db() as cur:
            cur.execute(
                "UPDATE training_runs SET status = 'running', started_at = %s WHERE id = %s",
                (utc_now(), training_run_id),
            )

    # 在锁外启动训练线程，避免阻塞队列调度
    Thread(target=_run_training, args=(training_run_id,), daemon=True).start()


def _recover_orphaned_runs() -> None:
    """启动恢复：将残留 running 状态标记为 failed（服务器重启导致中断）。"""
    orphaned = fetch_all(
        "SELECT id, run_id, log_path FROM training_runs WHERE status = 'running'"
    )
    if not orphaned:
        return
    for row in orphaned:
        with db() as cur:
            cur.execute(
                "UPDATE training_runs SET status = 'failed', error = %s, finished_at = %s WHERE id = %s",
                ("服务器重启，训练中断", utc_now(), row["id"]),
            )
        log_path = Path(row["log_path"])
        if log_path.exists():
            try:
                _append_log(log_path, "[SYSTEM] 服务器重启，训练中断")
            except Exception:
                pass


def _append_log(path: Path, line: str) -> None:
    """向训练日志文件追加一行（委托给 log_capture.append_log）。"""
    append_log(path, line)


def _resolve_base_model_for_run(run: dict, log_path: Path) -> str:
    """Resolve deferred base-model selections when a queued run starts."""
    base_model = (run.get("base_model") or "").strip()
    if base_model.startswith(TRAINING_RUN_MODEL_PREFIX):
        raw_target_id = base_model[len(TRAINING_RUN_MODEL_PREFIX):].strip()
        try:
            target_run_id = int(raw_target_id)
        except ValueError as exc:
            raise RuntimeError(f"训练任务产物引用无效: {base_model}") from exc
        if target_run_id == int(run["id"]):
            raise RuntimeError("训练任务不能引用自己的产物作为基础模型。")

        target = fetch_one(
            """
            SELECT tr.id, tr.run_id, tr.status, tr.project_id,
                   mv.best_pt_path, mv.last_pt_path, mv.model_name, mv.run_id AS model_run_id
            FROM training_runs tr
            LEFT JOIN model_versions mv ON mv.training_run_id = tr.id
            WHERE tr.id = %s
            ORDER BY mv.id DESC
            LIMIT 1
            """,
            (target_run_id,),
        )
        if not target:
            raise RuntimeError(f"找不到被引用的训练任务: {target_run_id}")
        if run.get("project_id") and target.get("project_id") != run.get("project_id"):
            raise RuntimeError("不能引用其他项目的训练产物。")
        if target.get("status") != "completed":
            raise RuntimeError(f"被引用训练任务 {target.get('run_id')} 当前状态为 {target.get('status')}，没有可用产物。")

        resolved = target.get("best_pt_path") or target.get("last_pt_path") or ""
        if not resolved:
            raise RuntimeError(f"被引用训练任务 {target.get('run_id')} 没有注册 best.pt/last.pt。")
        weight_path = Path(resolved)
        if not weight_path.exists():
            raise RuntimeError(f"被引用训练任务的权重不存在: {resolved}")

        with db() as cur:
            cur.execute(
                "UPDATE training_runs SET base_model = %s WHERE id = %s",
                (resolved, run["id"]),
            )
        run["base_model"] = resolved

        label = target.get("model_name") or target.get("model_run_id") or target.get("run_id") or f"run#{target_run_id}"
        _append_log(log_path, f"[queue] base_model resolved to training run output: {label} -> {resolved}")
        return resolved

    if base_model != LATEST_PROJECT_MODEL_SENTINEL:
        return base_model

    project_id = run.get("project_id")
    if project_id is None:
        raise RuntimeError("当前训练任务没有 project_id，无法解析最新项目模型。")

    latest_model = fetch_one(
        """
        SELECT mv.best_pt_path, mv.last_pt_path, mv.model_name, mv.run_id, mv.training_run_id
        FROM model_versions mv
        LEFT JOIN training_runs tr ON tr.id = mv.training_run_id
        WHERE mv.project_id = %s
          AND COALESCE(mv.model_format, '') IN ('', 'YOLO', 'yolo')
          AND COALESCE(NULLIF(mv.best_pt_path, ''), NULLIF(mv.last_pt_path, ''), '') <> ''
          AND COALESCE(tr.status, 'completed') = 'completed'
        ORDER BY mv.id DESC
        LIMIT 1
        """,
        (project_id,),
    )
    if not latest_model:
        raise RuntimeError("没有找到本项目已完成的 YOLO 模型。请让第一个任务使用预训练模型，后续任务再选择最新项目模型。")

    resolved = latest_model.get("best_pt_path") or latest_model.get("last_pt_path") or ""
    if not resolved:
        raise RuntimeError("最新项目模型没有可用的 best.pt/last.pt 权重路径。")

    weight_path = Path(resolved)
    if not weight_path.exists():
        raise RuntimeError(f"最新项目模型权重不存在: {resolved}")

    with db() as cur:
        cur.execute(
            "UPDATE training_runs SET base_model = %s WHERE id = %s",
            (resolved, run["id"]),
        )
    run["base_model"] = resolved

    label = latest_model.get("model_name") or latest_model.get("run_id") or f"model#{latest_model.get('training_run_id')}"
    _append_log(log_path, f"[queue] base_model resolved to latest project model: {label} -> {resolved}")
    return resolved


def _run_training(training_run_id: int) -> None:
    """后台线程：加载配置 → YOLO 训练 → 收集产物 → 生成报告。"""
    with db() as cur:
        raw_run = cur.execute("SELECT * FROM training_runs WHERE id = %s", (training_run_id,)).fetchone()
        if raw_run is None:
            raise ValueError(f"Training run {training_run_id} not found.")
        run = dict(raw_run)
        raw_ver = cur.execute("SELECT * FROM dataset_versions WHERE id = %s", (run["dataset_version_id"],)).fetchone()
        if raw_ver is None:
            raise ValueError(f"Dataset version {run['dataset_version_id']} not found.")
        version = dict(raw_ver)
        cur.execute(
            "UPDATE training_runs SET status = 'running', started_at = %s WHERE id = %s",
            (utc_now(), training_run_id),
        )

    log_path = Path(run["log_path"])

    try:
        _append_log(log_path, f"=== 训练开始 {run['run_id']} ===")
        resolved_base_model = _resolve_base_model_for_run(run, log_path)
        _append_log(log_path, f"模型: {resolved_base_model}")
        _append_log(log_path, f"数据: {version.get('data_yaml_path', '')}")
        _append_log(log_path, f"参数: epochs={run['epochs']} imgsz={run['imgsz']} batch={run['batch']}")

        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("ultralytics is not installed.") from exc

        model = YOLO(resolved_base_model)

        kwargs = {
            "data": version["data_yaml_path"],
            "epochs": int(run["epochs"]),
            "imgsz": int(run["imgsz"]),
            "batch": int(run["batch"]),
            "project": str(RUNS_DIR),
            "name": run["run_id"],
            "exist_ok": True,
        }
        if run["device"]:
            kwargs["device"] = run["device"]
        else:
            try:
                import torch
                if torch.cuda.is_available():
                    kwargs["device"] = "0"
                else:
                    kwargs["device"] = "cpu"
            except Exception:
                kwargs["device"] = "cpu"

        # 高级训练参数
        opt = (run.get("optimizer") or "").strip()
        if opt and opt != "auto":
            kwargs["optimizer"] = opt
        lr0 = (run.get("lr0") or "").strip()
        if lr0:
            try: kwargs["lr0"] = float(lr0)
            except ValueError: pass

        import threading as _thr
        _heartbeat_stop = False
        def _heartbeat():
            import time as _time
            while not _heartbeat_stop:
                _time.sleep(15)
                if not _heartbeat_stop:
                    _append_log(log_path, "[heartbeat] 训练进行中...")

        hb = _thr.Thread(target=_heartbeat, daemon=True)
        hb.start()

        capture_stdout = LogCapture(log_path, sys.stdout)
        capture_stderr = LogCapture(log_path, sys.stderr)
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = capture_stdout, capture_stderr
        try:
            model.train(**kwargs)
        finally:
            _heartbeat_stop = True
            sys.stdout, sys.stderr = old_stdout, old_stderr
            capture_stdout.flush()
            capture_stderr.flush()

        _append_log(log_path, "=== 训练完成，开始收集产物 ===")
        collect_artifacts(training_run_id)
        generate_training_report(training_run_id)

        with db() as cur:
            cur.execute(
                "UPDATE training_runs SET status = 'completed', finished_at = %s WHERE id = %s",
                (utc_now(), training_run_id),
            )
        _append_log(log_path, "=== 全部完成 ===")

    except Exception as exc:
        error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        _append_log(log_path, f"[ERROR] {error}")
        _append_log(log_path, f"[TRACEBACK]\n{traceback.format_exc()}")
        with db() as cur:
            cur.execute(
                "UPDATE training_runs SET status = 'failed', error = %s, finished_at = %s WHERE id = %s",
                (error, utc_now(), training_run_id),
            )
    finally:
        # 训练结束（成功/失败）→ 启动下一个排队任务
        _maybe_start_next()
