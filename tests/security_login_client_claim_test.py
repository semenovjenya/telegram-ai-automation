"""Regression tests for signed BFF login-client claims."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_claims():
    spec = importlib.util.spec_from_file_location(
        "security_login_client_claims",
        ROOT / "auth-backend" / "login_client_claims.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KEY = "login-client-test-signing-key-0123456789-ABCDEF"
CLIENT_ID = "A" * 43
NOW = 1_800_000_000


def _headers(module, *, username: str = "operator", timestamp: int = NOW):
    signature = module.build_login_client_signature(
        signing_key=KEY,
        timestamp=timestamp,
        client_id=CLIENT_ID,
        username=username,
    )
    return {
        module.VERSION_HEADER: module.CLAIM_VERSION,
        module.TIMESTAMP_HEADER: str(timestamp),
        module.CLIENT_ID_HEADER: CLIENT_ID,
        module.SIGNATURE_HEADER: signature,
    }


def _verify(module, headers, *, username: str = "operator"):
    return module.verify_login_client_claim(
        headers,
        username=username,
        signing_key=KEY,
        max_age_seconds=30,
        future_skew_seconds=5,
        clock=lambda: NOW,
    )


def test_valid_claim_is_bound_to_version_timestamp_client_and_username() -> None:
    module = _load_claims()
    headers = _headers(module)

    assert _verify(module, headers) == CLIENT_ID
    assert headers[module.SIGNATURE_HEADER] == (
        "df89576cf5d06818bc0414b40b17afb392a497f4d1b36b6d1aebf85b7224a04c"
    )

    for name, value in (
        (module.VERSION_HEADER, "v2"),
        (module.TIMESTAMP_HEADER, str(NOW - 1)),
        (module.CLIENT_ID_HEADER, "B" * 43),
        (module.SIGNATURE_HEADER, "0" * 64),
    ):
        spoofed = {**headers, name: value}
        with pytest.raises(module.LoginClientClaimError):
            _verify(module, spoofed)

    with pytest.raises(module.LoginClientClaimError):
        _verify(module, headers, username="another-operator")


def test_claim_rejects_expired_future_and_malformed_inputs_without_leaking_id() -> None:
    module = _load_claims()
    cases = [
        _headers(module, timestamp=NOW - 31),
        _headers(module, timestamp=NOW + 6),
        {},
        {
            **_headers(module),
            module.CLIENT_ID_HEADER: f"{CLIENT_ID}\r\nX-Forged: yes",
        },
        {**_headers(module), module.TIMESTAMP_HEADER: "9" * 11},
        {**_headers(module), module.SIGNATURE_HEADER: "not-hex"},
    ]

    for headers in cases:
        with pytest.raises(module.LoginClientClaimError) as error:
            _verify(module, headers)
        assert CLIENT_ID not in str(error.value)


def test_username_canonicalization_is_bounded_and_unicode_stable() -> None:
    module = _load_claims()
    assert module.canonical_login_username("ｏｐｅｒａｔｏｒ") == "operator"

    for username in ("", "x" * 129, "operator\nforged", "😀" * 129):
        with pytest.raises(module.LoginClientClaimError):
            module.canonical_login_username(username)
