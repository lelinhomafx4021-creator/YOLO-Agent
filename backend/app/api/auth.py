"""简单密码门禁 — 无用户系统，单密码共享。"""

import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import ACCESS_PASSWORD, DATA_DIR

router = APIRouter(prefix="/api/auth", tags=["auth"])

TOKEN_FILE = DATA_DIR / "auth_tokens.json"
TOKEN_TTL = 86400 * 7  # 7 天
ENABLED = bool(ACCESS_PASSWORD)

# Token 持久化到文件，重启不丢
_tokens: dict[str, float] = {}

def _load_tokens():
    if TOKEN_FILE.exists():
        try:
            data = json.loads(TOKEN_FILE.read_text())
            now = time.time()
            # 只加载未过期的
            return {t: exp for t, exp in data.items() if exp > now}
        except Exception:
            pass
    return {}

def _save_tokens():
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(_tokens))

# 启动时加载
_tokens = _load_tokens()


class LoginRequest(BaseModel):
    password: str


def _make_token() -> str:
    return hashlib.sha256(os.urandom(32)).hexdigest()[:48]


def _cleanup_tokens() -> None:
    now = time.time()
    expired = [t for t, exp in _tokens.items() if exp < now]
    if expired:
        for t in expired:
            del _tokens[t]
        _save_tokens()


@router.get("/status")
def auth_status() -> dict:
    """返回门禁是否启用。"""
    return {"enabled": ENABLED}


@router.post("/login")
def login(payload: LoginRequest) -> dict:
    """验证密码，返回 token。"""
    if not ENABLED:
        return {"token": "disabled", "message": "门禁未启用"}

    if not hmac.compare_digest(payload.password, ACCESS_PASSWORD):
        raise HTTPException(status_code=401, detail="密码错误")

    _cleanup_tokens()
    token = _make_token()
    _tokens[token] = time.time() + TOKEN_TTL
    _save_tokens()
    return {"token": token, "ttl": TOKEN_TTL}


@router.post("/verify")
def verify(request: Request) -> dict:
    """验证 token 是否有效。"""
    if not ENABLED:
        return {"valid": True}

    token = request.headers.get("X-Auth-Token", "")
    if not token:
        raise HTTPException(status_code=401, detail="未登录")

    if token in _tokens and _tokens[token] > time.time():
        return {"valid": True}

    raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")


def check_auth(request: Request) -> bool:
    """中间件调用：检查请求是否已认证。返回 True 表示通过。"""
    if not ENABLED:
        return True

    # 登录和状态接口不需要认证
    path = request.url.path
    if path.startswith("/api/auth/"):
        return True
    # 静态资源和文档不需要认证
    if path.startswith(("/images/", "/runs/", "/exports/", "/model_registry/", "/inferences/", "/camera_snapshots/", "/docs", "/openapi", "/redoc", "/favicon")):
        return True
    if path == "/" or path == "/api/health":
        return True

    token = request.headers.get("X-Auth-Token", "")
    if token and token in _tokens and _tokens[token] > time.time():
        return True

    return False
