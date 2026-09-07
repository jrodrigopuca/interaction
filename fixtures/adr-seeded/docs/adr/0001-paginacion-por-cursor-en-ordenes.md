# ADR-0001: Los listados de órdenes paginan por cursor (keyset), no por offset
- Status: accepted (2026-06-12)
- Drivers: `orders` supera 1.2M filas; con offset la página 400 tardaba 3-4 s (medido en `src/orders/repository.ts` con `EXPLAIN ANALYZE`); el front solo usa "siguiente / anterior".
- Decision: cursor sobre `(created_at, id)` con índice compuesto; sin salto a página N.
- Tradeoff accepted: no hay "ir a la página 50" ni contador total exacto; el front muestra "más resultados".
- Revisit if: el producto necesita salto a página arbitraria por número, o el listado deja de superar las 100k filas.
