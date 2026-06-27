"""设置与系统运行时 API。"""

import json
import subprocess
from pathlib import Path
from time import monotonic

from fastapi import APIRouter

from app.core.config import DATA_DIR, DB_BACKEND, PG_HOST, PG_PORT, SQLITE_PATH

router = APIRouter(prefix="/api", tags=["settings"])

SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULTS = {
    "agent_mode": "rule",
    "llm_endpoint": "",
    "llm_model": "deepseek-chat",
    "llm_api_key": "",
    "gpu_device": "cuda:0",
}


def _read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    return {**DEFAULTS, **data}


def _write_settings(data: dict) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@router.get("/settings")
def get_settings() -> dict:
    return _read_settings()


@router.put("/settings")
def update_settings(payload: dict) -> dict:
    current = _read_settings()
    valid_updates = {k: v for k, v in payload.items() if k in DEFAULTS}
    current.update(valid_updates)
    _write_settings(current)
    return current


@router.post("/settings/test-connection")
def test_llm_connection() -> dict:
    settings = _read_settings()
    endpoint = settings.get("llm_endpoint", "").rstrip("/")
    api_key = settings.get("llm_api_key", "")
    if not endpoint or not api_key:
        return {"ok": False, "error": "请填写 API 端点和 Key"}
    import urllib.request, urllib.error
    try:
        req = urllib.request.Request(f"{endpoint}/models", headers={"Authorization": f"Bearer {api_key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---- 系统运行时信息 ----

_GPU_CACHE_TTL = 60.0
_gpu_cache: dict | None = None
_gpu_cache_at = 0.0


@router.get("/system/runtime")
def get_runtime() -> dict:
    return {
        "backend": "running",
        "database": {
            "backend": DB_BACKEND,
            "host": PG_HOST if DB_BACKEND == "postgres" else "",
            "port": PG_PORT if DB_BACKEND == "postgres" else None,
            "data_dir": str(DATA_DIR),
            "sqlite_path": str(SQLITE_PATH) if DB_BACKEND == "sqlite" else "",
        },
        "gpu": _detect_gpu(),
    }


def _detect_gpu() -> dict:
    global _gpu_cache, _gpu_cache_at
    now = monotonic()
    if _gpu_cache and (now - _gpu_cache_at) < _GPU_CACHE_TTL:
        return _gpu_cache

    # 先试 nvidia-smi
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
            text=True, timeout=3,
        )
        devices = []
        for line in output.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                mem = round(float(parts[2]) / 1024, 1)
            except ValueError:
                mem = None
            devices.append({"index": int(parts[0]), "name": parts[1], "memory_total_gb": mem, "device": f"cuda:{parts[0]}"})
        if devices:
            first = devices[0]
            mem_text = f" · {first['memory_total_gb']}GB" if first.get("memory_total_gb") else ""
            result = {"available": True, "provider": "nvidia-smi", "summary": f"{first['name']}{mem_text}", "devices": devices}
            _gpu_cache = result
            _gpu_cache_at = now
            return result
    except Exception:
        pass

    # 回退到 torch
    try:
        import torch
        if torch.cuda.is_available():
            devices = []
            for idx in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(idx)
                devices.append({"index": idx, "name": props.name, "memory_total_gb": round(props.total_mem / 1024**3, 1), "device": f"cuda:{idx}"})
            result = {"available": True, "provider": "torch", "summary": f"{devices[0]['name']} · {devices[0]['memory_total_gb']}GB", "devices": devices}
            _gpu_cache = result
            _gpu_cache_at = now
            return result
    except Exception:
        pass

    return {"available": False, "provider": "cpu", "summary": "CPU 模式", "devices": []}
