# ADR-0001: Paginación por cursor en el listado de pedidos
- Status: accepted
- Drivers: `orders` tiene 12 millones de filas; con OFFSET la página 400 tardaba 6 s.
- Decision: el listado pagina por cursor sobre `(created_at, id)`.
- Tradeoff accepted: no se puede saltar a la página N; solo siguiente y anterior.
- Revisit if: el producto necesita saltar a la página N.
