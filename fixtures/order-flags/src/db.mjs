// Los pedidos se guardan tal cual en la tabla `orders` (columnas is_paid, is_shipped).
export async function saveOrder(db, o) {
  await db.query("INSERT INTO orders (id, is_paid, is_shipped) VALUES ($1, $2, $3)",
    [o.id, o.isPaid, o.isShipped]);
}
