from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import (
    agents,
    annotations,
    auth,
    camera,
    datasets,
    inference,
    models,
    notifications,
    projects,
    settings,
    training,
)
from app.core.config import DATASETS_DIR, EXPORTS_DIR, INFERENCE_DIR, MODEL_REGISTRY_DIR, RUNS_DIR, ensure_data_dirs
from app.core.database import init_db

ensure_data_dirs()

app = FastAPI(
    title="YOLOps-Agent API",
    description="YOLO dataset management, training, evaluation, model registry, and agent APIs.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5174",
        "http://localhost:5174",
        "http://127.0.0.1:5175",
        "http://localhost:5175",
        "http://127.0.0.1:5176",
        "http://localhost:5176",
        "http://127.0.0.1:5177",
        "http://localhost:5177",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    from app.api.auth import check_auth
    if not check_auth(request):
        return JSONResponse(status_code=401, content={"detail": "未登录，请先输入密码"})
    return await call_next(request)


@app.on_event("startup")
def startup() -> None:
    ensure_data_dirs()
    init_db()


@app.get("/")
def root() -> dict:
    return {
        "name": "YOLOps-Agent",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(datasets.router)
app.include_router(projects.router)
app.include_router(annotations.router)
app.include_router(training.router)
app.include_router(models.router)
app.include_router(notifications.router)
app.include_router(settings.router)
app.include_router(agents.router)
app.include_router(inference.router)
app.include_router(camera.router)

app.mount("/images", StaticFiles(directory=str(DATASETS_DIR)), name="images")
app.mount("/runs", StaticFiles(directory=str(RUNS_DIR)), name="runs")
app.mount("/exports", StaticFiles(directory=str(EXPORTS_DIR), check_dir=False), name="exports")
app.mount("/model_registry", StaticFiles(directory=str(MODEL_REGISTRY_DIR), check_dir=False), name="model_registry")
app.mount("/inferences", StaticFiles(directory=str(INFERENCE_DIR), check_dir=False), name="inferences")
app.mount("/camera_snapshots", StaticFiles(directory=str(DATASETS_DIR.parent / "camera_snapshots"), check_dir=False), name="camera_snapshots")
