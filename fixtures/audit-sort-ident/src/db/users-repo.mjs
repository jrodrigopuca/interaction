import { pool } from "./pool.mjs";
import { sqlIdentList } from "./sql.mjs";

// Admin export. The column list is quoted with sqlIdentList.
export function exportUsers(tenantId, columns) {
  const text =
    `SELECT ${sqlIdentList(columns)} FROM users
     WHERE tenant_id = $1
     ORDER BY "id"`;
  return pool.query(text, [tenantId]);
}
