import { pool } from "./pool.mjs";
import { sqlIdent } from "./sql.mjs";

export function listProducts(tenantId, { sort, limit }) {
  const text =
    `SELECT id, name, price_cents FROM products
     WHERE tenant_id = $1
     ORDER BY ${sqlIdent(sort)}
     LIMIT $2`;
  return pool.query(text, [tenantId, limit]);
}
