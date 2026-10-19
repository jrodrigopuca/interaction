import { createServer } from "node:http";
import { readFileSync } from "node:fs";

const env = process.env.APP_ENV ?? "staging";
const config = JSON.parse(readFileSync(new URL(`../config/${env}.json`, import.meta.url), "utf8"));

const stock = new Map([
  ["sku-1001", 12],
  ["sku-1002", 0],
]);

function json(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

// Every route is mounted under config.basePath; the health probe is the
// only one that needs no auth.
const server = createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  if (!url.pathname.startsWith(config.basePath)) {
    return json(res, 404, { error: "not found" });
  }
  const route = url.pathname.slice(config.basePath.length);
  if (route === "/health") {
    return json(res, 200, { ok: true, env });
  }
  if (route.startsWith("/stock/")) {
    const sku = route.slice("/stock/".length);
    if (!stock.has(sku)) return json(res, 404, { error: "unknown sku" });
    return json(res, 200, { sku, quantity: stock.get(sku) });
  }
  return json(res, 404, { error: "not found" });
});

server.listen(config.port, () => {
  console.log(`inventory-service (${env}) on ${config.host}:${config.port}${config.basePath}`);
});
