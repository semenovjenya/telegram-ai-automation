"""Data models for the application."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NamedUserModel(StrictModel):
    username: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def username_must_be_log_safe(cls, value: str) -> str:
        if value != value.strip() or any(
            ord(character) < 0x20 or ord(character) == 0x7F for character in value
        ):
            raise ValueError("username contains unsupported whitespace or controls")
        return value


class User(NamedUserModel):
    """User model."""

    id: int = Field(..., gt=0)
    saas_user_id: int = Field(..., gt=0)


class LoginRequest(NamedUserModel):
    """Login request model."""

    password: str = Field(..., min_length=1, max_length=1024, description="Password")


class Token(StrictModel):
    """Token response model."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    user: User = Field(..., description="User information")


class TokenData(NamedUserModel):
    """Token payload data."""

    user_id: int = Field(..., gt=0)
    saas_user_id: int = Field(..., gt=0)
    exp: datetime | None = None


class UserResponse(NamedUserModel):
    """User response model."""

    id: int = Field(..., gt=0)
    saas_user_id: int = Field(..., gt=0)
