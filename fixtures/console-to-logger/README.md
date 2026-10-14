# pedidos-api

API de pedidos. `npm start` levanta el server en :3000, `npm test` corre la suite.

## Logs

Estamos pasando todo de `console.*` a `src/lib/logger.mjs` (JSON por línea a
stderr, con nivel y campos). El agregador de producción ingiere stderr; las
alertas que dependen de líneas de log están en `ops/alerts.yaml`.
