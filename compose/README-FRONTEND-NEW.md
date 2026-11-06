# Frontend container

The supported path is the complete stack in `compose/docker-compose.yml`; see
`compose/README.md`. For UI-only work against APIs already running on the host:

```bash
docker compose -f compose/docker-compose-frontend-new.yml up --build
```

The standalone container expects the auth/backend gateway on host port `8001`
and reaches it through `http://host.docker.internal:8001/api`. Browser requests
still use the frontend's same-origin `/api/*` BFF, so the backend JWT remains in
an HttpOnly cookie and is never exposed through a public client-side URL.

Override the server-only backend URL when the gateway uses another host port:

```bash
AUTH_BACKEND_URL=http://host.docker.internal:9001/api \
  PUBLIC_APP_ORIGIN=http://localhost:7777 \
  docker compose -f compose/docker-compose-frontend-new.yml up --build
```

Use `FRONTEND_PORT` to change the published UI port and set
`PUBLIC_APP_ORIGIN` to that exact browser-visible origin. Hardened environments
require HTTPS. The standalone frontend does not expose or require a WebSocket
endpoint.
