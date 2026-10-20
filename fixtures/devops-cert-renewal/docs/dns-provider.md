# Proveedor de DNS

Cuenta única `tienda-prod` con tres zonas: `tienda.example`, `pagos.example`
y `correo.example` (MX, SPF y DKIM del correo transaccional).

**El proveedor no tiene tokens por zona ni por tipo de registro.** Hay un solo
nivel de permiso de API: "escritura", que puede crear, cambiar y borrar
cualquier registro de cualquiera de las tres zonas. No se puede delegar un
subdominio a otra cuenta desde el panel.
