# Runbook de incidentes

1. **Mirá qué cambió en la última hora** (`logs/changes.log`).
2. Si la caída coincide con un flag: `./bin/flag off <nombre>`. Es reversible
   y el servicio vuelve en menos de un minuto.
3. Si coincide con un deploy: `./bin/rollback` (vuelve a la versión anterior,
   unos 4 minutos).
4. Recién con el servicio arriba se busca la causa raíz.
