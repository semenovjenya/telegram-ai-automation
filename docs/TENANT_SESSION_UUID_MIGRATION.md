# Tenant/session UUID compatibility

## Version boundary

Before the tenant-isolation hardening, chat storage used a global key:

```text
uuid5(NAMESPACE_DNS, session_id)
```

The current runtime deliberately uses a different, tenant-scoped key:

```text
uuid5(NAMESPACE_URL, "tenant:<saas_user_id>:session:<trimmed_session_id>")
```

This is a security boundary, not a transparent hash refactor. Two tenants may
legitimately use the same public `session_id`, so the old key cannot remain a
fallback without reintroducing cross-tenant history access.

## Public demo

No automatic migration is shipped for the public demo. Its bundled data is
synthetic and disposable; recreate the local PostgreSQL volume when upgrading
from a pre-tenant build. The current schema and `ai_brain_sessions` index are
then created from scratch on startup.

## Existing non-demo installations

Do not deploy the new key derivation over a database whose old conversations
must be retained without an explicit migration. The legacy history table does
not contain an authoritative tenant owner for every UUID, so ownership cannot
be inferred safely from the UUID itself.

The installation owner must:

1. stop writes and take a verified PostgreSQL backup;
2. export `old_storage_uuid -> saas_user_id + original_session_id` mappings from
   an authoritative identity/session system;
3. quarantine rows without an unambiguous owner instead of assigning them to a
   default tenant;
4. copy verified messages to the new tenant-scoped UUID and populate
   `ai_brain_sessions` in one reviewed transaction or migration job;
5. start new LangGraph threads, or migrate checkpoint rows using the installed
   LangGraph version's supported schema tooling;
6. validate negative access with two tenants sharing the same `session_id`
   before reopening traffic.

`CREATE TABLE IF NOT EXISTS` only creates missing structures; it does not
rewrite old UUIDs or prove tenant ownership. Rollback must restore the backup,
not enable a global-key dual-read fallback.
