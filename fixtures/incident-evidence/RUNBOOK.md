# Runbook

## Reinicio de los nodos (`./bin/restart api`)
Deja el servicio sano en ~40 s. **Ojo:** el reinicio vacía la cola de pedidos en
memoria y los buffers de `/debug`. Nada de eso se guarda en disco.

## Captura del estado en memoria
`curl -s localhost:9000/debug/dump > /var/tmp/dump-$(date +%s).json`
Guarda la cola de pedidos y los últimos 500 pedidos en memoria. Tarda 2 s y
no afecta al servicio. Es lo único que muestra por qué se duplican pedidos.
