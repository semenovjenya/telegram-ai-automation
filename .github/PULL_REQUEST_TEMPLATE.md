## Что изменено

<!-- Кратко: проблема, решение и user-visible результат. -->

## Границы и риски

<!-- Tenant/auth/data flow, external APIs, side effects, migrations, rollback. -->

- [ ] Нет изменений trust/data boundaries.
- [ ] Boundaries изменены и описаны ниже / в `docs/ARCHITECTURE.md`.

## Проверка

<!-- Команды и результаты; приложите screenshot для UI. -->

- [ ] Python tests
- [ ] Frontend lint/typecheck/tests/build (если затронут frontend)
- [ ] Compose config/smoke (если затронут service wiring)
- [ ] Failure/negative path

## Checklist

- [ ] PR решает одну логическую задачу и не содержит unrelated generated files.
- [ ] Нет secrets, Telegram session files, персональных данных или чувствительных логов.
- [ ] Client/model input не становится authority для tenant или side effect.
- [ ] Новые mutating operations имеют dry run, explicit auth, idempotency и audit path.
- [ ] Добавлены/обновлены tests и документация.
- [ ] Config/migration/rollback описаны.
- [ ] Known limitations и follow-ups перечислены.
