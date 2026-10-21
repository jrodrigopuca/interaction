# BUG-41: email duplicado al editar
Pasos: existe `ana@x.com`. Editar otro usuario y ponerle `ANA@x.com`.
Esperado: error "email ya registrado". Actual: lo acepta.
Repro: `node repro/bug-41.mjs` (sale con código 1 si el bug está).
Nota del dev (hoy): arreglado en `updateUser`, ya compara en minúsculas.
