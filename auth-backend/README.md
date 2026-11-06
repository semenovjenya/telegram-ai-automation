# Auth backend и tenant-aware gateway

FastAPI-сервис аутентификации и внутренний API gateway. В публичной
архитектуре browser обращается к Next.js BFF; BFF хранит JWT в HttpOnly
cookie и уже сервер-сервер вызывает этот сервис.

Рекомендуемый запуск — полный [Compose stack](../compose/README.md). Auth
backend не следует публиковать напрямую в production.

## Контракт

| Метод | Endpoint | Назначение |
|---|---|---|
| POST | /api/auth/login | Проверка bootstrap user и выдача JWT для BFF |
| GET | /api/auth/me | Текущий пользователь из проверенного JWT |
| POST | /api/auth/logout | Серверная часть logout |
| GET | /api/dashboard | Агрегированный dashboard с явным data_source |
| * | /api/ai/{allowlisted path} | Tenant-safe proxy к AI-BRAIN |
| * | /api/chatbot/{allowlisted path} | Proxy к Telegram adapter |
| GET | /health | Liveness |

AI proxy принимает только известные method/path combinations, удаляет
caller credentials и identity/network metadata. Outbound headers собираются
по allowlist: bounded `Accept`, `Content-Type`, `X-Request-ID` и валидный
W3C `traceparent`; service/tenant claims добавляет сам gateway. `saas_user_id`
всегда берётся из проверенного JWT. Доступ к PNG ограничен префиксом
текущего tenant.

Для tenant-scoped Telegram routes gateway создаёт короткоживущую
HMAC-SHA256 claim, связанную с tenant, method и normalized path. Adapter
проверяет service API key, подпись, freshness и replay. Клиент не может
самостоятельно выбрать tenant.

## Локальный demo

Из корня репозитория:

~~~bash
docker compose \
  --env-file compose/env/.env.example \
  -f compose/docker-compose.yml \
  up --build --detach --wait
~~~

UI доступен на [http://localhost:7777](http://localhost:7777). Локальные
credentials из .env.example являются только demo fixture и блокируются
production-валидацией.

Для запуска сервиса отдельно:

~~~bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r auth-backend/requirements.lock
cd auth-backend
python -m uvicorn main:app --reload --port 8001
~~~

Перед отдельным запуском задайте необходимые переменные окружения.

## Security configuration

Staging/production startup отказывает при слабой или
placeholder-конфигурации. `ENVIRONMENT` принимает только
`development`, `test`, `staging` или `production`; опечатка блокирует
старт.
Обязательны:

- JWT_SECRET_KEY — уникальный секрет не короче 32 символов;
- DEFAULT_USERNAME и DEFAULT_PASSWORD_HASH в формате PBKDF2;
- AI_BRAIN_API_KEY и TELEGRAM_API_KEY;
- отдельный TELEGRAM_TENANT_SIGNING_KEY, не совпадающий с другими ключами;
- отдельный LOGIN_CLIENT_SIGNING_KEY, не совпадающий с JWT/service keys;
- точный allowlist в CORS_ORIGINS;
- DASHBOARD_DATA_SOURCE=live.

Plaintext DEFAULT_PASSWORD оставлен только для локального demo. В
staging/production он должен быть пустым.

Next.js BFF создаёт стабильный случайный `taap_login_client` cookie
(`HttpOnly`, `SameSite=Strict`) и передаёт его только в короткоживущем
HMAC claim, связанном с version, timestamp и canonical username.
Staging/production auth-backend требует корректный claim; direct-peer
fallback разрешён только в development/test. Сырой browser pseudonym не
хранится в limiter и не пишется в лог.

Login защищён bounded in-process limiter по verified client и паре
client/username. Глобального username scope нет: один browser не может
заблокировать учётную запись для остальных, а смена usernames не обходит
client-wide budget. Настройки:

- LOGIN_RATE_LIMIT_MAX_ATTEMPTS — по умолчанию 5;
- LOGIN_RATE_LIMIT_WINDOW_SECONDS — 300;
- LOGIN_RATE_LIMIT_BLOCK_SECONDS — 900;
- LOGIN_RATE_LIMIT_MAX_ENTRIES — 10000;
- LOGIN_CLIENT_CLAIM_MAX_AGE_SECONDS — 30;
- LOGIN_CLIENT_CLAIM_FUTURE_SKEW_SECONDS — 5.

При заполнении limiter закрывает вход, а превышение возвращает
429 и Retry-After. Несколько workers/replicas не делят in-process state,
поэтому production ingress также должен иметь распределённый rate limit.

ASGI middleware ограничивает тело запроса во время чтения потока: 8 KiB для
login, 64 KiB для отправки chat message и 1 MiB для остальных изменяющих
запросов. Проверка не доверяет отсутствующему или некорректному
`Content-Length`; ingress должен дублировать эти лимиты как внешний слой защиты.

Telegram claim verifier настраивается через:

- TELEGRAM_TENANT_CLAIM_MAX_AGE_SECONDS — 30;
- TELEGRAM_TENANT_CLAIM_FUTURE_SKEW_SECONDS — 5;
- TELEGRAM_TENANT_REPLAY_MAX_ENTRIES — 10000.

## Проверки

Из корня репозитория:

~~~bash
pytest -q tests/security_auth_backend_test.py \
  tests/security_login_rate_limit_test.py \
  tests/security_telegram_tenant_claim_test.py
~~~

Модель trust boundaries и browser flow:
[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md).
