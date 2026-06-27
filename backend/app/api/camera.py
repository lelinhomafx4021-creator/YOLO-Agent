"""摄像头实时推理 API — 浏览器摄像头 + RTSP 流。"""

import asyncio
import base64
import time
import uuid
from pathlib import Path
from threading import Lock, Thread

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.core.config import DATA_DIR, IMAGE_EXTENSIONS
from app.core.database import fetch_one
from app.core.path_utils import parse_yolo_boxes

router = APIRouter(prefix="/api/camera", tags=["camera"])

# 模型缓存（最多 3 个，线程安全）
_model_cache: dict[int, object] = {}
_cache_lock = Lock()

CAMERA_DIR = DATA_DIR / "camera_snapshots"
CAMERA_DIR.mkdir(parents=True, exist_ok=True)

# RTSP 流管理
_rtsp_streams: dict[str, dict] = {}
_rtsp_lock = Lock()


def _get_model(model_id: int):
    """获取缓存的 YOLO 模型，支持 .pt/.onnx/.engine/.torchscript。"""
    with _cache_lock:
        if model_id in _model_cache:
            return _model_cache[model_id]

    model = fetch_one("SELECT * FROM model_versions WHERE id = %s", (model_id,))
    if not model:
        raise HTTPException(status_code=404, detail="模型不存在")

    model_path = model.get("best_pt_path") or model.get("last_pt_path")
    if not model_path or not Path(model_path).exists():
        raise HTTPException(status_code=400, detail="模型权重文件不存在")

    try:
        from ultralytics import YOLO
        yolo = YOLO(model_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"模型加载失败: {exc}") from exc

    with _cache_lock:
        if len(_model_cache) >= 3:
            del _model_cache[next(iter(_model_cache))]
        _model_cache[model_id] = yolo

    return yolo


def _predict_sync(yolo, tmp_path: str, conf: float, iou: float) -> dict:
    """同步推理（在线程池中运行）。"""
    t0 = time.time()
    results = yolo.predict(tmp_path, conf=conf, iou=iou, save=False, verbose=False)
    elapsed_ms = round((time.time() - t0) * 1000, 1)

    result = results[0] if results else None
    boxes, class_names = parse_yolo_boxes(result)

    return {
        "boxes": boxes,
        "box_count": len(boxes),
        "elapsed_ms": elapsed_ms,
        "class_names": class_names,
    }


@router.post("/frame")
async def camera_frame(
    model_id: int = Form(...),
    frame: UploadFile = File(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
) -> dict:
    """单帧推理，返回检测框坐标。"""
    yolo = _get_model(model_id)
    content = await frame.read()
    if not content:
        return {"boxes": [], "elapsed_ms": 0, "class_names": []}

    tmp_path = CAMERA_DIR / f"_frame_{uuid.uuid4().hex[:8]}.jpg"
    tmp_path.write_bytes(content)
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: _predict_sync(yolo, str(tmp_path), conf, iou)
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@router.post("/snapshot")
async def camera_snapshot(
    model_id: int = Form(...),
    frame: UploadFile = File(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
    batch_name: str = Form(""),
) -> dict:
    """截图保存 — 保存原图和标注图。"""
    content = await frame.read()
    if not content:
        raise HTTPException(status_code=400, detail="空帧")

    session_id = f"cam_{uuid.uuid4().hex[:8]}"
    session_dir = CAMERA_DIR / session_id
    session_dir.mkdir(parents=True)
    input_path = session_dir / "snapshot.jpg"
    input_path.write_bytes(content)

    yolo = _get_model(model_id)
    try:
        results = yolo.predict(
            str(input_path), conf=conf, iou=iou,
            save=True, project=str(session_dir.resolve()), name="pred", exist_ok=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"推理失败: {exc}") from exc

    result = results[0] if results else None
    boxes, _ = parse_yolo_boxes(result)

    pred_url = ""
    pred_dir = session_dir / "pred"
    if pred_dir.exists():
        for f in pred_dir.iterdir():
            if f.suffix.lower() in IMAGE_EXTENSIONS:
                pred_url = f"/camera_snapshots/{session_id}/pred/{f.name}"
                break

    return {
        "session_id": session_id,
        "batch_name": batch_name or f"截图_{session_id}",
        "boxes": boxes,
        "box_count": len(boxes),
        "snapshot_url": f"/camera_snapshots/{session_id}/snapshot.jpg",
        "prediction_url": pred_url,
    }


# ---------------------------------------------------------------------------
# RTSP 流
# ---------------------------------------------------------------------------

def _rtsp_worker(stream_id: str, rtsp_url: str, model_id: int, conf: float, iou: float):
    """后台线程：循环拉帧 → 推理 → 更新最新结果。"""
    try:
        import cv2
    except ImportError:
        with _rtsp_lock:
            _rtsp_streams[stream_id]["error"] = "opencv-python 未安装"
            _rtsp_streams[stream_id]["running"] = False
        return

    yolo = _get_model(model_id)
    cap = cv2.VideoCapture(rtsp_url)
    if not cap.isOpened():
        with _rtsp_lock:
            _rtsp_streams[stream_id]["error"] = f"无法连接: {rtsp_url}"
            _rtsp_streams[stream_id]["running"] = False
        return

    with _rtsp_lock:
        _rtsp_streams[stream_id]["connected"] = True

    while True:
        with _rtsp_lock:
            if not _rtsp_streams.get(stream_id, {}).get("running"):
                break

        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        try:
            t0 = time.time()
            results = yolo.predict(frame, conf=conf, iou=iou, save=False, verbose=False)
            elapsed_ms = round((time.time() - t0) * 1000, 1)

            result = results[0] if results else None
            boxes, class_names = parse_yolo_boxes(result)

            _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            frame_b64 = base64.b64encode(buf).decode("ascii")

            with _rtsp_lock:
                if stream_id in _rtsp_streams:
                    _rtsp_streams[stream_id]["result"] = {
                        "boxes": boxes,
                        "box_count": len(boxes),
                        "elapsed_ms": elapsed_ms,
                        "class_names": class_names,
                        "frame_base64": frame_b64,
                        "timestamp": time.time(),
                    }
        except Exception:
            pass

    cap.release()
    with _rtsp_lock:
        if stream_id in _rtsp_streams:
            _rtsp_streams[stream_id]["connected"] = False


@router.post("/rtsp/start")
def start_rtsp_stream(
    rtsp_url: str = Form(...),
    model_id: int = Form(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
    stream_name: str = Form(""),
) -> dict:
    """启动 RTSP 摄像头流推理。"""
    with _rtsp_lock:
        for sid, s in _rtsp_streams.items():
            if s.get("rtsp_url") == rtsp_url and s.get("running"):
                return {"stream_id": sid, "status": "already_running"}

    stream_id = f"rtsp_{uuid.uuid4().hex[:8]}"
    with _rtsp_lock:
        _rtsp_streams[stream_id] = {
            "stream_id": stream_id,
            "rtsp_url": rtsp_url,
            "model_id": model_id,
            "name": stream_name or f"RTSP {rtsp_url.split('/')[-1]}",
            "running": True,
            "connected": False,
            "error": "",
            "result": None,
        }

    Thread(target=_rtsp_worker, args=(stream_id, rtsp_url, model_id, conf, iou), daemon=True).start()
    return {"stream_id": stream_id, "status": "started"}


@router.post("/rtsp/stop")
def stop_rtsp_stream(stream_id: str = Form(...)) -> dict:
    """停止 RTSP 流。"""
    with _rtsp_lock:
        if stream_id in _rtsp_streams:
            _rtsp_streams[stream_id]["running"] = False
            return {"stream_id": stream_id, "status": "stopping"}
    raise HTTPException(status_code=404, detail="流不存在")


@router.get("/rtsp/{stream_id}/result")
def get_rtsp_result(stream_id: str) -> dict:
    """获取 RTSP 流的最新推理结果。"""
    with _rtsp_lock:
        stream = _rtsp_streams.get(stream_id)
        if not stream:
            raise HTTPException(status_code=404, detail="流不存在")
        return {
            "stream_id": stream_id,
            "running": stream["running"],
            "connected": stream.get("connected", False),
            "error": stream.get("error", ""),
            "result": stream.get("result"),
        }


@router.get("/rtsp/list")
def list_rtsp_streams() -> list[dict]:
    """列出所有 RTSP 流。"""
    with _rtsp_lock:
        return [
            {
                "stream_id": sid,
                "name": s.get("name", ""),
                "rtsp_url": s.get("rtsp_url", ""),
                "running": s.get("running", False),
                "connected": s.get("connected", False),
                "error": s.get("error", ""),
            }
            for sid, s in _rtsp_streams.items()
        ]
