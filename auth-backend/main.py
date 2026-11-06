"""Main FastAPI application."""

import hashlib
import json
import logging
import os
import re
import sys
from typing import Annotated
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(__file__))

from app_version import __version__
from auth import login_user
from body_limit import RequestBodyLimitMiddleware
from config import settings
from data_loader import (
    get_ai_recommendation,
    get_ai_summary,
    get_dashboard_metrics,
    get_notifications,
    get_profile,
    get_publications,
)
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from httpx import AsyncClient
from login_client_claims import LoginClientClaimError, verify_login_client_claim
from middleware import get_current_user
from models import LoginRequest, Token, TokenData, UserResponse
from rate_limit import LoginRateLimiter
from tenant_claims import build_tenant_claim_headers

logger = logging.getLogger(__name__)
CurrentUser = Annotated[TokenData, Depends(get_current_user)]
login_rate_limiter = LoginRateLimiter(
    max_attempts=settings.LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    window_seconds=settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    block_seconds=settings.LOGIN_RATE_LIMIT_BLOCK_SECONDS,
    max_entries=settings.LOGIN_RATE_LIMIT_MAX_ENTRIES,
)

_VISIBLE_HEADER_VALUE = re.compile(r"[\x20-\x7e]{1,512}\Z")
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_TRACEPARENT_PATTERN = re.compile(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})\Z")
_MAX_CHAT_MESSAGE_BODY_BYTES = 64 * 1024
_MAX_CHAT_MESSAGE_TEXT_LENGTH = 12_000

app = FastAPI(
    title="Telegram AI Analytics Platform API",
    description="Authenticated gateway for the Telegram AI Analytics Platform",
    version=__version__,
)

# Конфигурация сервисов для прокси
SERVICES = {
    "ai_brain": os.getenv("AI_BRAIN_URL", "http://ai_brain:8000"),
    "telegram_chatbot": os.getenv(
        "TELEGRAM_CHATBOT_URL", "http://telegram_chatbot:8010"
    ),
}


def _validated_proxy_path(path: str) -> str:
    """Return a canonical relative path or reject ambiguous URL syntax."""

    decoded = path
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value

    segments = decoded.split("/")
    if (
        not decoded
        or "%" in decoded
        or any(
            not segment
            or segment in {".", ".."}
            or any(character in segment for character in ("\\", "\0", "?", "#"))
            for segment in segments
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Unsupported proxy route",
        )
    return "/".join(segments)


def _proxy_response(response) -> Response:
    """Preserve upstream status and a minimal safe response-header set."""

    headers = {"Cache-Control": "no-store"}
    for name in ("content-type", "content-disposition"):
        value = response.headers.get(name)
        if value:
            headers[name] = value
    return Response(
        content=None
        if response.status_code == status.HTTP_204_NO_CONTENT
        else response.content,
        status_code=response.status_code,
        headers=headers,
    )


def _filtered_proxy_headers(request: Request) -> dict[str, str]:
    """Build a minimal outbound allowlist without caller identity metadata."""

    headers: dict[str, str] = {}
    for source_name, target_name in (
        ("accept", "Accept"),
        ("content-type", "Content-Type"),
    ):
        value = request.headers.get(source_name, "").strip()
        if _VISIBLE_HEADER_VALUE.fullmatch(value):
            headers[target_name] = value

    request_id = request.headers.get("x-request-id", "").strip()
    if _REQUEST_ID_PATTERN.fullmatch(request_id):
        headers["X-Request-ID"] = request_id

    traceparent = request.headers.get("traceparent", "").strip().lower()
    trace_match = _TRACEPARENT_PATTERN.fullmatch(traceparent)
    if (
        trace_match
        and trace_match.group(1) != "0" * 32
        and trace_match.group(2) != "0" * 16
    ):
        headers["traceparent"] = traceparent

    return headers


def _canonical_chat_message_body(body: bytes, content_type: str) -> bytes:
    """Validate the body-only chat message contract without exposing text in URLs."""

    media_type = content_type.partition(";")[0].strip().casefold()
    if media_type != "application/json":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Chat messages must use application/json",
        )
    if not body or len(body) > _MAX_CHAT_MESSAGE_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat message body is missing or too large",
        )
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid chat message JSON body",
        ) from None
    if not isinstance(payload, dict) or set(payload) != {"text"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chat message body must contain only text",
        )
    message_text = payload["text"]
    if (
        not isinstance(message_text, str)
        or not message_text.strip()
        or len(message_text) > _MAX_CHAT_MESSAGE_TEXT_LENGTH
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Chat message text must contain between 1 and 12000 characters",
        )
    return json.dumps({"text": message_text}, ensure_ascii=False).encode("utf-8")


def _client_id(request: Request, username: str) -> str:
    """Resolve a verified BFF pseudonym or a development-only direct peer."""

    try:
        verified_client_id = verify_login_client_claim(
            getattr(request, "headers", {}),
            username=username,
            signing_key=settings.LOGIN_CLIENT_SIGNING_KEY,
            max_age_seconds=settings.LOGIN_CLIENT_CLAIM_MAX_AGE_SECONDS,
            future_skew_seconds=settings.LOGIN_CLIENT_CLAIM_FUTURE_SKEW_SECONDS,
        )
        # Keep the stable raw pseudonym out of limiter state and diagnostics.
        return "bff:" + hashlib.sha256(verified_client_id.encode("ascii")).hexdigest()
    except LoginClientClaimError:
        if settings.runtime_environment not in {"development", "test"}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication is temporarily unavailable",
            ) from None

    direct_peer = getattr(request, "client", None)
    peer = direct_peer.host if direct_peer else "<unknown>"
    return "peer:" + hashlib.sha256(peer.encode("utf-8")).hexdigest()


def _rate_limit_exception(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many login attempts",
        headers={"Retry-After": str(max(1, retry_after))},
    )


def _dashboard_loader_args(token_data: TokenData) -> dict[str, int | str]:
    """Bind every dashboard file lookup to the verified JWT tenant claim."""

    if (
        settings.DASHBOARD_DATA_SOURCE == "synthetic-demo"
        and token_data.saas_user_id != settings.DEFAULT_SAAS_USER_ID
    ):
        # Do not reveal whether another tenant's demo dataset exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dashboard data not found",
        )
    return {
        "saas_user_id": token_data.saas_user_id,
        "data_source": settings.DASHBOARD_DATA_SOURCE,
        "default_saas_user_id": settings.DEFAULT_SAAS_USER_ID,
    }


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestBodyLimitMiddleware)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Telegram AI Analytics Platform API", "version": __version__}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post(f"{settings.API_V1_PREFIX}/auth/login", response_model=Token)
async def login(login_request: LoginRequest, request: Request):
    """Login endpoint - authenticate user and return JWT token."""
    client_id = _client_id(request, login_request.username)
    try:
        retry_after = login_rate_limiter.register_attempt(
            login_request.username,
            client_id,
        )
    except Exception:
        logger.exception("Login limiter failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable",
        ) from None

    if retry_after is not None:
        raise _rate_limit_exception(retry_after)

    token = login_user(login_request)
    login_rate_limiter.record_success(login_request.username, client_id)
    return token


@app.get(f"{settings.API_V1_PREFIX}/auth/me", response_model=UserResponse)
async def get_current_user_info(token_data: CurrentUser):
    """Get current authenticated user information."""
    return UserResponse(
        id=token_data.user_id,
        username=token_data.username,
        saas_user_id=token_data.saas_user_id,
    )


@app.post(f"{settings.API_V1_PREFIX}/auth/logout")
async def logout(token_data: CurrentUser):
    """Logout endpoint (client should remove token)."""
    return {"message": "Logged out successfully"}


# ==================== Dashboard API Routes ====================


@app.get(f"{settings.API_V1_PREFIX}/dashboard/metrics")
async def get_metrics(token_data: CurrentUser):
    """Получить метрики dashboard."""
    metrics = get_dashboard_metrics(**_dashboard_loader_args(token_data))
    if not metrics:
        raise HTTPException(
            status_code=404,
            detail="Не удалось загрузить данные. Проверьте наличие файлов парсеров.",
        )
    return metrics


@app.get(f"{settings.API_V1_PREFIX}/dashboard/publications")
async def get_dashboard_publications(token_data: CurrentUser):
    """Получить лучшие публикации."""
    return get_publications(**_dashboard_loader_args(token_data), limit=3)


@app.get(f"{settings.API_V1_PREFIX}/dashboard/profile")
async def get_dashboard_profile(token_data: CurrentUser):
    """Получить профиль канала."""
    return get_profile(**_dashboard_loader_args(token_data))


@app.get(f"{settings.API_V1_PREFIX}/dashboard/ai-summary")
async def get_dashboard_ai_summary(token_data: CurrentUser):
    """Получить AI сводку."""
    return get_ai_summary(**_dashboard_loader_args(token_data))


@app.get(f"{settings.API_V1_PREFIX}/dashboard/ai-recommendation")
async def get_dashboard_ai_recommendation(token_data: CurrentUser):
    """Получить AI рекомендацию."""
    return {
        "recommendation": get_ai_recommendation(**_dashboard_loader_args(token_data))
    }


@app.get(f"{settings.API_V1_PREFIX}/dashboard/notifications")
async def get_dashboard_notifications(token_data: CurrentUser):
    """Получить уведомления."""
    return get_notifications(**_dashboard_loader_args(token_data))


@app.get(f"{settings.API_V1_PREFIX}/dashboard")
async def get_dashboard_data(token_data: CurrentUser):
    """Получить все данные dashboard одним запросом."""
    loader_args = _dashboard_loader_args(token_data)
    metrics = get_dashboard_metrics(**loader_args)
    if not metrics:
        raise HTTPException(
            status_code=404,
            detail="Не удалось загрузить данные. Проверьте наличие файлов парсеров.",
        )

    return {
        "data_source": settings.DASHBOARD_DATA_SOURCE,
        "profile": get_profile(**loader_args),
        "metrics": metrics,
        "publications": get_publications(**loader_args, limit=3),
        "aiSummary": get_ai_summary(**loader_args),
        "notifications": get_notifications(**loader_args),
        "aiRecommendation": get_ai_recommendation(**loader_args),
    }


# ==================== Proxy Routes to Other Services ====================


@app.api_route(
    f"{settings.API_V1_PREFIX}/ai/{{path:path}}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_ai_brain(
    path: str,
    request: Request,
    token_data: CurrentUser,
):
    """Прокси запросов к AI Brain сервису."""
    async with AsyncClient(timeout=30.0) as client:
        normalized_path = _validated_proxy_path(path)
        if normalized_path.startswith("api/"):
            normalized_path = normalized_path.removeprefix("api/")

        segments = normalized_path.split("/")
        route_method = None
        tenant_scoped = False
        if normalized_path == "brain/answer":
            route_method = "POST"
            tenant_scoped = True
        elif normalized_path == "chat/sessions":
            route_method = "GET"
            tenant_scoped = True
        elif len(segments) == 3 and segments[:2] == ["chat", "history"]:
            route_method = "GET"
            tenant_scoped = True
        elif len(segments) == 3 and segments[:2] == ["brain", "image"]:
            filename = segments[2]
            expected_prefix = f"dashboard-{token_data.saas_user_id}-"
            if os.path.basename(filename) != filename or not filename.startswith(
                expected_prefix
            ):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Dashboard image not found",
                )
            route_method = "GET"

        if route_method is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unsupported AI route",
            )
        if request.method != route_method:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="Method not allowed for AI route",
            )

        url = f"{SERVICES['ai_brain']}/api/{normalized_path}"

        # Tenant identity always comes from the verified JWT, never from the
        # caller-controlled request body or query string.
        params = dict(request.query_params)
        if tenant_scoped:
            params["saas_user_id"] = str(token_data.saas_user_id)

        body = await request.body()
        if tenant_scoped and body:
            if (
                "application/json"
                not in request.headers.get("content-type", "").lower()
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Tenant-scoped AI requests must use application/json",
                )
            try:
                payload = json.loads(body)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid JSON request body",
                ) from None
            if not isinstance(payload, dict):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="JSON request body must be an object",
                )
            payload["saas_user_id"] = token_data.saas_user_id
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        # Передаем заголовки (исключаем host)
        headers = _filtered_proxy_headers(request)

        # Добавляем API ключ для AI Brain
        ai_brain_api_key = settings.AI_BRAIN_API_KEY.strip()
        if not ai_brain_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI Brain proxy authentication is not configured",
            )
        headers["X-API-Key"] = ai_brain_api_key

        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                params=params,
                content=body if body else None,
            )
            return _proxy_response(response)
        except Exception:
            # Do not copy the caller-controlled path or upstream exception into
            # logs. Both may contain forged log records or sensitive endpoints.
            logger.error("AI Brain proxy request failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI Brain service is temporarily unavailable",
            ) from None


@app.api_route(
    f"{settings.API_V1_PREFIX}/chatbot/{{path:path}}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def proxy_chatbot(
    path: str,
    request: Request,
    token_data: CurrentUser,
):
    """Прокси запросов к Telegram Chatbot сервису."""
    async with AsyncClient(timeout=30.0) as client:
        normalized_path = _validated_proxy_path(path)
        segments = normalized_path.split("/")
        allowed_method = None
        tenant_scoped = False
        is_messages_path = (
            len(segments) == 4
            and segments[:2] == ["api", "chats"]
            and segments[3] == "messages"
        )
        if normalized_path == "api/chats":
            allowed_method = "GET"
            tenant_scoped = True
        elif is_messages_path:
            allowed_method = (
                request.method if request.method in {"GET", "POST"} else None
            )
            tenant_scoped = allowed_method is not None
        elif len(segments) == 3 and segments[:2] == ["api", "channels"]:
            allowed_method = "GET"
        elif normalized_path == "api/channel-search":
            allowed_method = "POST"

        if allowed_method is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Unsupported Telegram route",
            )
        if request.method != allowed_method:
            raise HTTPException(
                status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
                detail="Method not allowed for Telegram route",
            )

        url = f"{SERVICES['telegram_chatbot']}/{normalized_path}"

        params = dict(request.query_params)
        body = await request.body()
        if is_messages_path and request.method == "POST":
            if params:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Chat message POST does not accept query parameters",
                )
            body = _canonical_chat_message_body(
                body,
                request.headers.get("content-type", ""),
            )
        headers = _filtered_proxy_headers(request)

        telegram_api_key = settings.TELEGRAM_API_KEY.strip()
        if not telegram_api_key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Telegram proxy authentication is not configured",
            )
        headers["X-API-Key"] = telegram_api_key
        if tenant_scoped:
            signing_key = settings.TELEGRAM_TENANT_SIGNING_KEY.strip()
            if not signing_key:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Telegram tenant signing is not configured",
                )
            headers.update(
                build_tenant_claim_headers(
                    signing_key=signing_key,
                    tenant_id=token_data.saas_user_id,
                    method=request.method,
                    normalized_path=normalized_path,
                    body=body,
                )
            )

        try:
            response = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                params=params,
                content=body if body else None,
            )
            return _proxy_response(response)
        except Exception:
            # Keep caller-controlled paths and upstream diagnostics out of logs.
            logger.error("Telegram Chatbot proxy request failed")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Telegram service is temporarily unavailable",
            ) from None


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
