# Production release checklist

Default Compose — воспроизводимый demo, а не готовый production manifest. Перед подключением реальных пользователей, Telegram-сессий или платного LLM владелец релиза должен закрыть каждый пункт ниже и сохранить evidence в release/incident системе.

## 1. Репозиторий и история

- [ ] Любой credential, когда-либо попадавший в Git, отозван у провайдера; удаление строки из текущего branch не считается ротацией.
- [ ] Current tree и полная Git-история проверены secret scanner-ом.
- [ ] Проверены forks, Actions logs, release artifacts, container layers и package registries.
- [ ] Generated logs, Telegram session files, локальные выгрузки и персональные данные не отслеживаются Git.
- [ ] Если нужна очистка истории, согласован maintenance window: переписывание истории и force push затрагивают все clones, forks, branches и открытые PR.
- [ ] Branch protection требует зелёный CI и review для production branch.

Не запускайте history rewrite как обычный скрипт из README. Сначала отзовите секрет, создайте backup mirror, согласуйте операцию с владельцами репозитория и опубликуйте инструкции по повторному clone.

## 2. Secrets и runtime configuration

- [ ] `compose/env/.env.example` не используется как production env.
- [ ] `PUBLIC_APP_ORIGIN` задан как точный внешний HTTPS origin; ingress удаляет клиентские `Forwarded`/`X-Forwarded-*` и формирует собственные.
- [ ] Секреты передаются через managed secret store, не через image, Git, command line или публичные `NEXT_PUBLIC_*` variables.
- [ ] `ENVIRONMENT=production` и `LLM_PROVIDER=openai` заданы явно.
- [ ] `OPENAI_API_KEY`, `AI_BRAIN_API_KEY`, `JWT_SECRET_KEY`, `POSTGRES_PASSWORD`, `CHANNEL_SEARCH_API_KEY`, `TELEGRAM_API_KEY`, `TELEGRAM_TENANT_SIGNING_KEY` и `LOGIN_CLIENT_SIGNING_KEY` уникальны, имеют минимум 32 символа и владельца/rotation date.
- [ ] `CHANNEL_SEARCH_URL`, `CHANNEL_SEARCH_API_KEY`, `TELEGRAM_API_URL` и `TELEGRAM_API_KEY` заданы явно; URL не указывают на mock, loopback, example или demo targets.
- [ ] `DEFAULT_PASSWORD_HASH` содержит PBKDF2 hash; plaintext `DEFAULT_PASSWORD` не задан.
- [ ] `CORS_ORIGINS` содержит только реальные HTTPS origins, без wildcard.
- [ ] JWT issuer/audience/lifetime проверены; signing secret не переиспользуется другими сервисами.
- [ ] В логах, traces и error responses включена redaction для Authorization, cookies, API keys, Telegram identifiers и user content.

Production validators намеренно отклоняют пустые, короткие и placeholder secrets. Не обходите эти проверки изменением environment name.

## 3. Network и browser edge

- [ ] Public ingress открывает только TLS endpoint; AI-BRAIN и PostgreSQL недоступны из интернета.
- [ ] Reverse proxy корректно выставляет и очищает `X-Forwarded-Proto`/`Host`; cookie получает `Secure` через HTTPS.
- [ ] HSTS, CSP, request/body limits и security headers проверены на реальном ingress.
- [ ] Login и AI endpoints защищены rate limits, abuse detection и tenant quotas.
- [ ] BFF подписывает login-client claim отдельным ключом; auth-backend отклоняет unsigned/stale claims и не доверяет forwarding headers.
- [ ] BFF proxy allowlist не расширен произвольными URL/path и не следует redirects.

## 4. Identity и tenant isolation

- [ ] Пользователи хранятся во внешнем identity store или в явно спроектированной account database; demo bootstrap user отключён.
- [ ] `saas_user_id` всегда извлекается из проверенного JWT и не доверяется body/query/header клиента.
- [ ] Есть тесты отрицательного доступа между двумя tenant с одинаковым `session_id`.
- [ ] Есть процесс revoke/logout, key compromise и удаления пользователя.
- [ ] Administrative endpoints отделены отдельными roles/claims и аудитом.

## 5. PostgreSQL и state durability

- [ ] Используется managed/replicated PostgreSQL с encryption at rest и TLS in transit.
- [ ] Выполнен restore drill для history, session index и LangGraph checkpoint tables.
- [ ] Определены RPO/RTO, retention, PITR, migration owner и rollback procedure.
- [ ] Connection pool limits согласованы с числом replicas и лимитом базы.
- [ ] `/health/ready` проверяется orchestrator-ом; traffic не идёт в instance до готовности checkpointer.
- [ ] Volatile memory fallback выключен (`ALLOW_MEMORY_CHECKPOINT_FALLBACK=false`).

## 6. LLM и RAG

- [ ] Выбраны модель, cost budget, timeout/retry policy и provider quota alerts.
- [ ] Prompt/tool inputs не содержат secrets; чувствительные пользовательские данные минимизируются.
- [ ] RAG documents имеют tenant/source ACL, provenance и deletion workflow.
- [ ] Есть защита от prompt injection в retrieved content и tool arguments.
- [ ] Ошибки провайдера приводят к controlled degraded response, а не к утечке stack trace.

## 7. Live Telegram adapter

- [ ] Adapter развёрнут отдельно от public core и соответствует контракту [`chatbot/README.md`](../chatbot/README.md).
- [ ] Telegram credentials/session files находятся в отдельном secret storage с минимальными permissions.
- [ ] Все adapter endpoints аутентифицированы; tenant ownership проверяется до чтения/отправки.
- [ ] User/chat/message identifiers и content не попадают в незащищённые логи.
- [ ] Исходящий message text передаётся только JSON body; query strings и request bodies redacted на ingress/proxy/adapter.
- [ ] Есть Telegram rate-limit/backoff, flood-wait handling, delivery audit и kill switch.
- [ ] Public synthetic mock не используется как источник business data.

## 8. Repost side effects

- [ ] Live executor подключён только в private adapter/runtime; public demo остаётся read-only.
- [ ] Задан сильный `REPOST_CONFIRMATION_SECRET`, отдельный от JWT/API secrets.
- [ ] `REPOST_TOOL_PATH`, `REPOST_CONFIG_DIR` и `REPOST_INPUT_DIR` заданы absolute staging/production paths; tenant `N` видит только regular non-symlink `REPOST_CONFIG_DIR/N.json` и `REPOST_INPUT_DIR/N/forward_post_*.json`.
- [ ] `REPOST_IDEMPOTENCY_DB` указывает на persistent, shared storage для всех replicas.
- [ ] UI показывает source, message and target из dry run до подтверждения.
- [ ] Execution принимает только structured confirmation; conversational text не является согласием.
- [ ] Tool output оборачивается как bounded untrusted data; prompt-injection из tool result не становится system instruction.
- [ ] Проверены duplicate request, changed target, timeout after send, retry и operator reconciliation.
- [ ] Есть audit trail: кто, когда и какую exact operation подтвердил, без сохранения секретов.

## 9. Observability и incident response

- [ ] Metrics/logs/traces имеют environment, service, request ID и tenant-safe correlation.
- [ ] Настроены alerts на readiness, error rate, latency, DB pool, provider quota, auth failures и repost anomalies.
- [ ] Log retention соответствует требованиям к персональным данным.
- [ ] Runbooks покрывают DB outage, LLM outage, leaked credential, Telegram flood wait и duplicate side effect.
- [ ] Назначены on-call/incident owner и канал security disclosure из [`SECURITY.md`](../SECURITY.md).

## 10. Supply chain и release

- [ ] CI зелёный на exact release commit.
- [ ] Release tag строго равен `v$(cat VERSION)`, tagged commit входит в `origin/main`, image workflow прошёл полный reusable CI gate до registry login/publish.
- [ ] Dependency audit и обязательный CI container scan зелёные; исключения для critical/high документированы, имеют владельца и срок.
- [ ] Container images закреплены digest-ами или проходят controlled promotion.
- [ ] SBOM/provenance сохранены рядом с release artifact.
- [ ] Images запускаются non-root, с read-only filesystem и минимальными capabilities, где это возможно.
- [ ] Deploy проверен в staging с production-like secrets/network policies.
- [ ] Rollback отрепетирован; предыдущие images и compatible DB migration доступны.

## Release sign-off

Зафиксируйте перед релизом:

```text
release commit/tag:
environment:
release owner:
security reviewer:
database restore drill:
secret scan evidence:
smoke test evidence:
rollback target:
known accepted risks and expiry:
```

Незакрытый пункт должен иметь явно принятого владельца, срок и компенсирующую меру. Без этого релиз не считается готовым к live Telegram data или mutating operations.
