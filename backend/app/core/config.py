"""Core runtime configuration for the backend."""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env", override=False)

DEFAULT_DATA_DIR = BASE_DIR / "data"
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(DEFAULT_DATA_DIR))).expanduser().resolve()
DATASETS_DIR = DATA_DIR / "datasets"
RUNS_DIR = DATA_DIR / "runs"
MODEL_REGISTRY_DIR = DATA_DIR / "model_registry"
EXPORTS_DIR = DATA_DIR / "exports"
INFERENCE_DIR = DATA_DIR / "inferences"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}

DB_BACKEND = os.getenv("DB_BACKEND", "postgres").lower()
SQLITE_PATH = Path(os.getenv("SQLITE_PATH", str(DATA_DIR / "yolops.db"))).expanduser().resolve()
PG_HOST = os.getenv("PG_HOST", "127.0.0.1")
PG_PORT = int(os.getenv("PG_PORT", "55432"))
PG_USER = os.getenv("PG_USER", "yolops")
PG_PASSWORD = os.getenv("PG_PASSWORD", "yolops123")
PG_DATABASE = os.getenv("PG_DATABASE", "yolops")

# Login gate:
# - unset   -> use the weak default password "yolops"
# - empty   -> disable the gate explicitly
# - custom  -> use the provided shared password
_access_password_raw = os.getenv("ACCESS_PASSWORD")
ACCESS_PASSWORD = "yolops" if _access_password_raw is None else _access_password_raw.strip()


def ensure_data_dirs() -> None:
    for path in (DATA_DIR, DATASETS_DIR, RUNS_DIR, MODEL_REGISTRY_DIR, EXPORTS_DIR, INFERENCE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def resolve_path(stored: str) -> Path:
    """Resolve a stored path to an absolute path."""
    if not stored:
        return DATA_DIR
    p = Path(stored)
    if p.is_absolute():
        return p
    return DATA_DIR / p


def relative_path(absolute: Path) -> str:
    """Store a path relative to DATA_DIR when possible."""
    try:
        return str(absolute.relative_to(DATA_DIR))
    except ValueError:
        return str(absolute)
