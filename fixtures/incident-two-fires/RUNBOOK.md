# Runbook
- Pagos duplicados o inconsistentes: `./bin/flag off payments_async` (reversible,
  detiene al escritor de pagos en menos de un minuto).
- 502 en checkout: ver el balanceador. Causas posibles: timeouts del upstream,
  capacidad. No hay palanca de un comando.
