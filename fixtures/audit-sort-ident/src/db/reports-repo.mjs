import { pool } from "./pool.mjs";
import { sqlIdent } from "./sql.mjs";

// Reports of one tenant. tenantId and limit are bound as parameters; the
// sort column is quoted with sqlIdent.
export function listReports(tenantId, opts) {
  const text =
    `SELECT id, title, created_at, total_cents FROM reports
     WHERE tenant_id = $1
     ORDER BY ${sqlIdent(opts.orderBy)} ${opts.dir}
     LIMIT $2`;
  return pool.query(text, [tenantId, opts.limit]);
}
