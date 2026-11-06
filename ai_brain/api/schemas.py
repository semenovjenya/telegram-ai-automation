"""Validated API contracts for AI-BRAIN."""

from __future__ import annotations

import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

SESSION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$"
TELEGRAM_USERNAME = re.compile(r"^[A-Za-z0-9_]{5,64}$")
SessionId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=SESSION_ID_PATTERN,
    ),
]
StringIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=IDENTIFIER_PATTERN,
    ),
]
SignedIntegerIdentifier = Annotated[int, Field(ge=-(2**63), le=2**63 - 1)]
PositiveIntegerIdentifier = Annotated[int, Field(gt=0, le=2**63 - 1)]


class BrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    saas_user_id: int = Field(..., gt=0, description="Authenticated tenant ID")
    session_id: SessionId
    chat_id: StringIdentifier | SignedIntegerIdentifier
    user_id: StringIdentifier | PositiveIntegerIdentifier
    message_text: str = Field(..., min_length=1, max_length=12_000)
    channel_username: str | None = Field(default=None, max_length=65)
    language: str | None = Field(default="ru", pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    metadata: dict[str, Any] | None = None

    @field_validator("message_text")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message_text cannot be blank")
        return value.strip()

    @field_validator("channel_username")
    @classmethod
    def normalize_channel_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        normalized = stripped[1:] if stripped.startswith("@") else stripped
        if not TELEGRAM_USERNAME.fullmatch(normalized):
            raise ValueError("channel_username must be a valid Telegram username")
        return normalized.casefold()

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        forbidden = {"api_key", "authorization", "system_prompt", "instructions"}
        if forbidden.intersection(key.casefold() for key in value):
            raise ValueError("metadata contains a reserved key")
        if len(json.dumps(value, ensure_ascii=False, default=str)) > 16_384:
            raise ValueError("metadata exceeds 16 KiB")
        return value


class BrainResponse(BaseModel):
    reply_text: str
    used_agent: Literal["general", "sales", "barter"]
    route: Literal["GENERAL", "SALES", "BARTER"]
    metadata: dict[str, Any] | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
