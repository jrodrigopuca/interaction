# Runbook
- Subir el pool de conexiones: `./bin/set pool_size N`. **El pool se lee al
  arrancar:** el cambio no hace nada hasta `./bin/restart api` (unos 40 s).
- Reiniciar la API: `./bin/restart api`.
