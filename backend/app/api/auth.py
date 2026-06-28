"""Shared-password auth for the whole app."""

import hashlib
import hmac
import json
import os
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.core.config import ACCESS_PASSWORD, DATA_DIR

router = APIRouter(prefix="/api/auth", tags=["auth"])

TOKEN_FILE = DATA_DIR / "auth_tokens.json"
AUTH_CONFIG_FILE = DATA_DIR / "auth_config.json"
TOKEN_TTL = 86400 * 7

_tokens: dict[str, float] = {}
_auth_config: dict[str, str | bool] = {}


class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _default_auth_config() -> dict[str, str | bool]:
    if not ACCESS_PASSWORD:
        return {"enabled": False, "password_hash": ""}
    return {"enabled": True, "password_hash": _hash_password(ACCESS_PASSWORD)}


def _load_auth_config() -> dict[str, str | bool]:
    defaults = _default_auth_config()
    if not AUTH_CONFIG_FILE.exists():
        return defaults
    try:
        data = json.loads(AUTH_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    return {
        "enabled": bool(data.get("enabled", defaults["enabled"])),
        "password_hash": str(data.get("password_hash") or defaults["password_hash"]),
    }


def _save_auth_config() -> None:
    AUTH_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    AUTH_CONFIG_FILE.write_text(json.dumps(_auth_config, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_tokens() -> dict[str, float]:
    if not TOKEN_FILE.exists():
        return {}
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    now = time.time()
    return {token: exp for token, exp in data.items() if exp > now}


def _save_tokens() -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(_tokens, ensure_ascii=False), encoding="utf-8")


def _make_token() -> str:
    return hashlib.sha256(os.urandom(32)).hexdigest()[:48]


def _cleanup_tokens() -> None:
    now = time.time()
    expired = [token for token, exp in _tokens.items() if exp <= now]
    if not expired:
        return
    for token in expired:
        _tokens.pop(token, None)
    _save_tokens()


def _extract_token(request: Request) -> str:
    return request.headers.get("X-Auth-Token", "").strip()


def _auth_enabled() -> bool:
    return bool(_auth_config.get("enabled")) and bool(_auth_config.get("password_hash"))


def _password_matches(password: str) -> bool:
    password_hash = str(_auth_config.get("password_hash") or "")
    if not password_hash:
        return False
    return hmac.compare_digest(_hash_password(password), password_hash)


def _is_valid_token(token: str) -> bool:
    if not token:
        return False
    exp = _tokens.get(token)
    if not exp:
        return False
    if exp <= time.time():
        _tokens.pop(token, None)
        _save_tokens()
        return False
    return True


_tokens = _load_tokens()
_auth_config = _load_auth_config()


@router.get("/status")
def auth_status() -> dict:
    return {
        "enabled": _auth_enabled(),
        "token_ttl": TOKEN_TTL,
        "password_hint": "共享弱密码，仅防误操作" if _auth_enabled() else "",
    }


@router.post("/login")
def login(payload: LoginRequest) -> dict:
    if not _auth_enabled():
        return {"token": "disabled", "ttl": 0}

    if not _password_matches(payload.password):
        raise HTTPException(status_code=401, detail="密码错误")

    _cleanup_tokens()
    token = _make_token()
    _tokens[token] = time.time() + TOKEN_TTL
    _save_tokens()
    return {"token": token, "ttl": TOKEN_TTL}


@router.post("/verify")
def verify(request: Request) -> dict:
    if not _auth_enabled():
        return {"valid": True}

    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    if not _is_valid_token(token):
        raise HTTPException(status_code=401, detail="登录已过期，请重新输入密码")
    return {"valid": True}


@router.post("/password")
def change_password(payload: ChangePasswordRequest, request: Request) -> dict:
    if not _auth_enabled():
        raise HTTPException(status_code=400, detail="共享密码门禁未启用")

    token = _extract_token(request)
    if not _is_valid_token(token):
        raise HTTPException(status_code=401, detail="当前登录已失效，请重新登录")

    if not _password_matches(payload.old_password):
        raise HTTPException(status_code=401, detail="原密码错误")

    new_password = payload.new_password.strip()
    if len(new_password) < 3:
        raise HTTPException(status_code=400, detail="新密码至少 3 位")
    if len(new_password) > 64:
        raise HTTPException(status_code=400, detail="新密码过长")

    _auth_config["enabled"] = True
    _auth_config["password_hash"] = _hash_password(new_password)
    _save_auth_config()

    _tokens.clear()
    new_token = _make_token()
    _tokens[new_token] = time.time() + TOKEN_TTL
    _save_tokens()

    return {"ok": True, "token": new_token, "ttl": TOKEN_TTL}


@router.post("/logout")
def logout(request: Request) -> dict:
    if not _auth_enabled():
        return {"ok": True}

    token = _extract_token(request)
    if token:
        _tokens.pop(token, None)
        _save_tokens()
    return {"ok": True}


def check_auth(request: Request) -> bool:
    if not _auth_enabled():
        return True

    path = request.url.path
    if path.startswith("/api/auth/"):
        return True
    if path.startswith(("/images/", "/runs/", "/exports/", "/model_registry/", "/inferences/", "/camera_snapshots/", "/docs", "/openapi", "/redoc", "/favicon")):
        return True
    if path in {"/", "/api/health"}:
        return True

    _cleanup_tokens()
    return _is_valid_token(_extract_token(request))
