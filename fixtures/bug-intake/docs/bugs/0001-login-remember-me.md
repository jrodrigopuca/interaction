# "Recordarme" no persiste la sesión después de cerrar el navegador

- Severidad: media (bloquea un flujo, hay workaround: volver a loguearse)
- Frecuencia: siempre
- Entorno / build: staging, build 2026.10.02

## Pasos

1. Ir a /login, tildar "Recordarme", entrar con un usuario válido.
2. Cerrar el navegador por completo y volver a abrir /dashboard.

## Esperado

El dashboard abre con la sesión activa.

## Obtenido

Redirige a /login.

## Evidencia

La cookie `sid` se emite sin `Max-Age` ni `Expires` (cookie de sesión).

## Notas

Lead para dev: el flag `remember` no llega al emisor de la cookie. Tu call.
