"""
Entry point for AI-BRAIN service
"""

import uvicorn

from .config import settings

if __name__ == "__main__":
    uvicorn.run(
        "ai_brain.api.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
