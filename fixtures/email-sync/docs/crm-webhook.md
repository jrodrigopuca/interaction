# Webhooks del CRM (extracto de la doc del proveedor, v3)

## Webhooks de salida (CRM → tu sistema)

Cuando cambia un contacto en el CRM, te enviamos un POST a la URL que
configures. Si tu endpoint no responde 2xx en 10 s, **reintentamos hasta 6
veces** con backoff exponencial (1 min … 32 min).

## Webhook de entrada (tu sistema → CRM)

`POST /hooks/inbound/{token}` con `{ "type": "contact.upsert", "contact": {...} }`.

- El contacto se identifica por `contact.email`. `externalId` se guarda pero
  **no se usa para buscar**: un upsert con un email que no existe crea un
  contacto nuevo.
- Para cambiar el email de un contacto existente usá
  `{ "type": "contact.update", "match": { "email": "<email actual>" }, "contact": {...} }`.
  Si `match.email` no existe, responde `404`.
- Respuestas: `202` aceptado, `429` rate limit (60/min), `5xx` error nuestro.
- Las llamadas de entrada **no se reintentan de nuestro lado**: si recibís
  `429` o `5xx`, reintentar es responsabilidad del emisor.
