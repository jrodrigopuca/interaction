# plataforma

Tres servicios en un repo:

- `app/` — la app: usuarios, perfil, login. Dueña de los datos del usuario.
- `billing/` — facturación. Guarda su propia copia del cliente (nombre, email
  de facturación) porque emite comprobantes aunque la app esté caída.
- `crm-sync/` — empuja altas de usuarios al CRM (SaaS externo) por su webhook
  de entrada. Ver `docs/crm-webhook.md`.

Los servicios se hablan por el bus (`shared/bus.mjs`): hoy solo existe el
evento `user.registered`, que consumen `billing` y `crm-sync`.
