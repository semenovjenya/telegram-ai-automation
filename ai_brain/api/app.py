"""FastAPI application factory for AI-BRAIN."""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import __version__
from ..clients import postgres_client
from ..config import settings
from ..graph import brain_graph
from .routes import router

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Fail startup when required persistence is unavailable; close cleanly."""

    await asyncio.to_thread(postgres_client.ensure_schema)
    await brain_graph.initialize()
    logger.info("AI-BRAIN startup completed")
    try:
        yield
    finally:
        await brain_graph.close()
        await asyncio.to_thread(postgres_client.close)
        logger.info("AI-BRAIN shutdown completed")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-BRAIN Service",
        description="Tenant-safe AI analytics orchestration for Telegram channels",
        version=__version__,
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id[:128]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        response.headers["Cache-Control"] = "no-store"
        if settings.ENVIRONMENT in {"staging", "production"}:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers=exc.headers,
        )

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
    )
