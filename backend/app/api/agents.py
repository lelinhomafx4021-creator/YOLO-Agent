import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.agents.chat_agent import chat, chat_stream
from app.agents.context_builder import build_context
from app.agents.plan_service import apply_plan, get_plan, list_plans, mark_plan_read, save_plan, update_plan_status
from app.api.settings import _read_settings
from app.core.database import db, fetch_all, fetch_one, utc_now

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/sessions")
def list_sessions(project_id: int | None = Query(default=None)) -> list[dict]:
    if project_id:
        return fetch_all(
            "SELECT * FROM agent_sessions WHERE project_id = %s ORDER BY id DESC",
            (project_id,),
        )
    return fetch_all("SELECT * FROM agent_sessions ORDER BY id DESC")


@router.post("/sessions")
def create_session(payload: dict | None = None) -> dict:
    payload = payload or {}
    now = utc_now()
    title = str(payload.get("title") or "").strip() or f"会话 {now[:16]}"
    project_id = payload.get("project_id")
    settings = _read_settings()
    mode = payload.get("mode") or settings.get("agent_mode", "rule")
    with db() as cur:
        cur.execute(
            """
            INSERT INTO agent_sessions(project_id, title, mode, created_at)
            VALUES (%s, %s, %s, %s) RETURNING *
            """,
            (project_id, title, mode, now),
        )
        return dict(cur.fetchone())


@router.get("/sessions/{session_id}/messages")
def get_messages(session_id: int) -> list[dict]:
    return fetch_all(
        "SELECT * FROM agent_messages WHERE session_id = %s ORDER BY id ASC",
        (session_id,),
    )


@router.post("/sessions/{session_id}/chat")
def send_message(session_id: int, payload: dict) -> dict:
    session = fetch_one("SELECT * FROM agent_sessions WHERE id = %s", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    message = str(payload.get("message", payload.get("content", ""))).strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    project_id = payload.get("project_id") or session.get("project_id")
    result = chat(session_id, message, _read_settings(), project_id=project_id)
    result["role"] = "assistant"
    return result


@router.post("/sessions/{session_id}/chat/stream")
async def send_message_stream(session_id: int, payload: dict):
    """SSE 流式对话端点。实时返回 Agent 回复的每个片段。"""
    session = fetch_one("SELECT * FROM agent_sessions WHERE id = %s", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    message = str(payload.get("message", payload.get("content", ""))).strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    project_id = payload.get("project_id") or session.get("project_id")

    async def event_stream():
        async for event in chat_stream(session_id, message, _read_settings(), project_id=project_id):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/context")
def get_context(project_id: int | None = Query(default=None)) -> dict:
    return build_context(project_id)


@router.get("/plans")
def get_plans(status: str = "") -> list[dict]:
    plans = list_plans(status)
    # 默认排除已删除
    if not status:
        plans = [p for p in plans if p.get("status") != "deleted"]
    return plans


@router.post("/plans")
def create_plan(payload: dict) -> dict:
    return save_plan(
        session_id=payload.get("session_id"),
        project_id=payload.get("project_id"),
        plan_type=payload.get("plan_type", "general"),
        title=payload.get("title", ""),
        content=payload.get("content", {}),
        dataset_version_id=payload.get("dataset_version_id"),
        training_run_id=payload.get("training_run_id"),
    )


@router.get("/plans/{plan_id}")
def get_plan_detail(plan_id: int) -> dict:
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    return plan


@router.post("/plans/{plan_id}/apply")
def apply_plan_endpoint(plan_id: int) -> dict:
    try:
        return apply_plan(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/plans/{plan_id}/read")
def mark_plan_read_endpoint(plan_id: int) -> dict:
    try:
        return mark_plan_read(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/plans/{plan_id}/status")
def update_plan(plan_id: int, payload: dict) -> dict:
    status = payload.get("status", "draft")
    if status not in ("draft", "executed", "archived", "deleted"):
        raise HTTPException(status_code=400, detail="invalid status")
    try:
        return update_plan_status(plan_id, status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int) -> dict:
    session = fetch_one("SELECT * FROM agent_sessions WHERE id = %s", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    with db() as cur:
        cur.execute("DELETE FROM agent_messages WHERE session_id = %s", (session_id,))
        cur.execute("DELETE FROM agent_sessions WHERE id = %s", (session_id,))
    return {"message": "deleted"}


@router.put("/sessions/{session_id}")
def rename_session(session_id: int, payload: dict) -> dict:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    session = fetch_one("SELECT * FROM agent_sessions WHERE id = %s", (session_id,))
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    with db() as cur:
        cur.execute("UPDATE agent_sessions SET title = %s WHERE id = %s RETURNING *", (title, session_id))
        return dict(cur.fetchone())
