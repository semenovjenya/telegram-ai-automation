# Observability profile

The optional `observability` Compose profile starts Prometheus, Loki, Alloy,
Grafana and an isolated read-only Docker API proxy. Alloy collects logs only
from containers carrying the tracked `logging_enabled=true` label; Prometheus
monitors the observability services themselves. Grafana provisions both data
sources and repository dashboards.

```bash
docker compose \
  --env-file compose/env/.env.example \
  -f compose/docker-compose.yml \
  --profile observability up --detach
```

Grafana is available at `http://localhost:3000`. The demo credentials come from
`compose/env/.env.example`; change `GRAFANA_ADMIN_PASSWORD` before sharing the
profile. Published ports bind to `127.0.0.1` by default. A shared deployment must
use a deliberate bind address, TLS and network policy. Only the socket proxy
mounts the Docker socket. It exposes GET-only container discovery/log APIs to
Alloy over an internal Compose network; Alloy has no direct daemon socket and
mutating Docker API calls are denied.
