# Notificaciones

- Hoy: email de confirmación de compra y de envío, desde `src/notify.js`,
  llamado dentro del request de checkout.
- Volumen: ~1.200 emails por día, picos de 40 por minuto en promociones.
- Problema actual: cuando el proveedor de email tarda, el checkout tarda.
- Pedido del negocio: sumar WhatsApp el próximo trimestre.
