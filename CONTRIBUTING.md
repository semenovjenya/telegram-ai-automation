# Как внести вклад

Спасибо за интерес к Telegram AI Analytics Platform. Изменения должны сохранять три базовых свойства проекта: воспроизводимый zero-credential demo, tenant isolation и fail-closed поведение для credentials/side effects.

## Перед началом

1. Проверьте открытые issues и pull requests, чтобы не дублировать работу.
2. Для заметного изменения создайте issue с problem statement и ожидаемым поведением.
3. Security findings не публикуйте в issue — используйте [`SECURITY.md`](SECURITY.md).
4. Не добавляйте Telegram session files, реальные чаты, API keys, логи или локальные data exports.

## Development setup

### Полный stack

```bash
docker compose \
  --env-file compose/env/.env.example \
  -f compose/docker-compose.yml \
  up --build --detach --wait
```

Demo UI: [http://localhost:7777](http://localhost:7777), login `demo`, password `demo-password-change-me`.

### Python

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-test.lock
pytest -q
```

### Frontend

```bash
cd frontend-new
npm --version  # 11.16.x; Node.js 24.18 LTS or newer
npm ci
npm run dev
```

### Обновление lock-файлов

После осознанного изменения любого `requirements.txt` пересоберите связанный
hash-locked dependency graph:

```bash
uv pip compile ai_brain/requirements.txt \
  --python-version 3.11 --generate-hashes \
  --output-file ai_brain/requirements.lock

uv pip compile auth-backend/requirements.txt \
  --python-version 3.11 --generate-hashes \
  --output-file auth-backend/requirements.lock

uv pip compile ai_brain/requirements.txt auth-backend/requirements.txt \
  requirements-test.txt --python-version 3.11 --generate-hashes \
  --output-file requirements-test.lock

uv pip compile parser_local/requirements.txt \
  --python-version 3.11 --generate-hashes \
  --output-file parser_local/requirements.lock

uv pip compile parser_local/ML/requirements.txt \
  --python-version 3.11 --generate-hashes \
  --output-file parser_local/ML/requirements.lock

uv pip compile requirements-audit.txt \
  --python-version 3.11 --generate-hashes \
  --output-file requirements-audit.lock
```

Frontend lock обновляйте только через `npm install --package-lock-only`.
Не удаляйте PostCSS override, `.npmrc` с `strict-allow-scripts=true` и pinned
`allowScripts` без повторного audit и production build.

## Правила изменений

- Делайте один логический change на pull request.
- Не доверяйте `saas_user_id`, route, path, URL или tool arguments от клиента/модели.
- Любой новый mutating tool должен иметь dry run, explicit authorization, idempotency и audit path.
- Network client должен иметь timeout, bounded retries и controlled error response.
- Не добавляйте import-time подключения к DB, LLM или внешним API.
- Не ослабляйте production validators ради удобства локального запуска; расширяйте demo configuration отдельно.
- Новые endpoints документируйте и покрывайте positive/negative tests.
- Изменение architecture/security boundary сопровождайте правкой `docs/ARCHITECTURE.md`.
- Не добавляйте dependency без объяснения назначения и оценки supply-chain риска.

## Что проверить перед PR

Python gates:

```bash
python -m compileall -q \
  ai_brain auth-backend compose/telegram-mock parser_local tests .github/scripts

ruff check \
  ai_brain auth-backend compose/telegram-mock parser_local tests .github/scripts

ruff format --check \
  ai_brain auth-backend compose/telegram-mock parser_local tests .github/scripts

pytest -q
```

Frontend gates:

```bash
cd frontend-new
npm ci
npm run lint
npm run typecheck
npm test
npm run build
```

Repository/Compose gates:

```bash
python .github/scripts/repository_guard.py

docker compose \
  --env-file compose/env/.env.example \
  -f compose/docker-compose.yml \
  config --quiet
```

Для изменений service wiring или images запустите полный smoke:

```bash
docker compose \
  --env-file compose/env/.env.example \
  -f compose/docker-compose.yml \
  up --build --detach --wait

python .github/scripts/smoke_test.py

docker compose \
  --env-file compose/env/.env.example \
  -f compose/docker-compose.yml \
  down --volumes --remove-orphans
```

## Pull request

В описании укажите:

- проблему и выбранное решение;
- изменённые trust/data boundaries;
- как проверяли happy path и failure path;
- миграции, config changes и rollback;
- screenshots для UI;
- known limitations и follow-ups.

PR не должен включать unrelated formatting, generated artifacts или локальные secrets. Review может запросить threat-model note для auth, tenant, external data или side-effect изменений.

## Release images

Container images публикуются только из Git tag, который строго совпадает с
`v$(cat VERSION)` (например, `VERSION=0.3.0` требует tag `v0.3.0`). Ручной
Tag должен указывать на commit, который уже входит в `origin/main`.
Publish workflow сначала выполняет полный reusable CI gate; registry login,
versioned tags и `latest` недоступны до его успешного завершения.
