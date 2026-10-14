# backoffice

Backoffice de ventas. Módulos en `src/`: `auth`, `reportes`, `export` (CSV
para contabilidad), `notificaciones`, `inventario`, y utilidades en `shared`.

- `npm test` — suite completa.
- `MOD=auth npm run test:mod` — un módulo.

Montos: siempre en centavos enteros; se formatean recién al mostrar, en
formato argentino (`$ 1.234,56`). El CSV de contabilidad va con `;` como
separador y montos sin símbolo (`1234,56`), porque lo abre Excel en es-AR.
