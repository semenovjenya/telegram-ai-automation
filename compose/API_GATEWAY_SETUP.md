# Local API gateway

The gateway is part of the main Compose file and is disabled by default to
avoid occupying another host port.

```bash
docker compose --env-file .env -f compose/docker-compose.yml \
  --profile gateway up --build -d
curl --fail http://localhost:8080/health
```

It sends both `/` and `/api/*` to the Next.js application. The same-origin BFF
keeps JWTs in HttpOnly cookies and is the only browser-facing API path; the
gateway never exposes auth-backend or AI-BRAIN directly. Its configuration is
tracked in `compose/api/nginx.conf`; local TLS termination is intentionally left
to a developer proxy such as Caddy or Traefik rather than shipping fake
certificates.
