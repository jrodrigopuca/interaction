import { createServer } from 'node:http';
import { getRedis } from './redis.mjs';
import { getProduct } from './products.mjs';
import { readSession } from './sessions.mjs';
import { allow } from './rate-limit.mjs';
import { enqueuePriceUpdate } from './price-queue.mjs';
import { db } from './db.mjs';

const redis = await getRedis();

createServer(async (req, res) => {
  if (!(await allow(redis, req.socket.remoteAddress))) { res.statusCode = 429; return res.end(); }
  const url = new URL(req.url, 'http://x');
  if (req.method === 'GET' && url.pathname.startsWith('/products/')) {
    const p = await getProduct(redis, db, url.pathname.split('/')[2]);
    res.statusCode = p ? 200 : 404;
    return res.end(JSON.stringify(p));
  }
  if (req.method === 'POST' && url.pathname === '/prices') {
    const session = await readSession(redis, req.headers['x-session'] ?? '');
    if (!session) { res.statusCode = 401; return res.end(); }
    let body = '';
    for await (const chunk of req) body += chunk;
    await enqueuePriceUpdate(redis, JSON.parse(body));
    res.statusCode = 202;
    return res.end();
  }
  res.statusCode = 404;
  res.end();
}).listen(Number(process.env.PORT ?? 3000));
