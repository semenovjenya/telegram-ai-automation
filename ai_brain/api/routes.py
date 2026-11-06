"""Authenticated HTTP routes for AI-BRAIN."""

from __future__ import annotations

import asyncio
import logging
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from langchain_core.messages import HumanMessage

from ..clients import postgres_client
from ..config import settings
from ..graph import brain_graph
from .schemas import BrainRequest, BrainResponse, SessionId

logger = logging.getLogger(__name__)
router = APIRouter()


def error_detail(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def verify_api_key(x_api_key: str | None = Header(default=None)) -> str:
    """Authenticate internal callers using constant-time comparison."""

    if not x_api_key or not secrets.compare_digest(x_api_key, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_detail("UNAUTHORIZED", "Invalid or missing API key"),
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return x_api_key


@router.get("/health")
@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "healthy", "service": "ai-brain"}


@router.get("/health/ready")
async def readiness() -> dict[str, str]:
    database_ready = await asyncio.to_thread(postgres_client.ping)
    if not database_ready or not brain_graph.is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail("NOT_READY", "AI-BRAIN dependencies are not ready"),
        )
    return {
        "status": "ready",
        "service": "ai-brain",
        "checkpoint_backend": brain_graph.checkpoint_backend or "unknown",
    }


@router.get("/api/brain/image/{image_filename}")
async def get_image(
    image_filename: str,
    _: str = Depends(verify_api_key),
) -> FileResponse:
    """Serve generated PNGs without allowing filesystem traversal."""

    candidate = Path(image_filename)
    if candidate.name != image_filename or candidate.suffix.lower() != ".png":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("INVALID_IMAGE_NAME", "Invalid image filename"),
        )
    base_dir = settings.ARTIFACTS_DIR.resolve()
    image_path = (base_dir / candidate.name).resolve()
    if image_path.parent != base_dir or not image_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("IMAGE_NOT_FOUND", "Image not found"),
        )
    return FileResponse(image_path, media_type="image/png", filename=candidate.name)


@router.post("/api/brain/answer", response_model=BrainResponse)
async def answer(
    request: BrainRequest,
    _: str = Depends(verify_api_key),
) -> BrainResponse:
    logger.info("ai_request_received")
    state = {
        "saas_user_id": request.saas_user_id,
        "session_id": request.session_id,
        "chat_id": request.chat_id,
        "user_id": request.user_id,
        "message_text": request.message_text,
        "channel_username": request.channel_username,
        "language": request.language,
        "metadata": request.metadata or {},
        "history": [],
        "route": "",
        "reply_text": "",
        "used_agent": "",
        "output_metadata": {},
        "image_path": None,
    }
    try:
        result = await brain_graph.process(state)
    except Exception:
        logger.error("ai_request_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail(
                "PROCESSING_UNAVAILABLE",
                "The AI service is temporarily unavailable",
            ),
        ) from None

    metadata = dict(result.get("output_metadata") or {})
    image_path = result.get("image_path") or metadata.get("image_path")
    if image_path:
        metadata["image_filename"] = Path(str(image_path)).name
        metadata.pop("image_path", None)
    return BrainResponse(
        reply_text=result["reply_text"],
        used_agent=result["used_agent"],
        route=result["route"],
        metadata=metadata,
    )


@router.get("/api/chat/history/{session_id}")
async def get_chat_history(
    session_id: SessionId,
    saas_user_id: int = Query(..., gt=0, description="Authenticated tenant ID"),
    limit: int = Query(default=100, ge=1, le=settings.API_HISTORY_MAX_LIMIT),
    _: str = Depends(verify_api_key),
) -> dict:
    try:
        page = await asyncio.to_thread(
            postgres_client.get_history,
            saas_user_id,
            session_id,
            limit=limit,
        )
    except Exception:
        logger.error("history_lookup_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail("STORAGE_UNAVAILABLE", "History is unavailable"),
        ) from None

    formatted_messages = []
    for record in page.records:
        message = record.message
        content = str(getattr(message, "content", message))
        formatted_messages.append(
            {
                "id": str(record.id),
                "content": content,
                "is_own": isinstance(message, HumanMessage),
                "timestamp": record.created_at.isoformat(),
                "chat_id": session_id,
            }
        )
    return {
        "session_id": session_id,
        "chat_id": session_id,
        "messages": formatted_messages,
        "returned_count": page.returned_count,
        "total": page.total,
    }


@router.get("/api/chat/sessions")
async def list_sessions(
    saas_user_id: int = Query(..., gt=0, description="Authenticated tenant ID"),
    limit: int = Query(default=100, ge=1, le=1000),
    _: str = Depends(verify_api_key),
) -> dict:
    try:
        sessions = await asyncio.to_thread(
            postgres_client.list_sessions,
            saas_user_id,
            limit,
        )
    except Exception:
        logger.error("session_listing_failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail("STORAGE_UNAVAILABLE", "Sessions are unavailable"),
        ) from None
    return {"sessions": sessions, "total": len(sessions)}
