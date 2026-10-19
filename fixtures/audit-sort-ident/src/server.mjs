import http from "node:http";
import { exportReports } from "./routes/reports.mjs";
import { listProducts } from "./routes/products.mjs";
import { exportUsers } from "./routes/users.mjs";
import { requireSession } from "./lib/session.mjs";

const routes = {
  "GET /reports/export": exportReports,
  "GET /products": listProducts,
  "GET /admin/users/export": exportUsers,
};

http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://local");
  const handler = routes[`${req.method} ${url.pathname}`];
  if (!handler) { res.writeHead(404).end(); return; }
  try {
    const session = await requireSession(req);
    const body = await handler({ query: Object.fromEntries(url.searchParams), session });
    res.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(body));
  } catch (e) {
    res.writeHead(e.status ?? 500).end(JSON.stringify({ error: e.publicMessage ?? "internal" }));
  }
}).listen(process.env.PORT ?? 3000);
