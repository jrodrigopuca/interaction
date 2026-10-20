# Ticket #418 — importador de catálogos con ";"

Parte 1 (ayer): `parseCSVLine(line, sep = ",")`, con sus tres casos de prueba.
Tests: 16/16. Mensaje de commit sugerido entonces:
`feat(csv): separador configurable como segundo parámetro, #418`

Parte 2 (pendiente): el proveedor manda los campos sin comillas con espacios
alrededor (` 1234 ; Remera azul ; 3 `). Hace falta una opción `trim` para
recortar los espacios de los campos SIN comillas. El interior de un campo
entrecomillado no se toca (contrato #412, ver tests).
