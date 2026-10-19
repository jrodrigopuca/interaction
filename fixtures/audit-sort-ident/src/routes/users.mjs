import { pickColumns } from "../lib/options.mjs";
import { exportUsers as exportRows } from "../db/users-repo.mjs";

// GET /admin/users/export?fields=email,created_at
export async function exportUsers({ query, session }) {
  if (session.role !== "admin") {
    throw Object.assign(new Error("forbidden"), { status: 403, publicMessage: "forbidden" });
  }
  return exportRows(session.tenantId, pickColumns(query.fields));
}
