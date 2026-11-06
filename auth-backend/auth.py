"""Authentication module with JWT token handling."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from config import settings
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from models import LoginRequest, Token, TokenData, User
from pydantic import ValidationError


def verify_password(plain_password: str, encoded_password: str) -> bool:
    """Verify a PBKDF2-SHA256 password hash in constant time.

    Expected format: ``pbkdf2_sha256$iterations$salt_b64$digest_b64``.
    """
    try:
        algorithm, iterations_text, salt_b64, digest_b64 = encoded_password.split(
            "$", 3
        )
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 310_000:
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (TypeError, ValueError, UnicodeError):
        return False


def hash_password(password: str, *, iterations: int = 600_000) -> str:
    """Create a PBKDF2 hash suitable for ``DEFAULT_PASSWORD_HASH`` provisioning."""
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations, dklen=32
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def _jwt_secret() -> str:
    """Return configured JWT secret or fail closed before issuing/reading tokens."""
    secret = settings.JWT_SECRET_KEY
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured",
        )
    return secret


def authenticate_user(username: str, password: str) -> User | None:
    """Authenticate a user with username and password."""
    # Usernames are normalized, while passwords are compared byte-for-byte.
    username_clean = username.strip() if username else ""
    password_value = password if password else ""

    if not username_clean or not password_value or not settings.DEFAULT_USERNAME:
        return None

    username_matches = hmac.compare_digest(username_clean, settings.DEFAULT_USERNAME)
    if settings.DEFAULT_PASSWORD_HASH:
        password_matches = verify_password(
            password_value, settings.DEFAULT_PASSWORD_HASH
        )
    elif (
        settings.runtime_environment in {"development", "test"}
        and settings.DEFAULT_PASSWORD
    ):
        password_matches = hmac.compare_digest(
            password_value, settings.DEFAULT_PASSWORD
        )
    else:
        password_matches = False

    if username_matches and password_matches:
        return User(
            id=1,
            username=settings.DEFAULT_USERNAME,
            saas_user_id=settings.DEFAULT_SAAS_USER_ID,
        )
    return None


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            hours=settings.JWT_ACCESS_TOKEN_EXPIRE_HOURS
        )

    now = datetime.now(UTC)
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "nbf": now,
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "jti": secrets.token_urlsafe(16),
        }
    )
    encoded_jwt = jwt.encode(to_encode, _jwt_secret(), algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
        user_id: int = payload.get("user_id")
        username: str = payload.get("username")
        saas_user_id: int = payload.get("saas_user_id")

        if user_id is None or username is None or saas_user_id is None:
            raise credentials_exception

        token_data = TokenData(
            user_id=user_id, username=username, saas_user_id=saas_user_id
        )
        return token_data
    except (InvalidTokenError, ValidationError, TypeError, ValueError):
        raise credentials_exception from None


def login_user(login_request: LoginRequest) -> Token:
    """Authenticate user and return JWT token."""
    user = authenticate_user(login_request.username, login_request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(hours=settings.JWT_ACCESS_TOKEN_EXPIRE_HOURS)
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "username": user.username,
            "saas_user_id": user.saas_user_id,
        },
        expires_delta=access_token_expires,
    )

    return Token(
        access_token=access_token,
        token_type="bearer",  # noqa: S106 - OAuth scheme, not a password
        user=user,
    )
