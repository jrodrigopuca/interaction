// Listado de pedidos, paginado por cursor (ver docs/adr/0001-cursor-pagination.md).
export function listOrders(db, { after, limit = 50 }) {
  return db.query(
    "SELECT * FROM orders WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT $3",
    [after?.createdAt ?? "infinity", after?.id ?? 0, limit]);
}
