# orders-api

API de pedidos. Corre en Kubernetes (`k8s/`).

## Carga (últimos 90 días)

- Promedio: 40 rps; pico diario: 120 rps (12:30–13:30).
- Una réplica aguanta ~100 rps con p99 < 300 ms (prueba de carga del 2026-09-30).
- Hoy: 2 réplicas fijas. Costo por réplica: USD 70/mes.
