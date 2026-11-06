"""Regression tests for bounded, fail-closed login throttling."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_rate_limit():
    spec = importlib.util.spec_from_file_location(
        "security_login_rate_limit",
        ROOT / "auth-backend" / "rate_limit.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_limiter_isolates_accounts_between_clients_and_exposes_retry_after() -> None:
    module = _load_rate_limit()
    clock = FakeClock()
    limiter = module.LoginRateLimiter(
        max_attempts=2,
        window_seconds=30,
        block_seconds=60,
        max_entries=30,
        clock=clock,
    )

    assert limiter.register_attempt("operator", "203.0.113.7") is None
    assert limiter.register_attempt("operator", "203.0.113.7") is None
    assert limiter.register_attempt("operator", "203.0.113.7") == 60

    # There is deliberately no global username bucket: another verified client
    # cannot be locked out by the first client's targeted failures.
    assert limiter.register_attempt("operator", "198.51.100.4") is None

    # Rotating usernames does not bypass the direct-client scope either.
    other = module.LoginRateLimiter(
        max_attempts=2,
        window_seconds=30,
        block_seconds=60,
        max_entries=30,
        clock=clock,
    )
    assert other.register_attempt("first", "203.0.113.9") is None
    assert other.register_attempt("second", "203.0.113.9") is None
    assert other.register_attempt("third", "203.0.113.9") == 60


def test_success_forgives_current_attempt_without_resetting_client_failures() -> None:
    module = _load_rate_limit()
    limiter = module.LoginRateLimiter(
        max_attempts=2,
        window_seconds=30,
        block_seconds=60,
        max_entries=30,
    )

    assert limiter.register_attempt("operator", "client-a") is None
    assert limiter.register_attempt("known-account", "client-a") is None
    limiter.record_success("known-account", "client-a")

    # The known-account pair is cleared, but the earlier client-wide failure
    # remains. One more rotated username exhausts that client budget.
    assert limiter.entry_count == 2
    assert limiter.register_attempt("rotated-account", "client-a") is None
    assert limiter.register_attempt("another-account", "client-a") == 60

    # A distinct client remains unaffected even for the original username.
    assert limiter.register_attempt("operator", "client-b") is None


def test_capacity_exhaustion_fails_closed_without_evicting_active_entries() -> None:
    module = _load_rate_limit()
    limiter = module.LoginRateLimiter(
        max_attempts=5,
        window_seconds=30,
        block_seconds=60,
        max_entries=2,
    )

    assert limiter.register_attempt("first", "client-a") is None
    assert limiter.entry_count == 2
    retry_after = limiter.register_attempt("second", "client-b")
    assert retry_after is not None and retry_after >= 1
    assert limiter.entry_count == 2


def test_limiter_has_only_client_and_pair_scopes() -> None:
    module = _load_rate_limit()
    limiter = module.LoginRateLimiter(
        max_attempts=5,
        window_seconds=30,
        block_seconds=60,
        max_entries=10,
    )

    assert limiter.register_attempt("ＯＰＥＲＡＴＯＲ", "client-a") is None
    assert set(key.partition(":")[0] for key in limiter._entries) == {  # noqa: SLF001
        "client",
        "pair",
    }
