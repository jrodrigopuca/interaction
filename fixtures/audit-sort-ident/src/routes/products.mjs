import { clampLimit, productSort } from "../lib/options.mjs";
import { listProducts as list } from "../db/products-repo.mjs";

// GET /products?sort=&limit=
export async function listProducts({ query, session }) {
  return list(session.tenantId, { sort: productSort(query.sort), limit: clampLimit(query.limit) });
}
