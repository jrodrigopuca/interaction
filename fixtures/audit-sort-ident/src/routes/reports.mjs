import { buildListOptions } from "../lib/options.mjs";
import { listReports } from "../db/reports-repo.mjs";

// GET /reports/export?sort=&dir=&limit=
export async function exportReports({ query, session }) {
  const opts = buildListOptions(query);
  return listReports(session.tenantId, opts);
}
