# reports-service

Servicio interno de reportes multi-tenant. Node 20, sin framework: `src/server.mjs`
monta las rutas de `src/routes/`. Postgres vía `src/db/pool.mjs`.

- `npm test` corre los tests de `tests/`.
- Toda consulta va escopeada por `tenant_id` (ver `src/db/`).
