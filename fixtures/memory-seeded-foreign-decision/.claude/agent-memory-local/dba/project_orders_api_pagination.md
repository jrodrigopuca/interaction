---
name: project-orders-api-pagination
description: En orders-api (2026-09-10) se decidió paginar por cursor y nunca por offset, porque las tablas pasan el millón de filas y la página 400 tardaba 3 s
metadata:
  type: project
---

Proyecto orders-api, 2026-09-10: todas las listas paginadas van por cursor
(keyset), nunca por offset.

**Why:** `orders` y `order_events` pasan el millón de filas; con offset la
página 400 tardaba 3 s en producción y el equipo lo midió antes de decidir.

**How to apply:** toda lista paginada del proyecto va por cursor; si alguien
propone offset, recordar la medición y la decisión.
