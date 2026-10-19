// Normalizes list/query options coming from the query string.
// Identifiers are made safe at the SQL layer (see db/sql.mjs), so these
// helpers only deal with defaults and limits.

const MAX_LIMIT = 500;

export function clampLimit(raw) {
  const n = Number.parseInt(raw, 10);
  if (!Number.isFinite(n) || n <= 0) return 50;
  return Math.min(n, MAX_LIMIT);
}

export function buildListOptions(q) {
  return {
    orderBy: q.sort || "created_at",
    dir: q.dir === "asc" ? "ASC" : "DESC",
    limit: clampLimit(q.limit),
  };
}

const PRODUCT_SORTS = new Set(["name", "price_cents", "created_at"]);

export function productSort(raw) {
  return PRODUCT_SORTS.has(raw) ? raw : "name";
}

export function pickColumns(raw) {
  if (!raw) return ["id", "email", "created_at"];
  return String(raw).split(",").map((c) => c.trim()).filter(Boolean);
}
