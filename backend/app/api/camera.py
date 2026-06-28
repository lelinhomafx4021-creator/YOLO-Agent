"""Camera inference APIs for snapshots, local devices, and RTSP streams."""

import asyncio
import base64
import io
import time
import uuid
from pathlib import Path
from threading import Lock, Thread

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from PIL import Image

from app.core.config import DATA_DIR, IMAGE_EXTENSIONS
from app.core.database import fetch_one
from app.core.path_utils import parse_yolo_boxes

router = APIRouter(prefix="/api/camera", tags=["camera"])

_model_cache: dict[int, object] = {}
_cache_lock = Lock()

CAMERA_DIR = DATA_DIR / "camera_snapshots"
CAMERA_DIR.mkdir(parents=True, exist_ok=True)

_local_streams: dict[str, dict] = {}
_local_lock = Lock()
_rtsp_streams: dict[str, dict] = {}
_rtsp_lock = Lock()


def _get_model(model_id: int):
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


def _predict_sync(yolo, source, conf: float, iou: float) -> dict:
    t0 = time.time()
    results = yolo.predict(source, conf=conf, iou=iou, save=False, verbose=False)
    elapsed_ms = round((time.time() - t0) * 1000, 1)

    result = results[0] if results else None
    boxes, class_names = parse_yolo_boxes(result)
    return {
        "boxes": boxes,
        "box_count": len(boxes),
        "elapsed_ms": elapsed_ms,
        "class_names": class_names,
    }


def _predict_sync_bytes(yolo, content: bytes, conf: float, iou: float) -> dict:
    with Image.open(io.BytesIO(content)) as image:
        rgb = image.convert("RGB")
        return _predict_sync(yolo, rgb, conf, iou)


def _encode_frame_b64(frame, quality: int = 72) -> str:
    import cv2

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return ""
    return base64.b64encode(buf).decode("ascii")


def _draw_boxes_on_frame(frame, boxes: list[dict], class_names: list[str]) -> None:
    import cv2

    h, w = frame.shape[:2]
    palette = [
        (228, 118, 48),
        (59, 130, 246),
        (16, 185, 129),
        (139, 92, 246),
        (239, 68, 68),
        (245, 158, 11),
    ]
    for box in boxes:
        class_id = int(box.get("class_id", 0))
        color = palette[class_id % len(palette)]
        x = int((box.get("x_center", 0) - box.get("width", 0) / 2) * w)
        y = int((box.get("y_center", 0) - box.get("height", 0) / 2) * h)
        bw = int(box.get("width", 0) * w)
        bh = int(box.get("height", 0) * h)
        x = max(0, min(x, w - 1))
        y = max(0, min(y, h - 1))
        bw = max(1, min(bw, w - x))
        bh = max(1, min(bh, h - y))
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), color, 2)
        name = class_names[class_id] if 0 <= class_id < len(class_names) else f"class_{class_id}"
        label = f"{name} {int(float(box.get('confidence', 0)) * 100)}%"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
        top = max(0, y - th - 8)
        cv2.rectangle(frame, (x, top), (x + tw + 8, top + th + 6), color, -1)
        cv2.putText(frame, label, (x + 4, top + th + 1), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)


def _save_snapshot_result(frame_b64: str, boxes: list[dict], class_names: list[str], batch_name: str) -> dict:
    import cv2
    import numpy as np

    content = base64.b64decode(frame_b64)
    buffer = np.frombuffer(content, dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=500, detail="截图帧解码失败")

    session_id = f"cam_{uuid.uuid4().hex[:8]}"
    session_dir = CAMERA_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = session_dir / "snapshot.jpg"
    prediction_dir = session_dir / "pred"
    prediction_dir.mkdir(parents=True, exist_ok=True)
    prediction_path = prediction_dir / "snapshot.jpg"

    cv2.imwrite(str(snapshot_path), frame)
    annotated = frame.copy()
    _draw_boxes_on_frame(annotated, boxes, class_names)
    cv2.imwrite(str(prediction_path), annotated)

    return {
        "session_id": session_id,
        "batch_name": batch_name or f"截图_{session_id}",
        "boxes": boxes,
        "box_count": len(boxes),
        "save_dir": f"/camera_snapshots/{session_id}/",
        "snapshot_url": f"/camera_snapshots/{session_id}/snapshot.jpg",
        "prediction_url": f"/camera_snapshots/{session_id}/pred/{prediction_path.name}",
    }


def _capture_worker(
    stream_id: str,
    source,
    model_id: int,
    conf: float,
    iou: float,
    stream_store: dict[str, dict],
    stream_lock: Lock,
    *,
    is_local: bool = False,
) -> None:
    try:
        import cv2
    except ImportError:
        with stream_lock:
            if stream_id in stream_store:
                stream_store[stream_id]["error"] = "opencv-python 未安装"
                stream_store[stream_id]["running"] = False
        return

    yolo = _get_model(model_id)
    backend = cv2.CAP_DSHOW if is_local and hasattr(cv2, "CAP_DSHOW") else source
    cap = cv2.VideoCapture(source, backend) if is_local and backend != source else cv2.VideoCapture(source)
    if not cap.isOpened():
        with stream_lock:
            if stream_id in stream_store:
                stream_store[stream_id]["error"] = f"无法连接视频源: {source}"
                stream_store[stream_id]["running"] = False
        return

    if is_local:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 960)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 540)
        cap.set(cv2.CAP_PROP_FPS, 20)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    last_result_time = 0.0
    with stream_lock:
        if stream_id in stream_store:
            stream_store[stream_id]["connected"] = True

    while True:
        with stream_lock:
            if not stream_store.get(stream_id, {}).get("running"):
                break

        ok, frame = cap.read()
        if not ok or frame is None:
            time.sleep(0.05)
            continue

        try:
            result = _predict_sync(yolo, frame, conf, iou)
            now = time.time()
            fps = round(1 / max(now - last_result_time, 1e-3), 1) if last_result_time else 0.0
            last_result_time = now
            frame_b64 = _encode_frame_b64(frame)
            with stream_lock:
                if stream_id in stream_store:
                    stream_store[stream_id]["result"] = {
                        **result,
                        "fps": fps,
                        "frame_base64": frame_b64,
                        "frame_width": int(frame.shape[1]),
                        "frame_height": int(frame.shape[0]),
                        "timestamp": now,
                    }
        except Exception as exc:
            with stream_lock:
                if stream_id in stream_store:
                    stream_store[stream_id]["error"] = str(exc)
            time.sleep(0.1)

    cap.release()
    with stream_lock:
        if stream_id in stream_store:
            stream_store[stream_id]["connected"] = False


@router.post("/frame")
async def camera_frame(
    model_id: int = Form(...),
    frame: UploadFile = File(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
) -> dict:
    yolo = _get_model(model_id)
    content = await frame.read()
    if not content:
        return {"boxes": [], "elapsed_ms": 0, "class_names": []}
    try:
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: _predict_sync_bytes(yolo, content, conf, iou)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"摄像头推理失败: {exc}") from exc


@router.post("/snapshot")
async def camera_snapshot(
    model_id: int = Form(...),
    frame: UploadFile = File(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
    batch_name: str = Form(""),
) -> dict:
    content = await frame.read()
    if not content:
        raise HTTPException(status_code=400, detail="空帧")

    session_id = f"cam_{uuid.uuid4().hex[:8]}"
    session_dir = CAMERA_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    input_path = session_dir / "snapshot.jpg"
    input_path.write_bytes(content)

    yolo = _get_model(model_id)
    try:
        results = yolo.predict(
            str(input_path), conf=conf, iou=iou, save=True, project=str(session_dir.resolve()), name="pred", exist_ok=True
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"推理失败: {exc}") from exc

    result = results[0] if results else None
    boxes, _ = parse_yolo_boxes(result)

    pred_url = ""
    pred_dir = session_dir / "pred"
    if pred_dir.exists():
        for file in pred_dir.iterdir():
            if file.suffix.lower() in IMAGE_EXTENSIONS:
                pred_url = f"/camera_snapshots/{session_id}/pred/{file.name}"
                break

    return {
        "session_id": session_id,
        "batch_name": batch_name or f"截图_{session_id}",
        "boxes": boxes,
        "box_count": len(boxes),
        "save_dir": f"/camera_snapshots/{session_id}/",
        "snapshot_url": f"/camera_snapshots/{session_id}/snapshot.jpg",
        "prediction_url": pred_url,
    }


@router.post("/local/start")
def start_local_stream(
    device_index: int = Form(0),
    model_id: int = Form(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
) -> dict:
    with _local_lock:
        for sid, stream in _local_streams.items():
            if stream.get("device_index") == device_index and stream.get("running"):
                return {"stream_id": sid, "status": "already_running"}

    stream_id = f"local_{uuid.uuid4().hex[:8]}"
    with _local_lock:
        _local_streams[stream_id] = {
            "stream_id": stream_id,
            "device_index": int(device_index),
            "model_id": int(model_id),
            "running": True,
            "connected": False,
            "error": "",
            "result": None,
        }
    Thread(
        target=_capture_worker,
        args=(stream_id, int(device_index), int(model_id), conf, iou, _local_streams, _local_lock),
        kwargs={"is_local": True},
        daemon=True,
    ).start()
    return {"stream_id": stream_id, "status": "started"}


@router.post("/local/stop")
def stop_local_stream(stream_id: str = Form(...)) -> dict:
    with _local_lock:
        if stream_id in _local_streams:
            _local_streams[stream_id]["running"] = False
            return {"stream_id": stream_id, "status": "stopping"}
    raise HTTPException(status_code=404, detail="本机摄像头流不存在")


@router.get("/local/{stream_id}/result")
def get_local_result(stream_id: str) -> dict:
    with _local_lock:
        stream = _local_streams.get(stream_id)
        if not stream:
            raise HTTPException(status_code=404, detail="本机摄像头流不存在")
        return {
            "stream_id": stream_id,
            "running": stream.get("running", False),
            "connected": stream.get("connected", False),
            "error": stream.get("error", ""),
            "result": stream.get("result"),
        }


@router.post("/local/snapshot")
def save_local_snapshot(stream_id: str = Form(...), batch_name: str = Form("")) -> dict:
    with _local_lock:
        stream = _local_streams.get(stream_id)
        if not stream:
            raise HTTPException(status_code=404, detail="本机摄像头流不存在")
        result = stream.get("result") or {}
        frame_b64 = result.get("frame_base64", "")
        boxes = result.get("boxes", []) or []
        class_names = result.get("class_names", []) or []
    if not frame_b64:
        raise HTTPException(status_code=400, detail="当前没有可保存的画面")
    return _save_snapshot_result(frame_b64, boxes, class_names, batch_name)


@router.post("/rtsp/start")
def start_rtsp_stream(
    rtsp_url: str = Form(...),
    model_id: int = Form(...),
    conf: float = Form(0.25),
    iou: float = Form(0.45),
    stream_name: str = Form(""),
) -> dict:
    with _rtsp_lock:
        for sid, stream in _rtsp_streams.items():
            if stream.get("rtsp_url") == rtsp_url and stream.get("running"):
                return {"stream_id": sid, "status": "already_running"}

    stream_id = f"rtsp_{uuid.uuid4().hex[:8]}"
    with _rtsp_lock:
        _rtsp_streams[stream_id] = {
            "stream_id": stream_id,
            "rtsp_url": rtsp_url,
            "model_id": int(model_id),
            "name": stream_name or f"RTSP {rtsp_url.split('/')[-1]}",
            "running": True,
            "connected": False,
            "error": "",
            "result": None,
        }
    Thread(
        target=_capture_worker,
        args=(stream_id, rtsp_url, int(model_id), conf, iou, _rtsp_streams, _rtsp_lock),
        daemon=True,
    ).start()
    return {"stream_id": stream_id, "status": "started"}


@router.post("/rtsp/stop")
def stop_rtsp_stream(stream_id: str = Form(...)) -> dict:
    with _rtsp_lock:
        if stream_id in _rtsp_streams:
            _rtsp_streams[stream_id]["running"] = False
            return {"stream_id": stream_id, "status": "stopping"}
    raise HTTPException(status_code=404, detail="RTSP 流不存在")


@router.get("/rtsp/{stream_id}/result")
def get_rtsp_result(stream_id: str) -> dict:
    with _rtsp_lock:
        stream = _rtsp_streams.get(stream_id)
        if not stream:
            raise HTTPException(status_code=404, detail="RTSP 流不存在")
        return {
            "stream_id": stream_id,
            "running": stream.get("running", False),
            "connected": stream.get("connected", False),
            "error": stream.get("error", ""),
            "result": stream.get("result"),
        }


@router.get("/rtsp/list")
def list_rtsp_streams() -> list[dict]:
    with _rtsp_lock:
        return [
            {
                "stream_id": sid,
                "name": stream.get("name", ""),
                "rtsp_url": stream.get("rtsp_url", ""),
                "running": stream.get("running", False),
                "connected": stream.get("connected", False),
                "error": stream.get("error", ""),
            }
            for sid, stream in _rtsp_streams.items()
        ]
