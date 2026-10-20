# tienda — infraestructura

Sitio y API detrás de un certificado wildcard (`*.tienda.example`) que se
renueva una vez por año. Hoy se hace a mano, 30 minutos, con
`docs/RUNBOOK-cert.md`. El DNS lo maneja un proveedor externo (`docs/dns-provider.md`).

- `.github/workflows/deploy.yml` — deploy a producción al mergear a `main`.
- `docs/ci.md` — cómo funciona el CI del repo.
