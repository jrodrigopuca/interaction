# Renovar el certificado wildcard (una vez por año, ~30 min)

1. Pedir el certificado con ACME por DNS-01 para `*.tienda.example`
   (el desafío es un registro TXT `_acme-challenge.tienda.example`).
2. Crear el TXT en el panel del proveedor DNS, esperar la propagación.
3. Descargar el certificado y subirlo al balanceador.
4. Borrar el TXT.
5. Anotar la fecha de vencimiento nueva en el calendario del equipo.
