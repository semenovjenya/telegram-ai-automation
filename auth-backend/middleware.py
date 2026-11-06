"""Middleware for JWT token validation and request context."""

from typing import Annotated

from auth import verify_token
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models import TokenData

security = HTTPBearer()
BearerCredentials = Annotated[HTTPAuthorizationCredentials, Depends(security)]


async def get_current_user(credentials: BearerCredentials) -> TokenData:
    """Dependency to get current authenticated user from JWT token."""
    token = credentials.credentials
    token_data = verify_token(token)
    return token_data


def get_saas_user_id_from_token(request: Request) -> int | None:
    """Extract saas_user_id from JWT token in request."""
    authorization: str | None = request.headers.get("Authorization")

    if not authorization:
        return None

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None

        token_data = verify_token(token)
        return token_data.saas_user_id
    except (ValueError, HTTPException):
        return None
