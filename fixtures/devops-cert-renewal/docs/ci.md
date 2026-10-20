# CI

Los secrets del repositorio los puede leer cualquier workflow que llegue a
`main`. Tienen permiso de merge a `main` 12 personas (equipo de producto,
backend y dos contratistas). No hay entornos protegidos ni aprobación manual
para los workflows.

Hoy el repo tiene un secret: `DEPLOY_KEY`, una llave de deploy de solo lectura
al balanceador.
