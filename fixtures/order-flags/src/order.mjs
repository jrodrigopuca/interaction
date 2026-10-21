// Un pedido pasa por: creado → pagado → enviado.
export function newOrder(id) {
  return { id, isPaid: false, isShipped: false };
}
export function canShip(o) {
  return o.isPaid && !o.isShipped;
}
export function label(o) {
  if (o.isShipped) return "Enviado";
  if (o.isPaid) return "Pagado";
  return "Pendiente";
}
