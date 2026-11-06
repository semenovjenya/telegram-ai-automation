# Portfolio verification

Prepared on 2026-11-06 from source commit `9fbc463` of the private Telegram AI Analytics Platform. The source repository remains private and unchanged. This repository starts with a new history.

## Observed checks

| Check | Result |
| --- | --- |
| Fresh Python 3.11 install with `--require-hashes -r requirements-test.lock` | Passed |
| `python -m pytest -q` | **207 passed** |
| Repository guard | Passed |
| Python lint | Passed |
| Offline graph example | GENERAL, SALES, BARTER; two in-memory messages per scenario |
| Network-disabled demo test | Passed |
| Context benchmark | 14,055 → 8,485 bytes for 50 previous messages; 0% reduction for 10 |
| Frontend ESLint | Passed |
| TypeScript checking | Passed |
| Frontend tests | **31 passed** |
| Next.js production build | Passed |
| Frontend `npm audit` after compatible lockfile updates | 0 reported vulnerabilities |
| Default Docker Compose configuration | Passed |

The frontend audit initially reported 16 vulnerable dependency entries, including one critical. Compatible updates to the lockfile and a final brace-expansion update cleared reported findings. Frontend lint/types/tests/build passed after the main update; lint and audit were repeated after the final lint-only dependency update. This is a point-in-time dependency result, not a security certification.

## Scope of demonstration

The standalone example uses the real LangGraph workflow with the project's mock agents, an in-memory checkpointer and explicitly substituted in-memory history storage. Its regression test rejects network connections. It does not test PostgreSQL restart persistence, browser authentication or a live model.

The benchmark uses actual `build_messages` behavior with synthetic data. It compares the bounded input with sending the full loaded history window, including the current question once in both cases. It measures canonical role/content JSON bytes, not model token billing. Dropped old messages are reported explicitly; no lossless compression claim is made.

## Publication hygiene

- The original Git history was not copied.
- Telegram sessions, account credentials, user-message exports and generated runtime artifacts are not included.
- Demo datasets and environment examples are retained and marked as synthetic/local.
- Existing Apache 2.0 license and notices are preserved.
- CI definitions are retained under `docs/ci` as templates. The available GitHub credential lacks workflow scope, so no active CI result or badge is claimed.
- The repository guard checks the templates, tracked artifact rules, token patterns, version manifest and Compose boundaries. Passing it does not mean container vulnerability scans have run.

## Not verified in this export

Docker daemon was unavailable. Full Compose startup, container image vulnerability scans and the BFF/PostgreSQL smoke were not rerun. Live OpenAI, channel-search/RAG, real Telegram sessions, outgoing reposts and production throughput were not exercised.

Real Telegram execution requires a separate authenticated adapter. A model-generated or conversational agreement is not sufficient approval: the live repost design requires the structured confirmation/idempotency path. Demo does not send messages.
