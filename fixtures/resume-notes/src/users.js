import { config } from "./config.js";
import { db } from "./db.js";

export async function listUsers(req, res) {
  const size = Math.min(Number(req.query.size) || config.DEFAULT_PAGE_SIZE, config.MAX_PAGE_SIZE);
  const page = Math.max(Number(req.query.page) || 1, 1);
  const rows = await db.users.all();
  res.json({ page, size, items: rows.slice((page - 1) * size, page * size) });
}
