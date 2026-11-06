"""Deterministic environment for unit tests."""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("API_KEY", "unit-test-api-key-32-characters")
os.environ.setdefault("OPENAI_API_KEY", "unit-test-openai-key-32-characters")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("POSTGRES_PASSWORD", "unit-test-postgres-password")
os.environ.setdefault("CHECKPOINT_BACKEND", "memory")
os.environ.setdefault("CHANNEL_SEARCH_URL", "http://channel-search.test")
