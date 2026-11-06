# Security policy

## Supported versions

| Version | Security updates |
|---|---|
| Current `main` | Supported |
| Older commits/releases | Best effort only |

До появления стабильных tagged releases исправления безопасности делаются в текущей основной ветке.

## Как сообщить об уязвимости

Не публикуйте exploit, credentials, персональные данные или детали live Telegram account в issue/PR.

Предпочтительный канал — [GitHub private vulnerability report](https://github.com/semenovjenya/telegram-ai-automation/security/advisories/new). Если private reporting недоступен, создайте публичный issue только с заголовком `Security contact requested`, не раскрывая технических деталей; maintainer предложит закрытый канал.

В отчёт включите:

- затронутый commit/component;
- краткое описание и impact;
- минимальные шаги воспроизведения или proof of concept;
- необходимые условия и предполагаемую severity;
- возможную remediation;
- можно ли указать автора в advisory.

Не прикладывайте реальные токены. Если credential уже раскрыт, укажите только provider/type и последние четыре символа.

## Ожидаемый процесс

Целевые сроки, а не формальный SLA:

- подтверждение получения — до 3 рабочих дней;
- первичная оценка severity/scope — до 7 рабочих дней;
- согласованный remediation plan — после воспроизведения;
- disclosure — после выхода исправления и достаточного времени на обновление.

Срок зависит от сложности и внешних провайдеров. Reporter получает обновления при изменении статуса.

## Scope

В scope входят:

- auth/BFF/API gateway;
- tenant isolation, chat history и checkpoints;
- AI-BRAIN tools и prompt/tool boundary;
- Telegram adapter contract и repost confirmation protocol;
- Compose/CI/container configuration;
- утечки секретов или персональных данных из текущего repository tree/artifacts.

Вне scope без предварительного согласования:

- social engineering;
- destructive/availability testing и flood/DoS;
- действия против реальных Telegram-аккаунтов или сторонних API;
- automated scanning, создающий значимую нагрузку;
- уязвимости third-party service без доказанного влияния на этот проект;
- публичное раскрытие до согласованной даты.

Тестируйте только собственные локальные данные и synthetic demo. Не пытайтесь читать чужие tenant sessions, если для проверки можно использовать две локальные fixtures.

## Security model summary

- Browser JWT хранится в `HttpOnly`, `SameSite=Strict` cookie и проксируется только server-side BFF.
- Tenant identity извлекается из проверенного JWT; client-provided `saas_user_id` не является authority.
- AI и Telegram live endpoints защищаются отдельными service keys.
- LangGraph thread/checkpoint namespace и history storage key включают tenant.
- Public Telegram adapter synthetic и read-only; реальные session files находятся вне репозитория.
- Repost по умолчанию dry-run и требует отдельные confirmation token + idempotency key.
- Production validators отклоняют missing/placeholder credentials.

Эти меры уменьшают risk, но не являются заявлением об отсутствии уязвимостей.

## Credential incidents

Любой реальный секрет, когда-либо попавший в commit, log, artifact или container layer, считается скомпрометированным. Правильный порядок:

1. немедленно отозвать/rotate credential у provider;
2. оценить использование по audit logs;
3. убрать секрет из current tree и artifacts;
4. проверить всю Git-историю и forks;
5. согласовать history rewrite отдельно, если он необходим;
6. задокументировать root cause и preventive control.

Удаление строки из нового commit не отменяет утечку в старой истории.

## Safe harbor

Добросовестное исследование, соответствующее этой policy, будет рассматриваться как разрешённое: без нарушения приватности, повреждения данных, persistence и воздействия на третьих лиц. Остановитесь и свяжитесь с maintainer, если получили непреднамеренный доступ к чувствительным данным.
