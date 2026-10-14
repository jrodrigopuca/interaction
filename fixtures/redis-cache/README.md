# catalogo-api

API del catálogo. Deploy: el `Procfile` levanta `web` y `worker`.

- `src/server.mjs` — HTTP: productos (cacheados), login, rate limit por IP.
- `src/worker.mjs` — consume la cola `price-updates` y recalcula precios.
- `src/redis.mjs` — cliente compartido (`REDIS_URL`).

Tests: `npm test` (usan un fake del cliente, no necesitan Redis).
