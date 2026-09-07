# Estado — migración de `parseMoney` a enteros en centavos

Done (verified how):
- `src/money.mjs` ya expone `parseMoney(str) -> cents` (entero). Verificado con `node --test src/money.test.mjs`: 14/14.
- `src/cart.mjs` migrado a centavos; suite 9/9.

Decided (why):
- Centavos enteros, no `Decimal`: sin dependencia nueva y el dominio no pasa de 2 decimales.

Open:
- `src/invoice.mjs` sigue en floats; es el último consumidor de `parseMoney` viejo.
- Falta borrar `parseMoneyLegacy` de `src/money.mjs` cuando invoice migre.

Next:
- Migrar `src/invoice.mjs` (usa `parseMoneyLegacy` y redondea a 2 decimales).

Stop if:
- Aparece un consumidor de `parseMoney` fuera de `src/` (un script o un reporte): ahí el cambio deja de ser interno y hay que frenar y revisar el alcance con el usuario antes de seguir.
