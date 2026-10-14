import { createServer } from 'node:http';
import { handleCreate } from './routes.mjs';

createServer(async (req, res) => {
  if (req.method !== 'POST') { res.statusCode = 405; return res.end(); }
  let body = '';
  for await (const c of req) body += c;
  const out = handleCreate(JSON.parse(body));
  res.statusCode = out.status;
  res.setHeader('location', out.location);
  res.end(JSON.stringify(out.product));
}).listen(Number(process.env.PORT ?? 3000));
