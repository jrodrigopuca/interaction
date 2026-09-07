---
name: feedback-index-rollback-and-team-block
description: El usuario pidió que toda recomendación de índice traiga el DDL de rollback al lado y que la respuesta cierre con un bloque "Para el equipo" de tres líneas sin jerga
metadata:
  type: feedback
---

Cuando recomiendo un índice, el `CREATE INDEX CONCURRENTLY` va acompañado, en el
mismo bloque, del `DROP INDEX CONCURRENTLY` que lo revierte. Y la respuesta
cierra con una sección `## Para el equipo`: tres líneas en lenguaje no técnico
que digan qué cambia, qué riesgo tiene y cómo se vuelve atrás.

**Why:** lo pidió textualmente ("cada índice con su rollback al lado, y al
final tres líneas que pueda pegar en el canal del equipo"). Su equipo aprueba
cambios de base leyendo esa sección, no el DDL.

**How to apply:** en cualquier recomendación de índice, sin que lo vuelva a
pedir. Si la recomendación es NO crear el índice, el bloque final igual va.
