# Reproducible local stack

The default stack is self-contained: PostgreSQL, AI-BRAIN, auth/API,
the frontend BFF, synthetic demo data, and a read-only Telegram adapter. No
Telegram account or private repository is needed.

```bash
cp compose/env/.env.example .env
docker compose --env-file .env -f compose/docker-compose.yml up --build -d
docker compose --env-file .env -f compose/docker-compose.yml ps
```

Open `http://localhost:7777`. The local demo credentials from the example env
are `demo` / `demo-password-change-me`. The default `LLM_PROVIDER=mock` gives a
deterministic, zero-credential AI path. For live model calls, set
`LLM_PROVIDER=openai` and inject a real `OPENAI_API_KEY` from a secret manager.
Mock mode routes requests and persists chat history, but it does not invoke RAG
or tools. The synthetic Telegram adapter is smoke-tested as an independent
read-only contract, not as synthetic RAG execution.
All published ports bind to `127.0.0.1` by default; changing `BIND_ADDRESS`
should be a deliberate deployment decision backed by TLS and network policy.

Stop the stack without deleting data:

```bash
docker compose --env-file .env -f compose/docker-compose.yml down
```

Use `down --volumes` only when you intentionally want to erase local
PostgreSQL state.

## Optional profiles

The local gateway is enabled with `--profile gateway`; observability services
are enabled with `--profile observability`.

```bash
docker compose --env-file .env -f compose/docker-compose.yml \
  --profile gateway --profile observability up --build -d
```

For direct database debugging, add the explicit development override:

```bash
docker compose --env-file .env \
  -f compose/docker-compose.yml -f compose/compose.override.yml up -d
```

## Live Telegram integration

The public stack intentionally has no Telegram credentials, sessions, or
message-sending code. Provide a separately deployed adapter compatible with
`chatbot/README.md`, then set `TELEGRAM_ADAPTER_URL`, `CHANNEL_SEARCH_URL` and
the same `TELEGRAM_TENANT_SIGNING_KEY` on auth-backend and the live adapter.
Mutating Telegram operations should be authenticated and guarded by an explicit
confirmation policy in that external service.

## Login limiter trust boundary

`LOGIN_CLIENT_SIGNING_KEY` is shared only by `frontend-new` and
`auth-backend`. The BFF signs its opaque HttpOnly login-client cookie so the
backend can rate-limit distinct browsers even though every request arrives from
the same BFF peer. Generate an independent secret of at least 32 characters for
production; never reuse JWT, AI, or Telegram keys. Production auth refuses
unsigned, stale, malformed, or incorrectly signed client claims.
